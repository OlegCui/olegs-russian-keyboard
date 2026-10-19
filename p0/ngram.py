# -*- coding: utf-8 -*-
"""
P0 实验①：用公开语料现搭一个俄语 n-gram，看能不能复现 Gboard 的 "я хочу → чтобы/быть"。

语料：ru.wikipedia.org 随机条目（正文 ns=0）+ 讨论页（ns=1，含第一人称口语）
做法：拉取 → 抽纯文本 → 分词 → 统计 bigram → 对探针词输出条件概率 top-10
"""
import collections
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "data", "wiki_ru.txt")
UA = "ru-ime-p0/0.1 (research prototype; contact: local)"

TOKEN = re.compile(r"[а-яёА-ЯЁ]+(?:-[а-яёА-ЯЁ]+)?")
PROBES = ["хочу", "хочет", "хотим", "привет", "нужно", "помочь"]


def api(params):
    params = dict(params, format="json")
    url = "https://ru.wikipedia.org/w/api.php?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch(ns, batches, per=20):
    got = []
    for i in range(batches):
        try:
            d = api({
                "action": "query", "generator": "random", "grnnamespace": ns,
                "grnlimit": per, "prop": "extracts", "explaintext": 1, "exlimit": per,
            })
        except Exception as e:
            print(f"  [warn] batch {i} ns={ns} failed: {e}")
            continue
        pages = d.get("query", {}).get("pages", {})
        texts = [p.get("extract", "") for p in pages.values()]
        got.extend(t for t in texts if len(t) > 200)
        print(f"  ns={ns} batch {i+1}/{batches}: +{len(texts)} pages")
        time.sleep(0.3)
    return got


def main():
    print("拉取语料 …")
    texts = fetch(0, 8) + fetch(1, 8)
    print(f"有效页面: {len(texts)}")

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n\n".join(texts))
    mb = os.path.getsize(OUT) / 1024 / 1024
    print(f"语料落盘: {OUT} ({mb:.1f} MB)")

    uni = collections.Counter()
    bi = collections.defaultdict(collections.Counter)
    tokens = 0
    for t in texts:
        ws = [w.lower() for w in TOKEN.findall(t)]
        tokens += len(ws)
        uni.update(ws)
        for a, b in zip(ws, ws[1:]):
            bi[a][b] += 1

    print(f"token 总数: {tokens:,}   词表: {len(uni):,}   不同 bigram 首词: {len(bi):,}")
    print()
    print("=" * 64)
    print("探针：给定第一个词，模型预测的下一个词（条件概率 top-10）")
    print("=" * 64)
    for p in PROBES:
        n = uni.get(p, 0)
        print(f'\n"{p}"  出现 {n} 次')
        if n == 0:
            print("   （语料里没有这个词）")
            continue
        for w, c in bi[p].most_common(10):
            print(f"   {w:16} {c:5}  {c/n*100:5.1f}%")

    print()
    print("=" * 64)
    print("对照 Gboard: 输入 я хочу → предложить | чтобы | быть")
    print("=" * 64)
    n = uni.get("хочу", 0)
    got = [w for w, _ in bi["хочу"].most_common(10)] if n else []
    for target in ["чтобы", "быть", "предложить"]:
        mark = "✔ 命中" if target in got else "✘ 未进前10"
        print(f"  {target:12} {mark}")
    print()
    print("注意：Wikipedia 是百科语体，第一人称「я хочу」天然稀疏；")
    print("      对话语料（字幕/论坛）才会让这个 bigram 变强。")


if __name__ == "__main__":
    main()
