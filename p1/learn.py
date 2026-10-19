# -*- coding: utf-8 -*-
"""
个人词频记忆：像系统输入法一样，把你常用/选过的词往前排。

记录两类信号：
  1. 你从候选条里**选**了某个词   → 权重 2（强信号：你认可它）
  2. 你自己**打完**一个词并按空格  → 权重 1（弱信号：至少你会用它）

排序规则（越靠前）：
  选过的次数多  >  最近用过  >  词表里的原始词频

数据存在 user_freq.json，纯本地，不上传。
"""
import json
import os
import time

try:
    from paths import FREQ_FILE as DEFAULT_PATH
except Exception:
    DEFAULT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "user_freq.json")
MAX_ENTRIES = 5000


class UserFreq:
    def __init__(self, path=DEFAULT_PATH):
        self.path = path
        self.data = {}          # word -> [count, last_ts]
        self._dirty = False
        self._last_save = 0.0
        self._load()

    # ---------- 持久化 ----------
    def _load(self):
        try:
            if os.path.exists(self.path):
                with open(self.path, encoding="utf-8-sig") as fh:
                    raw = json.load(fh)
                for w, v in (raw.get("words") or {}).items():
                    if isinstance(v, list) and len(v) >= 2:
                        self.data[w] = [float(v[0]), float(v[1])]
                    elif isinstance(v, (int, float)):
                        self.data[w] = [float(v), 0.0]
        except Exception as e:
            print(f"[learn] 读取失败（忽略）: {e}", file=__import__("sys").stderr)

    def save(self, force=False):
        if not self._dirty and not force:
            return
        now = time.time()
        if not force and now - self._last_save < 5:
            return
        try:
            if len(self.data) > MAX_ENTRIES:
                # 按次数+时间淘汰最弱的一批
                keep = sorted(self.data.items(),
                              key=lambda kv: (kv[1][0], kv[1][1]),
                              reverse=True)[:MAX_ENTRIES]
                self.data = dict(keep)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump({"version": 1, "words": self.data}, fh,
                          ensure_ascii=False)
            os.replace(tmp, self.path)
            self._dirty = False
            self._last_save = now
        except Exception as e:
            print(f"[learn] 保存失败: {e}", file=__import__("sys").stderr)

    # ---------- 记录 ----------
    def add(self, word, weight=1):
        w = (word or "").strip().lower()
        if len(w) < 2:
            return
        cur = self.data.get(w) or [0.0, 0.0]
        cur[0] += weight
        cur[1] = time.time()
        self.data[w] = cur
        self._dirty = True
        self.save()

    # ---------- 排序 ----------
    def count(self, word):
        v = self.data.get((word or "").lower())
        return v[0] if v else 0.0

    def last(self, word):
        v = self.data.get((word or "").lower())
        return v[1] if v else 0.0

    def sort_key(self, word, base_rank):
        """越小越靠前。"""
        w = (word or "").lower()
        return (-self.count(w), -self.last(w), base_rank)

    def stats(self):
        return {"entries": len(self.data),
                "total": int(sum(v[0] for v in self.data.values()))}


def selftest():
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    import tempfile
    p = os.path.join(tempfile.gettempdir(), "_ufreq_test.json")
    if os.path.exists(p):
        os.remove(p)

    uf = UserFreq(p)
    print("初始:", uf.stats())
    uf.add("привет", 2)
    uf.add("привет", 2)
    uf.add("приветик", 1)
    uf.save(force=True)

    uf2 = UserFreq(p)
    print("重载:", uf2.stats())
    print("привет 次数:", uf2.count("привет"))

    words = ["привести", "привет", "привыкнуть", "приветик"]
    base = {w: i for i, w in enumerate(words)}
    ranked = sorted(words, key=lambda w: uf2.sort_key(w, base[w]))
    print("排序前(按原词频):", words)
    print("排序后(个人记忆):", ranked)
    assert ranked[0] == "привет", ranked
    print("PASS")
    os.remove(p)


if __name__ == "__main__":
    selftest()
