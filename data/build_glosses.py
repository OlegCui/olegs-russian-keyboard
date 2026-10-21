# -*- coding: utf-8 -*-
"""
给生词本里的词生成干净的中文释义（替换 Yandex 收藏带过来的机翻）。

用法
----
    python data/build_glosses.py --dry-run          # 只看要处理多少、花多少
    python data/build_glosses.py                    # 真跑（key 从 env 或 --key-file）

特点
----
* 只改 gloss 字段，原值留在 gloss_raw，不丢原始数据
* gloss_src 标成 llm，重跑时自动跳过已处理的
* 每 50 条存一次，中断可续
* 词性一起传，减少歧义（тот 是代词不是名字 Том）
"""
import argparse
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

APP_DIR = os.path.join(os.environ["APPDATA"], "OlegsRussianKeyboard")
WB = os.path.join(APP_DIR, "wordbook.json")

SYSTEM = ('你是俄语词典编辑。只输出 JSON：{"gloss":"中文释义，最多12字，'
          '多个义项用 / 分隔"}。不要解释，不要造句，不要带「它/他/她/吧/了」这类句子成分。')


POS_ZH = {"NOUN": "名词", "INFN": "动词", "VERB": "动词",
          "ADJF": "形容词", "ADVB": "副词", "NUMR": "数词",
          "NPRO": "代词", "PREP": "前置词", "CONJ": "连词",
          "PRCL": "语气词", "INTJ": "感叹词"}
# 这些是"形式"不是词性：быть 被标成副动词，就是因为取了第一个 parse
INFLECTED = ("PRTF", "PRTS", "GRND", "ADJS")


def fix_pos(words):
    """按原形重新判定词性。"""
    import pymorphy3
    morph = pymorphy3.MorphAnalyzer()
    changed = 0
    for w in words:
        lemma = (w.get("lemma") or w["word"]).lower()
        want = None
        for p in morph.parse(lemma)[:6]:
            if p.normal_form.lower() != lemma:
                continue
            if p.tag.POS in INFLECTED:
                continue
            want = POS_ZH.get(p.tag.POS or "", "")
            # тот / этот / такой 这类是代词性的形容词，中文教学一律叫代词
            if want == "形容词" and "Apro" in p.tag:
                want = "代词"
            if want:
                break
        if want and want != w.get("pos"):
            w["pos"] = want
            changed += 1
    return changed


TOK_IN, TOK_OUT = 70, 18
PRICE = {"in_hit": 0.5, "out": 8.0}


def ask(word, pos, key, model, base, timeout=40):
    import urllib.error
    import urllib.request

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"词：{word}（{pos or '词性未知'}）"},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "max_tokens": 60,
    }
    req = urllib.request.Request(
        base.rstrip("/") + "/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {key}"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return None, None, f"HTTP {e.code}"
    except Exception as e:
        return None, None, f"{type(e).__name__}: {e}"
    usage = data.get("usage") or {}
    try:
        obj = json.loads(data["choices"][0]["message"]["content"])
        g = (obj.get("gloss") or "").strip()
    except Exception as e:
        return None, usage, f"JSON: {e}"
    if not g or len(g) > 24:
        return None, usage, "释义为空或过长"
    return g, usage, ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--key", default=os.environ.get("DEEPSEEK_API_KEY", ""))
    ap.add_argument("--key-file", default="")
    ap.add_argument("--model", default="deepseek-chat")
    ap.add_argument("--api-base", default="https://api.deepseek.com")
    ap.add_argument("--delay", type=float, default=0.12)
    a = ap.parse_args()

    data = json.load(open(WB, encoding="utf-8"))
    words = data.get("words") or []
    todo = [w for w in words if w.get("gloss_src") != "llm"]
    if a.limit:
        todo = todo[:a.limit]

    print(f"  生词本共 {len(words)} 条")
    print(f"  待修释义: {len(todo)} 条（已用模型生成的会跳过）")
    cost = (TOK_IN * len(todo) / 1e6 * PRICE["in_hit"]
            + TOK_OUT * len(todo) / 1e6 * PRICE["out"])
    print(f"  预估: 输入 {TOK_IN*len(todo)/1e6:.2f}M / "
          f"输出 {TOK_OUT*len(todo)/1e6:.2f}M token ≈ ¥{cost:.1f}")
    if a.dry_run:
        print("\n  --dry-run：没联网、没写文件。前 8 条：")
        for w in todo[:8]:
            print(f"    {w['word']:16} {w.get('pos',''):4} "
                  f"现在: {w.get('gloss') or '（空）'}")
        return 0

    if not a.key and a.key_file:
        a.key = open(os.path.expanduser(a.key_file), encoding="utf-8").read().strip()
    if not a.key:
        print("\n  缺少 API key：DEEPSEEK_API_KEY 或 --key-file")
        return 2
    if not todo:
        print("\n  全部已处理")
        return 0

    changed = fix_pos(words)
    print(f"  顺手修正词性: {changed} 条")

    done = fail = 0
    tin = tout = 0
    t0 = time.time()
    by_id = {id(w): w for w in words}

    for i, w in enumerate(todo, 1):
        g, usage, err = ask(w["word"], w.get("pos", ""), a.key, a.model, a.api_base)
        if g is None:
            g, usage2, err2 = ask(w["word"], w.get("pos", ""), a.key, a.model, a.api_base)
            usage = usage2 or usage
            err = err2 or err
        if usage:
            tin += usage.get("prompt_tokens", 0)
            tout += usage.get("completion_tokens", 0)
        if g is None:
            fail += 1
            if fail <= 5:
                print(f"  [{i}] {w['word']:16} 失败: {err}")
        else:
            w["gloss_raw"] = w.get("gloss_raw") or w.get("gloss") or ""
            w["gloss"] = g
            w["gloss_src"] = "llm"
            done += 1
        if i % 50 == 0:
            json.dump(data, open(WB + ".tmp", "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
            os.replace(WB + ".tmp", WB)
            print(f"  [{i}/{len(todo)}] 已改 {done}，"
                  f"{time.time()-t0:.0f}s")

    json.dump(data, open(WB + ".tmp", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    os.replace(WB + ".tmp", WB)
    real = tin / 1e6 * PRICE["in_hit"] + tout / 1e6 * PRICE["out"]
    print(f"\n  完成 {done} 条，失败 {fail} 条，"
          f"耗时 {(time.time()-t0)/60:.1f} 分钟")
    print(f"  实际用量: 输入 {tin/1e6:.2f}M / 输出 {tout/1e6:.2f}M token")
    print(f"  实际成本: ¥{real:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
