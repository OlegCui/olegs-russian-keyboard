# -*- coding: utf-8 -*-
"""
统计三元组，先看数据量再决定裁剪（不直接写成品）。

思路
----
三元组 (w1 w2 → w3) 的数量级远大于二元组。全量存下来几十 MB，
所以只统计"值得存"的：前两个词组成的二元组本身要足够常见。

用法：python data/probe_trigram.py
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

SPLIT = re.compile(r"[^А-Яа-яЁё\-]+")
VOCAB_LIMIT = 25000


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


def tokens(text, vocab=None):
    out = [t for t in (x.lower() for x in SPLIT.split(text))]
    if vocab:
        out = [t for t in out if t in vocab]
    return out


def load_bigram_pairs(min_count):
    """从已有二元组里取「足够常见」的前两个词组合。"""
    pairs = set()
    if not os.path.exists(BIGRAM):
        return pairs
    with open(BIGRAM, encoding="utf-8") as fh:
        for line in fh:
            head, _, rest = line.rstrip("\n").partition("\t")
            for item in rest.split(" "):
                w, _, c = item.rpartition(":")
                try:
                    if int(c) >= min_count:
                        pairs.add((head, w))
                except ValueError:
                    continue
    return pairs


def main():
    # 词表：用 bigram 文件里出现过的高频词
    vocab = set()
    with open(BIGRAM, encoding="utf-8") as fh:
        for line in fh:
            head, _, rest = line.rstrip("\n").partition("\t")
            vocab.add(head)
            for item in rest.split(" "):
                w, _, _c = item.rpartition(":")
                if w:
                    vocab.add(w)
    print(f"词表（来自二元组）: {len(vocab)}")

    for head_min in (20, 50):
        allowed = load_bigram_pairs(head_min)
        print(f"\n=== 前两词组合出现 ≥{head_min} 次的: {len(allowed)} 对 ===")
        tri = collections.Counter()
        lines = 0
        for factory in (iter_subtitles, iter_leipzig):
            for text in factory():
                lines += 1
                t = tokens(text, vocab)
                for i in range(len(t) - 2):
                    a, b, c = t[i], t[i + 1], t[i + 2]
                    if (a, b) in allowed:
                        tri[(a, b, c)] += 1
        print(f"  扫描 {lines} 行，三元组种类: {len(tri)}")
        for thr in (3, 5, 10):
            kept = [(k, v) for k, v in tri.items() if v >= thr]
            heads = collections.defaultdict(int)
            for (a, b, c), v in kept:
                heads[(a, b)] += 1
            # 每个前两词保留最多 4 个后词
            total = 0
            for h, n in heads.items():
                total += min(n, 4)
            size_mb = total * 22 / 1024 / 1024      # 粗估每条 22 字节
            print(f"   次数≥{thr}: 组合 {len(kept)}, 前两词 {len(heads)}, "
                  f"保留(每头≤4) {total} 条 ≈ {size_mb:.1f} MB")
        del tri


if __name__ == "__main__":
    sys.exit(main())
