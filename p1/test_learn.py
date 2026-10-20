# -*- coding: utf-8 -*-
"""
学习功能的测试：句法支配、例句、间隔重复、Anki 导出、查词历史。

不注入任何按键，也不碰用户真实数据（全部用临时目录）。
"""
import os
import sys
import tempfile
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"D:\Tools\俄语输入法\p1")

import engine as E
import gov
import paths
from examples import Examples
from wordbook import WordBook


def main():
    ok_all = True

    def check(name, got, want):
        nonlocal ok_all
        ok = got == want
        ok_all = ok_all and ok
        print(f"  {name:30} 得到={str(got)[:34]:36} {'PASS' if ok else 'FAIL'}")

    e = E.Engine()

    print("\n--- 句法：动词支配 ---")
    bad = [("помочь", "тебя", "тебе"),
           ("интересоваться", "музыку", "музыкой"),
           ("пользоваться", "телефон", "телефоном")]
    for verb, noun, expect in bad:
        r = gov.check(e.morph, verb, noun)
        check(f"{verb} {noun} 应提示", (r or {}).get("fix"), expect)

    good = [("помочь", "тебе"), ("бояться", "собак"), ("ждать", "автобуса"),
            ("любить", "его"), ("интересоваться", "музыкой")]
    for verb, noun in good:
        r = gov.check(e.morph, verb, noun)
        check(f"{verb} {noun} 不该提示", r, None)

    print("\n--- 例句 ---")
    ex = Examples(getattr(paths, "EXAMPLES_FILE", None))
    print(f"  例句库条数: {len(ex)}")
    ok_all = ok_all and len(ex) > 1000
    sent = ex.get("работу", e.morph)
    check("按变形查到原形例句", bool(sent) and "работ" in sent, True)
    check("不存在的词返回空", ex.get("эпппп", e.morph), "")

    print("\n--- 生词本：间隔重复 ---")
    d = tempfile.mkdtemp()
    wb = WordBook(os.path.join(d, "wb.json"), os.path.join(d, "wb.md"))
    wb.add("суббота", lemma="суббота", pos="名词", case="主格")
    wb.add("помогать", lemma="помогать", pos="动词")
    check("两个词立刻到期", len(wb.due_words()), 2)

    wb.review("суббота", 2)            # 记得
    it = [w for w in wb.words if w["word"] == "суббота"][0]
    check("记得 → 间隔 2 天", it["interval"], 2.0)
    check("记得后不再到期", len(wb.due_words()), 1)

    wb.review("помогать", 0)           # 忘了
    it2 = [w for w in wb.words if w["word"] == "помогать"][0]
    check("忘了 → 间隔 1 天", it2["interval"], 1.0)
    check("忘了 → lapses+1", it2["lapses"], 1)
    check("统计", wb.review_stats()["total"], 2)

    # 到期判断：把 due 拨到过去
    it["due"] = time.time() - 10
    due_now = [w["word"] for w in wb.due_words()]
    check("到期后重新出现", due_now, ["суббота"])
    check("没到期的仍在等", "помогать" in due_now, False)

    print("\n--- Anki 导出 ---")
    p = wb.export_anki(os.path.join(d, "anki.tsv"))
    raw = open(p, encoding="utf-8-sig").read()
    check("有表头", "#separator:tab" in raw, True)
    check("词都在里面", ("суббота" in raw and "помогать" in raw), True)
    check("制表符分隔", raw.count("\t") >= 2, True)

    print("\n--- 持久化 ---")
    wb2 = WordBook(os.path.join(d, "wb.json"), os.path.join(d, "wb.md"))
    check("重新读入词数", len(wb2), 2)
    check("SRS 字段保留", wb2.words[0].get("interval"), 2.0)
    old = [{"word": "старый", "lemma": "старый", "added": time.time()}]
    import json
    with open(os.path.join(d, "old.json"), "w", encoding="utf-8") as fh:
        json.dump({"version": 1, "words": old}, fh, ensure_ascii=False)
    wb3 = WordBook(os.path.join(d, "old.json"), os.path.join(d, "old.md"))
    check("老数据自动补 SRS 字段", "due" in wb3.words[0], True)

    print("\n" + ("全部通过" if ok_all else "有失败项"))
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
