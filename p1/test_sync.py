# -*- coding: utf-8 -*-
"""
生词本同步测试：合并规则、冲突副本、往返读写。

不碰真实数据，全部用临时目录。
"""
import json
import os
import sys
import tempfile
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"D:\Tools\俄语输入法\p1")

import sync as S
import wordbook as W


def main():
    ok_all = True

    def check(name, got, want):
        nonlocal ok_all
        ok = got == want
        ok_all = ok_all and ok
        print(f"  {name:30} 得到={str(got)[:34]:36} {'PASS' if ok else 'FAIL'}")

    now = time.time()

    print("\n--- 合并规则 ---")
    local = [
        {"word": "дом", "added": 1, "last": now},
        {"word": "суббота", "added": 2, "last": 100},
    ]
    remote = [
        {"word": "суббота", "added": 2, "last": now + 10, "interval": 9},
        {"word": "работа", "added": 3, "last": now},
    ]
    merged, added = S.merge(local, remote)
    got = {w["word"]: w for w in merged}
    check("云端较新的覆盖本地", got["суббота"].get("interval"), 9)
    check("只在本地的词保留", "дом" in got, True)
    check("只在云端的词加进来", "работа" in got, True)
    check("新增计数", added, 1)

    # 反向：本地更新，云端较旧
    merged2, added2 = S.merge(
        [{"word": "дом", "added": 1, "last": now, "interval": 4}],
        [{"word": "дом", "added": 1, "last": 50, "interval": 1}])
    check("本地较新时不回退", merged2[0].get("interval"), 4)
    check("没有新增", added2, 0)

    print("\n--- 冲突副本 ---")
    d = tempfile.mkdtemp()
    S.write_words(os.path.join(d, "wordbook-sync.json"),
                  [{"word": "дом", "added": 1, "last": now}])
    S.write_words(os.path.join(d, "wordbook-sync (1).json"),
                  [{"word": "дверь", "added": 2, "last": now}])
    words, added, nfiles = S.read_folder(d)
    names = {w["word"] for w in words}
    check("读到 2 个文件", nfiles, 2)
    check("副本里的词也合并", "дверь" in names, True)

    print("\n--- 往返读写 ---")
    p = os.path.join(d, "round.json")
    S.write_words(p, [{"word": "тест", "added": 5, "last": now}])
    back = S.read_words(p)
    check("读回条数", len(back), 1)
    check("读回内容", back[0]["word"], "тест")

    # 坏文件不该炸
    bad = os.path.join(d, "bad.json")
    open(bad, "w", encoding="utf-8").write("{不是JSON")
    check("坏文件返回空", S.read_words(bad), [])

    print("\n--- WordBook 接入 ---")
    cloud = os.path.join(tempfile.mkdtemp(), "OneDrive")
    os.makedirs(cloud)
    wb = W.WordBook(os.path.join(d, "wb.json"), os.path.join(d, "wb.md"))
    wb.attach_sync(cloud)
    wb.add("суббота", lemma="суббота")
    wb.sync_push_now()
    check("推送后有主文件", os.path.exists(S.WordbookSync(cloud).path), True)

    S.write_words(S.WordbookSync(cloud).path, [
        {"word": "работа", "added": 9, "last": now}])
    gained = wb.sync_pull()
    check("拉取新增 1 个", gained, 1)
    check("本地共 2 个", len(wb), 2)

    print("\n" + ("全部通过" if ok_all else "有失败项"))
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
