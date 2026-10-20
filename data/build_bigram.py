# -*- coding: utf-8 -*-
"""
构建「下一个词预测」用的 bigram 模型。

语料（有几个用几个）
--------------------
1. 俄语字幕语料 subtitles_ru.txt（口语对白，最贴近 Gboard 的使用场景）
   https://github.com/dbklim/Russian_subtitles_dataset   Apache-2.0   约 292 MB 文本
2. Leipzig Corpora 俄语句子（新闻 / 维基，书面语补充）
   https://wortschatz.uni-leipzig.de/en/download/Russian   CC BY 4.0

输出
----
data/ru-bigram.tsv   每行：`前一个词<TAB>后词:次数 后词:次数 ...`

为什么要两遍扫描
----------------
词表 ru-words.txt 里最短的词是 2 个字母，于是 `я`、`в`、`и`、`с`、`к`、`у`
这些真正的最高频词全被挡在外面——`я` 后面接什么都学不到，等于废掉一整类预测。
所以词表改成**从语料自己统计**：
  第 1 遍数单字 → 取前 VOCAB_LIMIT 个当词表（自然包含单字母词）
  第 2 遍只在这个词表内统计相邻对

过滤
----
- 只保留纯西里尔词（含 ё、连字符），长度 1–24
- bigram 出现次数 ≥ MIN_COUNT
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
OUT = os.path.join(HERE, "ru-bigram.tsv")

CYR = re.compile(r"^[а-яё\-]{1,24}$")
SPLIT = re.compile(r"[^А-Яа-яЁё\-]+")
VOCAB_LIMIT = 25000
MIN_COUNT = 3
MAX_FOLLOWERS = 8
MAX_HEADS = 45000


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


def sources():
    return (("字幕", iter_subtitles), ("Leipzig", iter_leipzig))


def tokens_of(text):
    return [t for t in (x.lower() for x in SPLIT.split(text)) if CYR.match(t)]


def main():
    # ---------- 第 1 遍：单字频次 ----------
    uni = collections.Counter()
    for label, factory in sources():
        lines = hits = 0
        for text in factory():
            lines += 1
            toks = tokens_of(text)
            hits += len(toks)
            uni.update(toks)
        if lines:
            print(f"  [1/2] {label}: {lines} 行 / {hits} 词")

    vocab = {w for w, _ in uni.most_common(VOCAB_LIMIT)}
    print(f"词表（语料统计）: {len(vocab)} 个")
    for w in ("я", "в", "и", "с", "к", "не", "ты"):
        print(f"    {w:4} 出现 {uni.get(w, 0)} 次  在词表: {w in vocab}")

    # ---------- 第 2 遍：相邻对 ----------
    pairs = collections.Counter()
    for label, factory in sources():
        lines = 0
        for text in factory():
            lines += 1
            toks = [t for t in tokens_of(text) if t in vocab]
            for a, b in zip(toks, toks[1:]):
                pairs[(a, b)] += 1
        if lines:
            print(f"  [2/2] {label}: {lines} 行")

    print(f"bigram 种类: {len(pairs)}")
    by_head = collections.defaultdict(list)
    dropped = 0
    for (a, b), c in pairs.items():
        if c < MIN_COUNT:
            dropped += 1
            continue
        by_head[a].append((c, b))
    print(f"过滤低频 {dropped} 条，前词 {len(by_head)} 个")

    heads = sorted(by_head.items(), key=lambda kv: -sum(c for c, _ in kv[1]))
    heads = heads[:MAX_HEADS]
    out, total = [], 0
    for head, followers in heads:
        followers.sort(key=lambda cb: (-cb[0], cb[1]))
        keep = followers[:MAX_FOLLOWERS]
        total += len(keep)
        out.append(head + "\t" + " ".join(f"{w}:{c}" for c, w in keep))

    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(out) + "\n")
    print(f"写出: {OUT}  {len(out)} 前词 / {total} 条组合  "
          f"{os.path.getsize(OUT)/1024/1024:.2f} MB")

    table = {l.split("\t", 1)[0]: l.split("\t", 1)[1] for l in out}
    for w in ("я", "в", "не", "как", "что", "ты", "хочу"):
        if w in table:
            print(f"  {w:6} -> {table[w]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
