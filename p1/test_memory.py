# -*- coding: utf-8 -*-
"""记忆功能集成测试：选过的词是否被提前，且能持久化。"""
import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "D:/Tools/俄语输入法/p1")
import engine as E
import learn


def main():
    tmp = os.path.join(tempfile.gettempdir(), "_freq_integration.json")
    if os.path.exists(tmp):
        os.remove(tmp)

    eng = E.Engine()
    eng._uf = learn.UserFreq(tmp)

    def show(tag):
        items = eng.complete("прив", 6)
        print(f"  {tag}: " + ", ".join(f"{i['form']}[{i['label']}]"
                                       for i in items))
        return [i["form"] for i in items]

    print("记忆功能集成测试")
    print("-" * 60)
    before = show("未学习")

    print("\n  模拟：用户连点两次 'привет'")
    eng._uf.add("привет", 2)
    eng._uf.add("привет", 2)
    eng._uf.save(force=True)
    after = show("学习后")

    ok1 = after and after[0] == "привет"
    print(f"\n  привет 排到第一位: {'PASS' if ok1 else 'FAIL'}")

    # 持久化
    uf2 = learn.UserFreq(tmp)
    ok2 = uf2.count("привет") == 4
    print(f"  重启后仍在（次数={uf2.count('привет')}）: "
          f"{'PASS' if ok2 else 'FAIL'}")

    # 另一个词也能学到
    eng._uf.add("привыкнуть", 5)
    show("再选 привыкнуть 5 次")

    # 不影响其他前缀
    other = [i["form"] for i in eng.complete("пожа", 4)]
    ok3 = "привет" not in other
    print(f"  不影响别的词（пожа）: {other}  {'PASS' if ok3 else 'FAIL'}")

    os.remove(tmp)
    ok = ok1 and ok2 and ok3
    print("\n" + ("全部通过" if ok else "有失败项"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
