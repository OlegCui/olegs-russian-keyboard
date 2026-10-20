# -*- coding: utf-8 -*-
"""
从字幕语料给高频词挑例句（第二版：带质量打分）。

输出
----
data/ru-examples.tsv   `原形<TAB>例句`

挑句规则
--------
硬性过滤（不合就直接丢）：
- 长度 18–75 字符
- 只有一个句末标点（避免"两句拼一起"）
- 不含拉丁字母、数字、引号、省略号、破折号
- 不以 "-" 开头

打分（同一个词有多条候选时留分最高的）：
- 长度接近 40 字符最好（有语境又不啰嗦）
- 目标词出现在句子中部比开头好（开头往往缺上下文）
- 词数 5–10 最好

为什么按「原形」索引
--------------------
学习者查的是词，不是某个变形。`субботу` 的例句放在 `суббота` 下面，
查任何格都能看到同一句话。

许可：字幕语料 Apache-2.0 + Leipzig CC BY 4.0，见 README。
"""
import glob
import os
import re
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
TMP = os.environ.get("TEMP", "/tmp")
SUBS_ZIP = os.path.join(TMP, "subtitles_ru.txt.zip")
LEIPZIG = os.path.join(TMP, "leipzig")
WORDS = os.path.join(HERE, "ru-words.txt")
OUT = os.path.join(HERE, "ru-examples.tsv")

SPLIT = re.compile(r"[^А-Яа-яЁё\-]+")
BAD = re.compile(r"[A-Za-z0-9«»\"“”…—–]")
SENT_END = re.compile(r"[.!?]")
PROFANITY = re.compile(
    r"ху[йяе]|пизд|бля|еба[тлн]|ебёт|сука|мудак|мудил|залуп|говно|жоп|срак")
TOP_WORDS = 40000
MIN_LEN, MAX_LEN = 18, 75


def iter_lines():
    """yield (句子, 是否书面语)"""
    if os.path.exists(SUBS_ZIP):
        with zipfile.ZipFile(SUBS_ZIP) as z:
            name = z.infolist()[0].filename
            with z.open(name) as raw:
                for line in raw:
                    yield line.decode("utf-8", "ignore"), False
    for path in sorted(glob.glob(os.path.join(LEIPZIG, "*-sentences.txt"))):
        with open(path, encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                parts = line.rstrip("\n").split("\t")
                if len(parts) >= 2:
                    yield parts[-1], True


def clean(text):
    t = re.sub(r"\s+", " ", text.strip().strip("-").strip())
    if not (MIN_LEN <= len(t) <= MAX_LEN):
        return ""
    if BAD.search(t):
        return ""
    if len(SENT_END.findall(t)) != 1:
        return ""                       # 只要单句
    if len(t.split()) < 4:
        return ""
    if PROFANITY.search(t):
        return ""
    return t


def score(sentence, pos, total, written=False):
    """越小越好。"""
    n = len(sentence)
    words = len(sentence.split())
    rel = pos / max(1, total)
    s = abs(n - 40) * 1.0
    s += abs(words - 7) * 2.0
    s += abs(rel - 0.45) * 30
    if written:                         # 新闻/维基的句子更完整
        s -= 12
    if sentence[:1].isupper():          # 字幕里很多小写开头 = 半句话
        s -= 6
    extra = sentence.count(",") - 2
    if extra > 0:                       # 逗号太多说明是拼起来的碎句
        s += extra * 8
    return s


def main():
    top = []
    seen = set()
    with open(WORDS, encoding="utf-8") as fh:
        for line in fh:
            w = line.strip().lower()
            if w and w not in seen:
                seen.add(w)
                top.append(w)
            if len(top) >= TOP_WORDS:
                break
    top_set = set(top)
    print(f"目标词: {len(top)}")

    import pymorphy3
    morph = pymorphy3.MorphAnalyzer()
    lemma_cache = {}

    def lemma_of(w):
        if w in lemma_cache:
            return lemma_cache[w]
        try:
            lem = morph.parse(w)[0].normal_form
        except Exception:
            lem = w
        lemma_cache[w] = lem
        return lem

    best = {}          # lemma -> (score, sentence)
    lines = 0
    for text, written in iter_lines():
        lines += 1
        s = clean(text)
        if not s:
            continue
        toks = [x.lower() for x in SPLIT.split(s) if x]
        if not toks:
            continue
        for i, tk in enumerate(toks):
            if tk not in top_set:
                continue
            lem = lemma_of(tk)
            sc = score(s, i, len(toks), written)
            cur = best.get(lem)
            if cur is None or sc < cur[0]:
                best[lem] = (sc, s)

    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        for lem, (sc, s) in best.items():
            fh.write(f"{lem}\t{s}\n")
    print(f"扫描 {lines} 行，覆盖 {len(best)} 个原形  "
          f"{os.path.getsize(OUT)/1024/1024:.2f} MB")

    for w in ("суббота", "говорить", "работа", "хотеть", "нравиться",
              "думать", "время", "человек"):
        it = best.get(w)
        print(f"  {w:11} -> {it[1] if it else '(无)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
