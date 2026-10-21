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
    # 纠错只在"常见词"里找。字幕语料里混进大量转写噪声
    # （секонд 排 139839），不设门槛就会把它们当答案。
    COMMON_RANK = 30000
    JUNK_RANK = 60000

    def _common_words(self):
        """常见词，按首字母分桶。

        不建索引的话每次纠错要扫 3 万个词（实测 16.5 ms），
        每敲一个键都卡一下。分桶后只剩几百个。
        """
        if getattr(self, "_common", None) is None:
            buckets = {}
            for w in self.words:
                if self.rank.get(w, 10 ** 9) < self.COMMON_RANK:
                    buckets.setdefault(w[:1], []).append(w)
            self._common = buckets
        return self._common

    @staticmethod
    def _within(a, b, limit=2):
        """带内编辑距离（banded Levenshtein）。

        只算对角线附近 limit 格，配合早停，比标准 DP 快 3-4 倍。
        """
        la, lb = len(a), len(b)
        if abs(la - lb) > limit:
            return limit + 1
        big = limit + 1
        prev = [big] * (lb + 1)
        for j in range(0, min(lb, limit) + 1):
            prev[j] = j
        for i in range(1, la + 1):
            cur = [big] * (lb + 1)
            lo = max(1, i - limit)
            hi = min(lb, i + limit)
            if lo == 1:
                cur[0] = i
            best = big
            for j in range(lo, hi + 1):
                cost = 0 if a[i - 1] == b[j - 1] else 1
                v = prev[j - 1] + cost
                if prev[j] + 1 < v:
                    v = prev[j] + 1
                if cur[j - 1] + 1 < v:
                    v = cur[j - 1] + 1
                cur[j] = v
                if v < best:
                    best = v
            if best > limit:
                return big
            prev = cur
        return prev[lb]

    def correct_near(self, word, limit=3, max_dist=2):
        """在常见词里按编辑距离找，兼顾词频。

        只做距离 1 是不够的：`сейконд` 到 `секунд` 差 3 步，
        但用户明明就是想打这个。
        """
        w = word.lower()
        # 首字母几乎不会错；桶内按词频取前 500 个就够了——
        # 用户想打的总是常用词，罕见的错法不值得每键扫一遍。
        common = self._common_words().get(w[:1], [])[:500]
        if not common:
            return []
        scored = []
        for cand in common:
            if abs(len(cand) - len(w)) > max_dist:
                continue
            dist = self._within(w, cand, max_dist)
            if dist <= max_dist:
                scored.append((dist, self.rank.get(cand, 10 ** 9), cand))
        scored.sort(key=lambda x: (x[0], x[1]))
        return [c for _, _, c in scored[:limit]]

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
        hits = [c for c in cands
                if c in self.rank and self.rank[c] < self.JUNK_RANK]
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
