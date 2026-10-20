# -*- coding: utf-8 -*-
"""
构建补全用的俄语词频表。

输入
----
1. OpenSubtitles 2018 词频表（口语/对白，真正的日常语料）
   https://github.com/hermitdave/FrequencyWords  content/2018/ru/ru_full.txt
   许可：内容 CC-BY-SA-4.0，原语料来自 OPUS OpenSubtitles2018
2. 旧的 Leeds 语料词表（书面语，作补充覆盖）
   data/russian-words/100000-russian-words.txt
   许可：CC BY 2.5

输出
----
data/ru-words.txt   每行一个词，**按词频降序**（行号即排名）

为什么这么干
------------
旧表是书面语，"зав" 的第一候选是 зависеть（文书用词）。
字幕语料下 "зав" -> завтра、"прив" -> привет，才符合日常输入。
但字幕也有 OCR 垃圾（декючр、重复字母），所以做了两道过滤：
形态学词典认不出的一律丢掉。
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_SUBS = os.path.join(os.environ.get("TEMP", "/tmp"), "ru_full.txt")
SRC_OLD = os.path.join(HERE, "russian-words", "100000-russian-words.txt")
OUT = os.path.join(HERE, "ru-words.txt")

CYR = re.compile(r"^[а-яё\-]{2,24}$")
VOWELS = set("аеёиоуыэюя")
KEEP_SUBS = 120000      # 字幕词取前多少
KEEP_OLD = 40000        # 旧词表补充多少


def repeated(w):
    """同一个字母连续 3 次以上（ааа、нееет 这类字幕噪声）。"""
    return re.search(r"(.)\1\1", w) is not None


def has_vowel(w):
    return any(c in VOWELS for c in w)


def main():
    if not os.path.exists(SRC_SUBS):
        print(f"缺少字幕词频表: {SRC_SUBS}", file=sys.stderr)
        return 1

    import pymorphy3
    morph = pymorphy3.MorphAnalyzer()

    known_cache = {}

    def known(w):
        if w in known_cache:
            return known_cache[w]
        ok = False
        try:
            ps = morph.parse(w)
            ok = bool(ps) and bool(getattr(ps[0], "is_known", False))
        except Exception:
            ok = False
        known_cache[w] = ok
        return ok

    rows = []
    with open(SRC_SUBS, encoding="utf-8") as fh:
        for line in fh:
            parts = line.split()
            if len(parts) != 2:
                continue
            w = parts[0].lower()
            if not CYR.match(w) or repeated(w) or not has_vowel(w):
                continue
            try:
                c = int(parts[1])
            except ValueError:
                continue
            rows.append((w, c))

    print(f"字幕原始可用词: {len(rows)}")

    out, seen = [], set()
    dropped_garbage = 0
    for w, _c in rows:
        if w in seen:
            continue
        if not known(w):
            dropped_garbage += 1
            continue
        seen.add(w)
        out.append(w)
        if len(out) >= KEEP_SUBS:
            break
    print(f"字幕保留: {len(out)}  丢弃(形态学不认): {dropped_garbage}")

    added_old = 0
    if os.path.exists(SRC_OLD):
        with open(SRC_OLD, encoding="utf-8") as fh:
            for line in fh:
                w = line.strip().lower()
                if not CYR.match(w) or w in seen:
                    continue
                seen.add(w)
                out.append(w)
                added_old += 1
                if added_old >= KEEP_OLD:
                    break
    print(f"旧表补充: {added_old}")

    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(out) + "\n")
    print(f"写出: {OUT}  共 {len(out)} 词  "
          f"{os.path.getsize(OUT)/1024/1024:.2f} MB")

    # 抽查
    for p in ("зав", "прив", "суббот", "помо", "хоч", "друг"):
        for i, w in enumerate(out):
            if w.startswith(p):
                print(f"  {p:8} -> {w} (#{i})")
                break
    return 0


if __name__ == "__main__":
    sys.exit(main())
