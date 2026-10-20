# -*- coding: utf-8 -*-
"""
统计俄语语料里的**原形**频次，产出 data/ru-lemmas.tsv。

为什么按原形
------------
俄语一个词平均十几个变形。按词形统计会让 `говорю/говорит/говорил…`
各算一次，排名完全失真（实测：2300 个词形只覆盖 63%，而 2300 个原形覆盖 87%）。

输出
----
data/ru-lemmas.tsv    `原形<TAB>频次`，按频次降序

用途
----
决定"给哪些词做深度卡"、以及算覆盖率。和例句/预测用的是同一批语料。
"""
import collections
import os
import re
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
TMP = os.environ.get("TEMP", "/tmp")
SUBS_ZIP = os.path.join(TMP, "subtitles_ru.txt.zip")
OUT = os.path.join(HERE, "ru-lemmas.tsv")

SPLIT = re.compile(r"[^А-Яа-яЁё\-]+")
LINE_LIMIT = 1_200_000        # 再多也不会改变前 3 万的排序


def main():
    if not os.path.exists(SUBS_ZIP):
        print("缺少字幕语料", file=sys.stderr)
        return 1
    import pymorphy3
    morph = pymorphy3.MorphAnalyzer()
    cache = {}

    def lemma(w):
        if w in cache:
            return cache[w]
        try:
            lem = morph.parse(w)[0].normal_form
        except Exception:
            lem = w
        cache[w] = lem
        return lem

    counter = collections.Counter()
    total = 0
    with zipfile.ZipFile(SUBS_ZIP) as z:
        name = z.infolist()[0].filename
        with z.open(name) as raw:
            for i, line in enumerate(raw):
                if i >= LINE_LIMIT:
                    break
                for t in SPLIT.split(line.decode("utf-8", "ignore")):
                    t = t.lower()
                    if not t:
                        continue
                    total += 1
                    counter[lemma(t)] += 1

    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        for w, c in counter.most_common():
            if len(w) >= 1:
                fh.write(f"{w}\t{c}\n")

    print(f"扫描 {LINE_LIMIT} 行 / {total} 词 · 原形 {len(counter):,}")
    print(f"写出 {OUT}  {os.path.getsize(OUT)/1024/1024:.2f} MB")
    for w, c in counter.most_common(12):
        print(f"  {w:12} {c:>8,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
