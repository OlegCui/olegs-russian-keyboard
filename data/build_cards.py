# -*- coding: utf-8 -*-
"""
批量生成深度卡（ru-cards.tsv）。

用法
----
    # 先看会做什么、大概花多少（不联网、不写文件）
    python data/build_cards.py --limit 3000 --dry-run

    # 真跑（key 从环境变量读）
    set DEEPSEEK_API_KEY=sk-xxxx
    python data/build_cards.py --limit 3000

    # 波谷时段（DeepSeek 00:30-08:30 北京时间，deepseek-chat 半价）
    python data/build_cards.py --limit 3000 --offpeak

设计要点
--------
* 断点续跑：已经有的词直接跳过，每张卡生成后立刻落盘，中断不丢已花的钱
* 不覆盖手写卡：只追加新词，已有的 50 张原样不动
* 先算后跑：--dry-run 打印预估成本；真跑结束打印接口返回的实际 token 用量
* 格式兜底：JSON 不合法重试一次，再不行跳过并记录，不写半张破卡
"""
import argparse
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
LEMMAS = os.path.join(HERE, "ru-lemmas.tsv")
CARDS = os.path.join(HERE, "ru-cards.tsv")

FIELDS = ("lemma", "pos", "gloss", "aspect", "pattern",
          "colloc", "compare", "errors", "src")

SYSTEM = """你是俄语教学词典编辑，为中文母语学习者编写词条卡片。
只输出 JSON，不要解释。字段固定为：
gloss  中文释义，一句话，不超 25 字
pattern 支配结构，如 "+ 宾格 + как + 宾格"，没有就空字符串
colloc 3 个高频搭配，俄语，用 · 分隔
compare 近义辨析，指出与哪个词的区别，不超 40 字
errors 1-2 条中国学生典型错误，格式 ❌ 错误 → ✅ 正确
要求：不确定的字段留空字符串，不要编造。"""

FEWSHOT = """词：расценить（动词）
{"gloss":"评价；估价；视为","pattern":"+ 宾格 + как + 宾格/形容词",
 "colloc":"расценить как угрозу · расценить по достоинству · расценить как победу",
 "compare":"与 оценить（最通用）、считать（更口语）区分",
 "errors":"❌ Расценить это успехом → ✅ Расценить это как успех"}

词：дверь（名词，阴性）
{"gloss":"门","pattern":"","colloc":"открыть дверь · закрыть дверь · входная дверь",
 "compare":"与 калитка（院门）、ворота（大门）区分",
 "errors":"❌ в дверь стоит → ✅ дверь стоит"}"""

# 约 312 token 输入 / 83 token 输出（实测 estimate_cost.py）
TOK_IN, TOK_OUT = 312, 83
PRICE = {"in_miss": 2.0, "in_hit": 0.5, "out": 8.0}   # 元 / 百万 token


def load_lemmas(path=LEMMAS):
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line or "\t" not in line:
                continue
            w, _, c = line.partition("\t")
            try:
                out.append((w.strip(), int(c)))
            except ValueError:
                continue
    out.sort(key=lambda x: -x[1])
    return out


def load_existing(path=CARDS):
    """已有卡的原形集合 + 文件末尾是否缺换行。"""
    have, tail_ok = set(), True
    if not os.path.exists(path):
        return have, False
    with open(path, encoding="utf-8") as fh:
        raw = fh.read()
    tail_ok = raw.endswith("\n")
    for line in raw.splitlines():
        if not line or line.startswith("#"):
            continue
        have.add(line.split("\t")[0].strip().lower())
    return have, tail_ok


def morph_info(word, morph):
    """给模型一点形态信息：词性 + 名词性别。"""
    try:
        p = morph.parse(word)[0]
        pos = p.tag.POS
        zh = {"NOUN": "名词", "VERB": "动词", "INFN": "动词", "ADJF": "形容词",
              "ADJS": "形容词", "ADVB": "副词", "PRTF": "分词", "PRTS": "分词",
              "GRND": "副动词", "NUMR": "数词", "NPRO": "代词",
              "PREP": "前置词", "CONJ": "连词", "PRCL": "语气词",
              "INTJ": "感叹词"}.get(pos or "", "")
        extra = ""
        if pos == "NOUN":
            g = {"masc": "阳性", "femn": "阴性", "neut": "中性"}.get(
                getattr(p.tag, "gender", "") or "", "")
            if g:
                extra = "，" + g
        return f"（{zh}{extra}）" if zh else ""
    except Exception:
        return ""


def request_card(word, morph, key, model, api_base, timeout=60):
    """调一次接口，返回 (dict 或 None, usage 或 None, 错误信息)。"""
    import urllib.request
    import urllib.error

    user = f"词：{word}{morph_info(word, morph)}"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": FEWSHOT + "\n\n" + user},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.3,
        "max_tokens": 400,
    }
    req = urllib.request.Request(
        api_base.rstrip("/") + "/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {key}"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:200]
        return None, None, f"HTTP {e.code}: {body}"
    except Exception as e:
        return None, None, f"{type(e).__name__}: {e}"

    usage = data.get("usage") or {}
    try:
        content = data["choices"][0]["message"]["content"].strip()
        obj = json.loads(content)
    except Exception as e:
        return None, usage, f"JSON 解析失败: {e}"
    if not isinstance(obj, dict) or not obj.get("gloss"):
        return None, usage, "缺少 gloss 字段"
    return obj, usage, ""


