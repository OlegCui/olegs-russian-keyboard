# -*- coding: utf-8 -*-
"""
输入注入自测：在自建 Tk 输入框里验证 退格 + Unicode 注入。

安全：只往自己的窗口注入，注入前校验前台窗口是我们自己。
"""
import sys
import time
import tkinter as tk

sys.stdout.reconfigure(encoding="utf-8")
import win32gui

sys.path.insert(0, "D:/Tools/俄语输入法/p1")
import input_sim


def main():
    root = tk.Tk()
    root.title("sim-selftest-5e21")
    root.geometry("720x180+380+340")
    ent = tk.Entry(root, font=("Consolas", 22), width=40)
    ent.pack(padx=20, pady=50)
    root.attributes("-topmost", True)
    root.update()
    root.lift()
    root.focus_force()
    root.update()
    ent.focus_force()
    root.update()
    time.sleep(0.6)

    fg = win32gui.GetWindowText(win32gui.GetForegroundWindow())
    if "sim-selftest-5e21" not in fg:
        print(f"前台是 {fg[:30]!r}，放弃")
        root.destroy()
        return 1

    results = []

    def case(name, initial, backspaces, text, expect):
        ent.delete(0, "end")
        ent.insert(0, initial)
        ent.icursor("end")
        root.update()
        time.sleep(0.15)
        input_sim.replace_tail(backspaces, text)
        for _ in range(15):
            root.update()
            time.sleep(0.02)
        got = ent.get()
        ok = got == expect
        results.append((name, initial, got, expect, ok))
        print(f"  {name:22} 初始={initial!r:12} 结果={got!r:14} 期望={expect!r:14} "
              f"{'PASS' if ok else 'FAIL'}")

    print("输入注入自测")
    case("拉丁替换", "drugu", 5, "drugom", "drugom")
    case("西里尔替换", "другу", 5, "друга", "друга")
    case("只退 2 个", "другу", 2, "X", "друX")
    case("纯注入", "", 0, "привет", "привет")
    case("长文本", "", 0, "здравствуйте, как дела?", "здравствуйте, как дела?")

    root.destroy()
    passed = sum(1 for r in results if r[4])
    print(f"\n  {passed}/{len(results)} 通过")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
