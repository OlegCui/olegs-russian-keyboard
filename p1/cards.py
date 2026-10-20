# -*- coding: utf-8 -*-
"""
深度卡：一个词的「释义 + 支配结构 + 搭配 + 辨析 + 常见错误」。

数据格式（data/ru-cards.tsv，制表符分隔，字段可空）
--------------------------------------------------
原形 | 词性 | 释义 | 体 | 支配结构 | 搭配 | 近义词辨析 | 常见错误

设计原则
--------
- 固定字段，不让模型自由排版：可疑字段能单独删掉、单独重生成
- 每条都短，能在 Ctrl+L 窗口里一屏看完
- 机器生成的条目标 src=m，人工/校验过的标 src=h
"""
import os

FIELDS = ("lemma", "pos", "gloss", "aspect", "pattern", "colloc",
          "compare", "errors", "src")


class Cards:
    def __init__(self, path=None):
        self.table = {}
        self.path = path
        self._load(path)

    def _load(self, path):
        try:
            if not path or not os.path.exists(path):
                return
            with open(path, encoding="utf-8-sig") as fh:
                for line in fh:
                    line = line.rstrip("\n")
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split("\t")
                    if len(parts) < 3:
                        continue
                    rec = {k: (parts[i] if i < len(parts) else "")
                           for i, k in enumerate(FIELDS)}
                    key = rec["lemma"].strip().lower()
                    if key:
                        self.table[key] = rec
        except Exception:
            self.table = {}

    def get(self, word, morph=None):
        """按原形查；查不到就用 pymorphy 折算原形再查。"""
        w = (word or "").strip().lower()
        if not w:
            return None
        hit = self.table.get(w)
        if hit:
            return hit
        if morph is not None:
            try:
                lem = morph.parse(w)[0].normal_form
                return self.table.get(lem)
            except Exception:
                return None
        return None

    def __len__(self):
        return len(self.table)


def format_card(rec):
    """把一条记录排成给人看的文本（纯文本，等宽字体下对齐）。"""
    if not rec:
        return ""
    out = []
    head = rec.get("lemma", "")
    bits = [x for x in [rec.get("pos"), rec.get("aspect")] if x]
    if bits:
        head += "  " + " · ".join(bits)
    out.append(head)
    out.append("─" * 40)

    if rec.get("gloss"):
        out.append("释义    " + rec["gloss"])
    if rec.get("pattern"):
        out.append("结构    " + rec["pattern"])
    if rec.get("colloc"):
        out.append("搭配    " + rec["colloc"].replace("；", "  ·  "))
    if rec.get("compare"):
        out.append("辨析    " + rec["compare"])
    if rec.get("errors"):
        out.append("错误    " + rec["errors"].replace("；", "\n        "))
    if (rec.get("src") or "").strip().lower() == "m":
        out.append("")
        out.append("（这条是机器生成的，可能有错，欢迎反馈）")
    return "\n".join(out)