def row_of(word, pos_zh, obj):
    def clean(v, limit=300):
        s = str(v or "").replace("\t", " ").replace("\n", " ").strip()
        return s[:limit]

    return "\t".join([
        word, pos_zh, clean(obj.get("gloss"), 40),
        clean(obj.get("aspect"), 10), clean(obj.get("pattern"), 80),
        clean(obj.get("colloc"), 160), clean(obj.get("compare"), 120),
        clean(obj.get("errors"), 160), "m",
    ])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=3000)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--model", default="deepseek-chat")
    ap.add_argument("--api-base", default="https://api.deepseek.com")
    ap.add_argument("--key", default=os.environ.get("DEEPSEEK_API_KEY", ""))
    ap.add_argument("--key-file", default="",
                    help="从文件读 key（避免出现在命令行历史/聊天记录里）")
    ap.add_argument("--delay", type=float, default=0.25,
                    help="每张之间停顿，避免触发限流")
    ap.add_argument("--min-count", type=int, default=0,
                    help="只处理词频 >= 该值的词")
    ap.add_argument("--offpeak", action="store_true",
                    help="按波谷半价估算")
    ap.add_argument("--out", default=CARDS)
    a = ap.parse_args()

    lemmas = load_lemmas()
    have, tail_ok = load_existing(a.out)
    todo = [(w, c) for w, c in lemmas
            if w.lower() not in have and c >= a.min_count and len(w) >= 2]

    print(f"  词频表: {len(lemmas)} 个原形")
    print(f"  已有卡: {len(have)} 个")
    print(f"  待生成: {min(len(todo), a.limit)} 个（可用 {len(todo)}）")

    n = min(len(todo), a.limit)
    hin, hout = TOK_IN * n / 1e6, TOK_OUT * n / 1e6
    cost = hin * PRICE["in_hit"] + hout * PRICE["out"]
    if a.offpeak:
        cost *= 0.5
    print(f"  预估用量: 输入 {hin:.2f}M / 输出 {hout:.2f}M token")
    print(f"  预估成本: ¥{cost:.1f}" + ("（波谷半价）" if a.offpeak else ""))
    if a.dry_run:
        print("\n  --dry-run：不联网、不写文件。前 10 个词：")
        for w, c in todo[:10]:
            print(f"    {w:16} 频次 {c}")
        return 0

    if not a.key and a.key_file:
        try:
            with open(os.path.expanduser(a.key_file), encoding="utf-8") as fh:
                a.key = fh.read().strip()
        except Exception as e:
            print(f"  读 key 文件失败: {e}")
    if not a.key:
        print("\n  缺少 API key：设置 DEEPSEEK_API_KEY，或用 --key-file 指向一个文本文件")
        return 2

    try:
        import pymorphy3
        morph = pymorphy3.MorphAnalyzer()
    except Exception as e:
        print(f"  需要 pymorphy3: {e}")
        return 2

    if not tail_ok:
        with open(a.out, "a", encoding="utf-8") as fh:
            fh.write("\n")

    done, failed = 0, []
    tin = tout = 0
    t0 = time.time()
    for i, (word, cnt) in enumerate(todo[:a.limit], 1):
        obj, usage, err = request_card(word, morph, a.key, a.model, a.api_base)
        if obj is None:                       # 重试一次
            obj, usage2, err2 = request_card(word, morph, a.key, a.model,
                                             a.api_base)
            usage = usage2 or usage
            err = err2 or err
        if usage:
            tin += usage.get("prompt_tokens", 0)
            tout += usage.get("completion_tokens", 0)
        if obj is None:
            failed.append((word, err))
            print(f"  [{i}/{n}] {word:16} 失败: {err[:60]}")
        else:
            with open(a.out, "a", encoding="utf-8") as fh:
                fh.write(row_of(word, morph_info(word, morph).strip("（）"),
                                obj) + "\n")
            done += 1
            if i % 25 == 0 or i <= 3:
                print(f"  [{i}/{n}] {word:16} 累计 {done} 张，"
                      f"{time.time()-t0:.0f}s")
        time.sleep(a.delay)

    real = (tin / 1e6 * PRICE["in_hit"] + tout / 1e6 * PRICE["out"])
    print(f"\n  完成 {done} 张，失败 {len(failed)} 个，"
          f"耗时 {(time.time()-t0)/60:.1f} 分钟")
    print(f"  实际用量: 输入 {tin/1e6:.2f}M / 输出 {tout/1e6:.2f}M token")
    print(f"  实际成本: ¥{real:.2f}")
    if failed:
        log = os.path.join(HERE, "cards-failed.txt")
        with open(log, "w", encoding="utf-8") as fh:
            for w, e in failed:
                fh.write(f"{w}\t{e}\n")
        print(f"  失败清单: {log}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
