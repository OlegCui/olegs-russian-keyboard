# -*- coding: utf-8 -*-
"""
高频词索引：补全 + 纠错

数据源：data/russian-words/100000-russian-words.txt
  - 已确认是**按词频降序**排列的（и, в, не, на, я, что, быть, с, он …）
  - 但含脏数据：混拉丁字母的词（хочy）、英文（quot/contest）、拼写错误

所以这里做三件事：
  1. 只保留纯西里尔词（含 ё、连字符），长度 ≥2
  2. 保持原顺序 = 保持词频顺序
  3. 补全时按词频扫描取前 N 个（而不是按字母序，否则 прив → привал，而不是 привет）
"""
import os
import re
import sys
import time

CYR = re.compile(r"^[а-яё\-]+$")
LETTERS = "абвгдеёжзийклмнопрстуфхцчшщъыьэюя"

try:
    from paths import WORDS_FILE as DEFAULT_PATH
except Exception:
    DEFAULT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "data", "russian-words",
                                "100000-russian-words.txt")


class WordIndex:
    def __init__(self, path=DEFAULT_PATH, max_words=None):
        self.words = []
        seen = set()
        kept = dropped = 0
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                w = line.strip().lower()
                if len(w) < 2 or not CYR.match(w) or w in seen:
                    dropped += 1
                    continue
                seen.add(w)
                self.words.append(w)
                kept += 1
                if max_words and kept >= max_words:
                    break
        self.rank = {w: i for i, w in enumerate(self.words)}
        self.cache = {}
        self.stats = {"kept": kept, "dropped": dropped}

    # ---------- 补全 ----------
    def complete(self, prefix, limit=6):
        p = prefix.lower()
        if len(p) < 2:
            return []
        if p in self.cache:
            return self.cache[p][:limit]
        out = []
        for w in self.words:                 # 按词频顺序扫
            if w != p and w.startswith(p):
                out.append(w)
                if len(out) >= 12:           # 多取一点，给缓存留余量
                    break
        self.cache[p] = out
        return out[:limit]

    # ---------- 纠错 ----------
    def correct(self, word, limit=2):
        w = word.lower()
        if w in self.rank or len(w) < 2:
            return []
        cands = set()
        n = len(w)
        for i in range(n):                                  # 删除一个
            cands.add(w[:i] + w[i + 1:])
        for i in range(n - 1):                              # 相邻互换
            cands.add(w[:i] + w[i + 1] + w[i] + w[i + 2:])
        for i in range(n + 1):                              # 插入/替换
            for c in LETTERS:
                cands.add(w[:i] + c + w[i:])
                if i < n:
                    cands.add(w[:i] + c + w[i + 1:])
        hits = [c for c in cands if c in self.rank]
        hits.sort(key=lambda x: self.rank[x])               # 更常用的排前面
        return hits[:limit]

    def is_word(self, w):
        return w.lower() in self.rank


def selftest():
    t0 = time.perf_counter()
    idx = WordIndex()
    load_ms = (time.perf_counter() - t0) * 1000
    print(f"加载 {idx.stats['kept']} 词，丢弃 {idx.stats['dropped']} 行，"
          f"耗时 {load_ms:.0f} ms")
    print(f"最靠前 10 个: {idx.words[:10]}")

    print("\n--- 补全（按词频，不是按字母序）---")
    for pre in ["прив", "дру", "хоч", "помо", "здрав", "пожа"]:
        t = time.perf_counter()
        got = idx.complete(pre, 6)
        dt = (time.perf_counter() - t) * 1000
        print(f"  {pre:7} -> {got}   ({dt:.1f} ms)")

    print("\n--- 纠错（编辑距离 1）---")
    for w in ["привет", "привт", "другу", "спосибо", "здравствуй"]:
        t = time.perf_counter()
        got = idx.correct(w, 3)
        dt = (time.perf_counter() - t) * 1000
        flag = "已在词表" if idx.is_word(w) else "不在词表"
        print(f"  {w:12} [{flag}] -> {got}   ({dt:.1f} ms)")

    print("\n--- 缓存后性能 ---")
    idx.complete("прив")
    t = time.perf_counter()
    for _ in range(1000):
        idx.complete("прив")
    print(f"  1000 次命中缓存耗时 {(time.perf_counter() - t) * 1000:.1f} ms")

    print("\n--- 冷启动最坏情况 ---")
    t = time.perf_counter()
    idx.complete("абракадабр")
    print(f"  未命中缓存的一次扫描 {(time.perf_counter() - t) * 1000:.1f} ms")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    selftest()
