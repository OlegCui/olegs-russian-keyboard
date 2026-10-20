# -*- coding: utf-8 -*-
"""
补全模式自测（零注入、零副作用）

规则：有补全 → 先帮拼写；没有补全（词已写完）→ 自动切变格教学。
Tab：两种视图都有时切换；只有一种时确认当前候选。
"""
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "D:/Tools/俄语输入法/p1")
import app as app_mod

VK_TAB = 0x09
injected = []


def main():
    app = app_mod.App(require_lang=None, verbose=False)

    # 用临时记忆库，别污染真实使用数据
    import os
    import tempfile
    import learn
    app.eng._uf = learn.UserFreq(
        os.path.join(tempfile.gettempdir(), "_freq_test_complete.json"))

    # 打桩：任何"真实注入"都换成记录，绝不碰其他窗口
    def fake_replace(n, text):
        injected.append((n, text))
        return True

    app_mod.input_sim.replace_tail = fake_replace
    app_mod.input_sim.send_text = lambda text: (injected.append(("space", text)), True)[1]

    app.start()
    app.root.after(40, app.pump)

    def pump(n=20):
        for _ in range(n):
            app.root.update()
            time.sleep(0.02)

    ok_all = True

    def check(text, expect_mode, expect_has_comp=None):
        nonlocal ok_all
        app._update(text)
        pump()
        mode = app._mode
        forms = [i["form"] for i in app.bar.items]
        variants = sorted(app._variants.keys())
        ok = (mode == expect_mode) and app.bar.visible
        if expect_has_comp is not None:
            ok = ok and (("complete" in variants) == expect_has_comp)
        ok_all = ok_all and ok
        print(f"  {text:9} 模式={mode:9} 视图={variants} "
              f"visible={app.bar.visible} has_comp={'complete' in variants} "
              f"{forms[:4]}")
        print(f"            {'PASS' if ok else 'FAIL'} (期望 {expect_mode})")
        return mode

    print("补全 / 变格 模式自测")
    print("-" * 66)
    check("прив", "complete", True)      # 没打完 → 补全
    check("пожа", "complete", True)
    check("здрав", "complete", True)     # 虽是合法词，但有补全 → 仍优先补全
    check("привт", "complete", True)     # 拼错 → 更正
    check("хочу", "cases", False)        # 词已写完、没有更长的词 → 变格

    print("\n--- Tab 在有两种视图时切换 ---")
    m1 = check("друг", "complete", True)
    app._maybe_intercept(VK_TAB)
    pump()
    m2 = app._mode
    ok = (m1 != m2 and m2 == "cases")
    ok_all = ok_all and ok
    print(f"  друг: {m1} --Tab--> {m2}  {'PASS' if ok else 'FAIL'}")
    app._maybe_intercept(VK_TAB)
    pump()
    m3 = app._mode
    ok = (m3 == m1)
    ok_all = ok_all and ok
    print(f"  друг: {m2} --Tab--> {m3}  {'PASS' if ok else 'FAIL'}")

    print("\n--- 只有一种视图时，Tab 确认候选 ---")
    before = len(injected)
    check("хочу", "cases", False)
    app._maybe_intercept(VK_TAB)
    pump()
    picked = len(injected) > before
    ok = picked and not app.bar.visible
    ok_all = ok_all and ok
    print(f"  确认候选=True 收起了={not app.bar.visible}  "
          f"{'PASS' if ok else 'FAIL'}")

    app.hook.stop()
    app.root.destroy()
    print("\n" + ("全部通过" if ok_all else "有失败项"))
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
