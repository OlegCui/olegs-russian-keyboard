# -*- coding: utf-8 -*-
"""
例句库：给一个词找一条真实句子。

数据由 data/build_examples.py 从字幕语料生成，按**原形**索引。
查任何变形（субботу / субботой）都会落到 суббота 那条句子。
"""
import os


class Examples:
    def __init__(self, path=None, zh_path=None):
        self.table = {}
        self.zh = {}
        self.path = path
        self._load(path)
        self._load_zh(zh_path)

    def _load(self, path):
        try:
            if not path or not os.path.exists(path):
                return
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.rstrip("\n")
                    if not line:
                        continue
                    word, _, sent = line.partition("\t")
                    if word and sent:
                        self.table[word.lower()] = sent
        except Exception:
            self.table = {}

    def _load_zh(self, path):
        """例句的中文翻译：原形 \t 俄语 \t 中文。"""
        try:
            if not path or not os.path.exists(path):
                return
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    parts = line.rstrip("\n").split("\t")
                    if len(parts) >= 3 and parts[1] and parts[2]:
                        self.zh[parts[1]] = parts[2]
        except Exception:
            self.zh = {}

    def get_zh(self, word, morph=None):
        """取例句的中文翻译（跟 get 同一条句子）。"""
        sent = self.get(word, morph)
        return self.zh.get(sent, "")

    def get(self, word, morph=None):
        """先按原样查，查不到再用 pymorphy 取原形查。"""
        w = (word or "").strip().lower()
        if not w:
            return ""
        hit = self.table.get(w)
        if hit:
            return hit
        if morph is not None:
            try:
                lem = morph.parse(w)[0].normal_form
                return self.table.get(lem, "")
            except Exception:
                return ""
        return ""

    def __len__(self):
        return len(self.table)
