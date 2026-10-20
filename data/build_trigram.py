# -*- coding: utf-8 -*-
"""
构建三元组模型（看前两个词，预测第三个词）。

语料
----
1. 俄语字幕语料 subtitles_ru.txt（口语对白）   Apache-2.0
2. Leipzig 俄语句子（新闻 / 维基）              CC BY 4.0

输出
----
data/ru-trigram.tsv   每行：`前一词 前两词<TAB>后词:次数 后词:次数 ...`

为什么要裁剪
------------
全量三元组有 168 万种，存下来几十 MB。实测只要满足两个条件就够用：
  1. 前两个词本身组成的二元组至少出现 20 次
  2. 这个三元组至少出现 3 次
留下的 2.5 万个前两词 / 6.7 万条组合，约 1.4 MB，覆盖了日常对话里
真正的固定搭配（`я не знаю`、`ты не знаешь`、`в этом году`）。

运行时是"三元组优先，不命中退回二元组"，所以覆盖率不会因为裁剪而塌。
"""
import collections
import glob
import os
import re
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
TMP = os.environ.get("TEMP", "/tmp")
SUBS_ZIP = os.path.join(TMP, "subtitles_ru.txt.zip")
LEIPZIG = os.path.join(TMP, "leipzig")
BIGRAM = os.path.join(HERE, "ru-bigram.tsv")
OUT = os.path.join(HERE, "ru-trigram.tsv")

SPLIT = re.compile(r"[^А-Яа-яЁё\-]+")
HEAD_MIN = 20          # 前两词组合至少要出现这么多次
TRI_MIN = 3            # 三元组本身至少出现这么多次
MAX_FOLLOWERS = 4      # 每个前两词最多保留几个后词


def iter_subtitles():
    if not os.path.exists(SUBS_ZIP):
        return
    with zipfile.ZipFile(SUBS_ZIP) as z:
        name = z.infolist()[0].filename
        with z.open(name) as raw:
            for line in raw:
                yield line.decode("utf-8", "ignore")


def iter_leipzig():
    for path in sorted(glob.glob(os.path.join(LEIPZIG, "*-sentences.txt"))):
        with open(path, encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                parts = line.rstrip("\n").split("\t")
                if len(parts) >= 2:
                    yield parts[-1]


def main():
    vocab, allowed = set(), set()
    with open(BIGRAM, encoding="utf-8") as fh:
        for line in fh:
            head, _, rest = line.rstrip("\n").partition("\t")
            vocab.add(head)
            for item in rest.split(" "):
                w, _, c = item.rpartition(":")
                if not w:
                    continue
                vocab.add(w)
                try:
                    if int(c) >= HEAD_MIN:
                        allowed.add((head, w))
                except ValueError:
                    pass
    print(f"词表 {len(vocab)}，前两词组合（≥{HEAD_MIN} 次）{len(allowed)}")

    tri = collections.Counter()
    lines = 0
    for factory in (iter_subtitles, iter_leipzig):
        for text in factory():
            lines += 1
            t = [x.lower() for x in SPLIT.split(text)]
            t = [x for x in t if x in vocab]
            for i in range(len(t) - 2):
                a, b, c = t[i], t[i + 1], t[i + 2]
                if (a, b) in allowed:
                    tri[(a, b, c)] += 1
    print(f"扫描 {lines} 行，三元组种类 {len(tri)}")

    by_head = collections.defaultdict(list)
    for (a, b, c), n in tri.items():
        if n >= TRI_MIN:
            by_head[(a, b)].append((n, c))
    print(f"过滤（≥{TRI_MIN} 次）后前两词 {len(by_head)} 个")

    heads = sorted(by_head.items(), key=lambda kv: -sum(n for n, _ in kv[1]))
    out, total = [], 0
    for (a, b), followers in heads:
        followers.sort(key=lambda nc: (-nc[0], nc[1]))
        keep = followers[:MAX_FOLLOWERS]
        total += len(keep)
        out.append(f"{a} {b}\t" + " ".join(f"{w}:{n}" for n, w in keep))

    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(out) + "\n")
    print(f"写出: {OUT}  {len(out)} 前两词 / {total} 条组合  "
          f"{os.path.getsize(OUT)/1024/1024:.2f} MB")

    table = {l.split("\t", 1)[0]: l.split("\t", 1)[1] for l in out}
    for key in ("я не", "ты не", "в этом", "я думаю", "не знаю", "как ты"):
        if key in table:
            print(f"  {key:9} -> {table[key]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
