# -*- coding: utf-8 -*-
"""
键盘钩子自测（A/B 对照）

A 组：不装钩子，直接打字 → 看输入框是否收到
B 组：装钩子，同样打字    → 看输入框是否仍然收到（关键：不能吞键）

安全：只在自建 Tk 窗口里输入；打字前校验前台窗口确实是我们的窗口。
"""
import sys
import time
import tkinter as tk

sys.stdout.reconfigure(encoding="utf-8")
import win32gui
from pynput.keyboard import Controller

sys.path.insert(0, "D:/Tools/俄语输入法/p1")
from hook import KeyboardCapture

TEXT = "privet mir kak dela "
kb = Controller()


def run_case(with_hook):
    words = []
    cap = None
    if with_hook:
        cap = KeyboardCapture(on_word=words.append, require_lang=None)
        if not cap.start():
            return None, None, "钩子安装失败"

    root = tk.Tk()
    root.title("hook-selftest-ab")
    root.geometry("720x180+360+320")
    ent = tk.Entry(root, font=("Consolas", 20), width=46)
    ent.pack(padx=20, pady=50)
    root.attributes("-topmost", True)
    root.update()
    root.lift()
    time.sleep(0.6)
    root.focus_force()
    root.update()
    time.sleep(0.2)
    ent.focus_force()          # 先给窗口焦点，再把焦点交给输入框
    root.update()
    time.sleep(0.4)

    for _ in range(20):
        if "hook-selftest-ab" in win32gui.GetWindowText(win32gui.GetForegroundWindow()):
            break
        time.sleep(0.1)
        root.update()
        ent.focus_force()

    fg_title = win32gui.GetWindowText(win32gui.GetForegroundWindow())
    focus_widget = str(root.focus_get())
    if "hook-selftest-ab" not in fg_title:
        root.destroy()
        if cap:
            cap.stop()
        return None, None, f"前台是 {fg_title[:30]!r}，放弃输入"
    print(f"  窗口焦点={focus_widget}")

    for ch in TEXT:
        kb.type(ch)
        root.update()
        time.sleep(0.03)
    for _ in range(20):
        root.update()
        time.sleep(0.03)

    got = ent.get()
    buf = cap.buffer if cap else None
    if cap:
        cap.stop()
    root.destroy()
    return got, buf, None


def main():
    print("A 组：不装钩子")
    a_text, _, err = run_case(False)
    print(f"  输入框内容 = {a_text!r}" + (f"  错误: {err}" if err else ""))
    time.sleep(0.8)

    print("\nB 组：装钩子")
    b_text, b_buf, err = run_case(True)
    print(f"  输入框内容 = {b_text!r}" + (f"  错误: {err}" if err else ""))
    print(f"  钩子缓冲   = {b_buf!r}")

    print("\n" + "=" * 56)
    checks = [
        ("A 组收到了输入（基线）", bool(a_text)),
        ("B 组与 A 组结果完全一致（没吞键）", b_text == a_text),
        ("B 组钩子读到了原始按键", (b_buf or "").strip() == TEXT.strip()),
    ]
    ok = True
    for name, cond in checks:
        print(f"  {'PASS' if cond else 'FAIL'}  {name}")
        ok = ok and cond
    print("=" * 56)
    print("结论:", "钩子可用，不影响用户输入" if ok else "仍有问题")


if __name__ == "__main__":
    main()

