# -*- coding: utf-8 -*-
"""
键盘选择测试（安全版）

关键：**不发送任何真实按键、不向任何窗口注入**
  - 直接调用 app._maybe_intercept(vk) 模拟按键
  - 打桩 input_sim.replace_tail，把"注入"改成改我们自己的输入框

这样测的是完整逻辑链：拦截 → 队列 → 选词 → 替换，且零副作用。
"""
import sys
import time
import tkinter as tk

sys.stdout.reconfigure(encoding="utf-8")
import ctypes

sys.path.insert(0, "D:/Tools/俄语输入法/p1")
import app as app_mod

user32 = ctypes.WinDLL("user32", use_last_error=True)
GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080

VK = {"1": 0x31, "2": 0x32, "3": 0x33, "LEFT": 0x25, "RIGHT": 0x27,
      "TAB": 0x09, "ESC": 0x1B, "ENTER": 0x0D}


def main():
    app = app_mod.App(require_lang=None, verbose=False)
    # 用临时记忆库，别污染真实使用数据
    import os
    import tempfile
    import learn
    app.eng._uf = learn.UserFreq(
        os.path.join(tempfile.gettempdir(), "_freq_test_keys.json"))
    app.start()
    app.root.after(40, app.pump)

    tw = tk.Toplevel(app.root)
    tw.title("keys-target-91ce")
    tw.geometry("620x130+540+520")
    ent = tk.Entry(tw, font=("Consolas", 20), width=34)
    ent.pack(padx=16, pady=34)
    tw.update()

    # 打桩：把真实注入换成改我们的输入框（不碰任何其他窗口）
    def fake_replace(n, text):
        cur = ent.get()
        new = (cur[:-n] if n else cur) + text
        ent.delete(0, "end")
        ent.insert(0, new)
        tw.update()
        return True

    app_mod.input_sim.replace_tail = fake_replace

    def fake_send(text):
        # 自动空格也走注入，同样必须打桩，否则会打到真实窗口里
        cur = ent.get()
        ent.delete(0, "end")
        ent.insert(0, cur + text)
        tw.update()
        return True

    app_mod.input_sim.send_text = fake_send

    h = app.bar.hwnd()
    ex = user32.GetWindowLongW(h, GWL_EXSTYLE)
    noact = bool(ex & WS_EX_NOACTIVATE)
    tool = bool(ex & WS_EX_TOOLWINDOW)
    print(f"候选条顶层 hwnd={h:#x}")
    print(f"  WS_EX_NOACTIVATE={noact}  WS_EX_TOOLWINDOW={tool}")

    def pump(n=25, dt=0.02):
        for _ in range(n):
            app.root.update()
            time.sleep(dt)

    results = []

    def setup(word):
        ent.delete(0, "end")
        ent.insert(0, word)
        ent.icursor("end")
        tw.update()
        app.hook.buffer = word
        app.bar.render(app.eng.suggest(word))
        app.bar.show_at(150, 150)
        app.root.update()

    def press(vk):
        handled = app._maybe_intercept(vk)
        pump()
        return handled

    def case(name, word, keys, expect):
        setup(word)
        handled_all = all(press(k) for k in keys)
        got = ent.get()
        ok = handled_all and got == expect
        results.append((name, ok))
        print(f"  {name:22} 结果={got!r:12} 期望={expect!r:12} "
              f"全部被拦截={handled_all} {'PASS' if ok else 'FAIL'}")

    print("\n--- 键盘选择 ---")
    # 期望值含两个新行为：自动补空格 + 句首首字母大写
    case("数字 2 直选", "другу", [VK["2"]], "Друга ")
    case("数字 1 直选", "другу", [VK["1"]], "Друг ")
    case("→ 一次 + Tab", "другу", [VK["RIGHT"], VK["TAB"]], "Друга ")
    case("→ 一次 + Enter", "другу", [VK["RIGHT"], VK["ENTER"]], "Друга ")
    case("← 一次 + Enter", "другу", [VK["LEFT"], VK["ENTER"]], "Друга ")
    case("← 两次 + Tab", "другу", [VK["LEFT"], VK["LEFT"], VK["TAB"]],
         "Друг ")
    # 回车：没动过高亮 = 保留已打的字母，只补空格
    case("Enter 保留原样", "другу", [VK["ENTER"]], "другу ")

    print("\n--- 未显示时不该拦截 ---")
    app.bar.hide()
    app.root.update()
    handled = app._maybe_intercept(VK["2"])
    results.append(("隐藏时不拦截", not handled))
    print(f"  候选条隐藏时按 2: 被拦截={handled}  {'PASS' if not handled else 'FAIL'}")

    print("\n--- Esc 关闭 ---")
    setup("другу")
    press(VK["ESC"])
    ok = not app.bar.visible
    results.append(("Esc 关闭", ok))
    print(f"  候选条 visible={app.bar.visible}  {'PASS' if ok else 'FAIL'}")

    app.hook.stop()
    tw.destroy()
    app.root.destroy()

    passed = sum(1 for _, ok in results if ok)
    print(f"\n  {passed}/{len(results)} 通过")
    return 0 if (passed == len(results) and noact and tool) else 1


if __name__ == "__main__":
    sys.exit(main())
