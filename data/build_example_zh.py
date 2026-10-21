# -*- coding: utf-8 -*-
r"""
给例句加中文翻译（离线烘焙进数据文件）。

为什么要做：例句原来只有俄语，学的人常常看不懂那句；有中文才能当"例句"用。

用法
----
    python data/build_example_zh.py --limit 3000 --dry-run
    python data/build_example_zh.py --limit 3000 --key-file %TEMP%\ds_key.txt

输出 ru-examples-zh.tsv：原形 \t 俄语句子 \t 中文翻译
断点续跑：已翻过的句子会跳过（按句子文本比对）。
"""
import argparse
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "ru-examples.tsv")
OUT = os.path.join(HERE, "ru-examples-zh.tsv")
LEMMAS = os.path.join(HERE, "ru-lemmas.tsv")

SYSTEM = ("把俄语句子译成自然的中文，只输出译文，不要解释、不要加引号。"
          "人名地名照常音译。")
TOK_IN, TOK_OUT = 55, 35
PRICE = {"in": 0.5, "out": 8.0}


def rank_of():
    r = {}
    with open(LEMMAS, encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            w = line.split("\t")[0].strip().lower()
            if w and w not in r:
                r[w] = i
    return r


def load_done():
    done = set()
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as fh:
            for line in fh:
                parts = line.rstrip("\n").split("\t")
                if len(parts) >= 3:
                    done.add(parts[1])
    return done


def translate(sentence, key, model, base, timeout=45):
    import urllib.error
    import urllib.request

    payload = {
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": sentence}],
        "temperature": 0.2,
        "max_tokens": 120,
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
        zh = data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return None, usage, f"结构异常: {e}"
    zh = zh.replace("\n", " ").strip().strip('"').strip()
    if not zh or len(zh) > 200:
        return None, usage, "译文为空或过长"
    return zh, usage, ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--key", default=os.environ.get("DEEPSEEK_API_KEY", ""))
    ap.add_argument("--key-file", default="")
    ap.add_argument("--model", default="deepseek-chat")
    ap.add_argument("--api-base", default="https://api.deepseek.com")
    ap.add_argument("--delay", type=float, default=0.1)
    a = ap.parse_args()

    rows = []
    with open(SRC, encoding="utf-8") as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 2 and parts[0] and parts[1]:
                rows.append((parts[0].lower(), parts[1]))

    rank = rank_of()
    rows.sort(key=lambda x: rank.get(x[0], 10 ** 9))
    done = load_done()
    todo = [(w, s) for w, s in rows if s not in done]
    if a.limit:
        todo = todo[:a.limit]

    print(f"  例句总数: {len(rows)}")
    print(f"  已翻译: {len(done)}")
    print(f"  本次待翻: {len(todo)}")
    cost = (TOK_IN * len(todo) / 1e6 * PRICE["in"]
            + TOK_OUT * len(todo) / 1e6 * PRICE["out"])
    print(f"  预估: 输入 {TOK_IN*len(todo)/1e6:.2f}M / "
          f"输出 {TOK_OUT*len(todo)/1e6:.2f}M token ≈ ¥{cost:.1f}")

    if a.dry_run:
        print("\n  --dry-run：不联网。前 5 条：")
        for w, s in todo[:5]:
            print(f"    [{w}] {s[:60]}")
        return 0

    if not a.key and a.key_file:
        a.key = open(os.path.expanduser(a.key_file), encoding="utf-8").read().strip()
    if not a.key:
        print("\n  缺少 API key")
        return 2
    if not todo:
        print("\n  全部翻完了")
        return 0

    ok = fail = 0
    tin = tout = 0
    t0 = time.time()
    with open(OUT, "a", encoding="utf-8") as out:
        for i, (w, s) in enumerate(todo, 1):
            zh, usage, err = translate(s, a.key, a.model, a.api_base)
            if usage:
                tin += usage.get("prompt_tokens", 0)
                tout += usage.get("completion_tokens", 0)
            if zh is None:
                fail += 1
                if fail <= 5:
                    print(f"  [{i}] 失败: {err} | {s[:40]}")
            else:
                out.write(f"{w}\t{s}\t{zh}\n")
                out.flush()
                ok += 1
            if i % 100 == 0:
                print(f"  [{i}/{len(todo)}] 已翻 {ok}，{time.time()-t0:.0f}s")
            time.sleep(a.delay)

    real = tin / 1e6 * PRICE["in"] + tout / 1e6 * PRICE["out"]
    print(f"\n  完成 {ok}，失败 {fail}，耗时 {(time.time()-t0)/60:.1f} 分钟")
    print(f"  实际用量: 输入 {tin/1e6:.2f}M / 输出 {tout/1e6:.2f}M token")
    print(f"  实际成本: ¥{real:.2f}")
    print(f"  输出: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
