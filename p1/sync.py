# -*- coding: utf-8 -*-
"""
生词本同步：只同步生词本，带按词合并。

为什么不用 OneDrive API
-----------------------
把文件放进 OneDrive（或任何同步文件夹）就够了，接 API 要 OAuth、应用注册、
token 刷新，工作量翻三倍，效果一样。

合并规则
--------
同一个词在两台机器都改过时，取 `last`（最近一次改动时间）更新的那条。
两边独有的词都保留——因为每条记录本来就带时间戳，可以做到一条都不丢。

OneDrive 的冲突副本
-------------------
两台机器同时写会生成 `wordbook-sync (1).json`。这些副本也会被读进来参与
合并，否则另一台的改动就静默消失了。
"""
import glob
import json
import os
import time

FILE_NAME = "wordbook-sync.json"


def _key(it):
    return (it.get("word") or "").strip().lower()


def _stamp(it):
    """一条记录的"最近改动时间"。老数据可能没有 last，退到 added。"""
    for k in ("last", "added"):
        v = it.get(k)
        if isinstance(v, (int, float)) and v > 0:
            return float(v)
    return 0.0


def read_words(path):
    """读一个文件里的词条列表；格式不对就当空的。"""
    try:
        with open(path, encoding="utf-8-sig") as fh:
            data = json.load(fh)
    except Exception:
        return []
    if isinstance(data, dict):
        data = data.get("words") or []
    if not isinstance(data, list):
        return []
    return [w for w in data if isinstance(w, dict) and _key(w)]


def merge(local, remote):
    """按词合并两份词表，同词取 last 更新的。返回 (合并结果, 新增数)。"""
    out = {}
    for it in local:
        out[_key(it)] = dict(it)
    added = 0
    for it in remote:
        k = _key(it)
        if not k:
            continue
        cur = out.get(k)
        if cur is None:
            out[k] = dict(it)
            added += 1
        elif _stamp(it) > _stamp(cur):
            out[k] = dict(it)
    # 保持稳定顺序：先按加入时间，再按词
    merged = sorted(out.values(), key=lambda w: (w.get("added") or 0, _key(w)))
    return merged, added


def write_words(path, words):
    """原子写入：先写临时文件再替换，避免 OneDrive 抓到半个文件。"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"version": 1, "words": words}, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def sync_files(folder):
    """目录里所有 `wordbook-sync*.json`（含 OneDrive 的冲突副本）。"""
    if not folder or not os.path.isdir(folder):
        return []
    pattern = os.path.join(folder, "wordbook-sync*.json")
    return sorted(glob.glob(pattern))


def read_folder(folder):
    """目录里所有副本合并后的结果。返回 (词表, 新增数, 读到的文件数)。"""
    files = sync_files(folder)
    total, added, nfiles = [], 0, 0
    for f in files:
        words = read_words(f)
        if not words:
            continue
        nfiles += 1
        total, a = merge(total, words)
        added += a
    return total, added, nfiles


class WordbookSync:
    """给 WordBook 用的同步器。"""

    def __init__(self, folder, log=None):
        self.folder = folder
        self.log = log or (lambda msg: None)
        self.last_added = 0
        self.last_at = 0.0

    @property
    def path(self):
        return os.path.join(self.folder, FILE_NAME)

    def available(self):
        return bool(self.folder) and os.path.isdir(self.folder)

    def push(self, words):
        """把本地词表写到同步目录（覆盖主文件；副本不动）。"""
        if not self.available():
            return False
        try:
            write_words(self.path, words)
            return True
        except Exception as e:
            self.log(f"[sync] 写入失败: {e}")
            return False

    def pull_and_merge(self, local_words):
        """读同步目录（含冲突副本）并与本地合并。

        返回 (合并后的词表, 从云端新增的词数)。
        """
        if not self.available():
            return local_words, 0
        remote, _added, nfiles = read_folder(self.folder)
        if not remote:
            self.log("[sync] 同步目录里还没有生词本")
            return local_words, 0
        merged, added = merge(local_words, remote)
        self.last_added = added
        self.last_at = time.time()
        self.log(f"[sync] 读 {nfiles} 个文件，云端 {len(remote)} 词，"
                 f"合并后 {len(merged)} 词（新增 {added}）")
        return merged, added
