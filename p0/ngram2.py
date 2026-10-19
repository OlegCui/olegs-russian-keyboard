# -*- coding: utf-8 -*-
"""
P0 实验①（v2）：在有限网络/限流条件下，用最少请求搭出可用的俄语 n-gram。

策略：
  A) 文章导语：generator=random(ns=0) + exintro + exlimit=20，一请求 20 页
  B) 讨论页全文：ns=1 单页请求（讨论页有第一人称口语，正是 "я хочу" 的来源）

产出：
  - 语料落盘 data/wiki_ru.txt
  - bigram 条件概率，探针 хочу / привет / нужно
  - 与 Gboard 的 я хочу → предложить|чтобы|быть 对照
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
UA = {"User-Agent": "ru-ime-p0/0.1 (research; contact: local)"}
TOKEN = re.compile(r"[а-яёА-ЯЁ]+(?:-[а-яёА-ЯЁ]+)?")
PROBES = ["хочу", "хочет", "привет", "нужно", "помочь", "быть"]

REQ = 0
ERR = 0


def api(p, tries=4):
    global REQ, ERR
    p = dict(p, format="json")
    u = "https://ru.wikipedia.org/w/api.php?" + urllib.parse.urlencode(p)
    for k in range(tries):
        try:
            REQ += 1
            r = urllib.request.Request(u, headers=UA)
            return json.loads(urllib.request.urlopen(r, timeout=40).read().decode("utf-8"))
        except Exception as e:
            ERR += 1
            wait = 3 + 3 * k
            print(f"    [retry {k+1}] {e} -> sleep {wait}s")
            time.sleep(wait)
    return {}


def article_intros(batches=5, per=20):
    out = []
    for i in range(batches):
        d = api({"action": "query", "generator": "random", "grnnamespace": 0,
                 "grnlimit": per, "prop": "extracts", "explaintext": 1,
                 "exintro": 1, "exlimit": per})
        pages = d.get("query", {}).get("pages", {})
        got = [p.get("extract", "") for p in pages.values() if len(p.get("extract", "")) > 150]
        out.extend(got)
        print(f"  A{i+1}: +{len(got)} intros (total {len(out)})")
        time.sleep(0.8)
    return out


def talk_pages(n=25):
    out = []
    for i in range(n):
        d = api({"action": "query", "generator": "random", "grnnamespace": 1,
                 "grnlimit": 1, "prop": "extracts", "explaintext": 1, "exlimit": 1})
        pages = d.get("query", {}).get("pages", {})
        for p in pages.values():
            t = p.get("extract", "")
            if len(t) > 1000:
                out.append(t)
        if (i + 1) % 5 == 0:
            print(f"  B{i+1}/{n}: talk pages 有效 {len(out)}")
        time.sleep(0.7)
    return out


def main():
    print("A) 文章导语 …")
    intros = article_intros(5, 20)
    print("\nB) 讨论页全文 …")
    talks = talk_pages(25)

    texts = intros + talks
    chars = sum(len(t) for t in texts)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n\n".join(texts))
    print(f"\n页面 {len(texts)}（导语 {len(intros)} + 讨论 {len(talks)}），字符 {chars:,}，"
          f"落盘 {os.path.getsize(OUT)/1024:.0f} KB")
    print(f"请求 {REQ} 次，失败重试 {ERR} 次\n")

    uni = collections.Counter()
    bi = collections.defaultdict(collections.Counter)
    tokens = 0
    for t in texts:
        ws = [w.lower() for w in TOKEN.findall(t)]
        tokens += len(ws)
        uni.update(ws)
        for a, b in zip(ws, ws[1:]):
            bi[a][b] += 1

    print(f"token {tokens:,}  词表 {len(uni):,}  bigram 首词种类 {len(bi):,}")
    print("=" * 60)
    for p in PROBES:
        n = uni.get(p, 0)
        print(f'\n"{p}" 出现 {n} 次')
        if not n:
            continue
        for w, c in bi[p].most_common(8):
            print(f"   {w:16}{c:5}  {c/n*100:5.1f}%")

    print("\n" + "=" * 60)
    n = uni.get("хочу", 0)
    got = [w for w, _ in bi["хочу"].most_common(15)] if n else []
    print("对照 Gboard（я хочу → предложить | чтобы | быть）:")
    for t in ["чтобы", "быть", "предложить"]:
        print(f"   {t:12} {'✔ 命中' if t in got else '✘ 未进前15'}")

    # 语体差异：第一人称代词密度
    vlast = uni.get("я", 0) / max(tokens, 1) * 1000
    print(f"\n第一人称 «я» 密度: {vlast:.1f} ‰（对话语料通常 >20‰，百科语料 <3‰）")


if __name__ == "__main__":
    main()
