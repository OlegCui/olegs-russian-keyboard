# -*- coding: utf-8 -*-
"""
下一个词预测（bigram）。

模型文件 data/ru-bigram.tsv 由 data/build_bigram.py 生成：
    前一个词<TAB>后词:次数 后词:次数 ...

只做"同一个词后面的常见搭配"，不做句子级语言模型：
- 常驻内存很小（几万个前词，每个最多 6 个后词）
- 查询是字典命中，微秒级
- 离线、不联网
"""
import os

_CYRILLIC_OK = True


class Bigram:
    def __init__(self, path=None, max_followers=6):
        self.table = {}
        self.path = path
        self.max_followers = max_followers
        self.loaded = False
        self._load(path)

    def _load(self, path):
        try:
            if not path or not os.path.exists(path):
                return
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.rstrip("\n")
                    if not line:
                        continue
                    head, _, rest = line.partition("\t")
                    if not rest:
                        continue
                    rows = []
                    for item in rest.split(" "):
                        word, _, cnt = item.rpartition(":")
                        if not word:
                            continue
                        try:
                            rows.append((word, int(cnt)))
                        except ValueError:
                            continue
                    if rows:
                        self.table[head] = rows[:self.max_followers]
            self.loaded = bool(self.table)
        except Exception:
            self.table = {}
            self.loaded = False

    def predict(self, word, limit=6):
        """给定前一个词，返回后面最可能出现的词。"""
        if not word:
            return []
        rows = self.table.get(word.strip().lower())
        if not rows:
            return []
        return [w for w, _ in rows[:limit]]

    def __len__(self):
        return len(self.table)
