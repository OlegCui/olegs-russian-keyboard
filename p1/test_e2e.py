# -*- coding: utf-8 -*-
"""
端到端测试：模拟用户真实操作（俄语布局 + 真按键）

流程：
  1. 建一个 Tk 输入框当"目标程序"
  2. 把它所在线程的键盘布局切成俄语（WM_INPUTLANGCHANGEREQUEST）
  3. 启动 App（require_lang=0x0419，和正式运行一致）
  4. 用 pynput 敲 "lheue"（俄语布局下就是 другу）
  5. 检查：输入框收到 другу、候选条弹出

这一步能回答"为什么用户试了没反应"。
"""
import ctypes
import sys
import time
import tkinter as tk
from ctypes import wintypes as wt

sys.stdout.reconfigure(encoding="utf-8")
import win32gui
from pynput.keyboard import Controller

sys.path.insert(0, "D:/Tools/俄语输入法/p1")
import app as app_mod
import hook as hook_mod

user32 = ctypes.WinDLL("user32", use_last_error=True)
WM_INPUTLANGCHANGEREQUEST = 0x0050
HKL_RU = 0x04190419
KEYS = "lheue"          # 俄语布局 → другу


def lang_of(hwnd):
    tid = user32.GetWindowThreadProcessId(hwnd, None)
    hkl = user32.GetKeyboardLayout(tid)
    return (hkl & 0xFFFF) if hkl else 0


def main():
    app = app_mod.App(require_lang=app_mod.LANG_RU, verbose=True)

    tw = tk.Toplevel(app.root)
    tw.title("e2e-target-2b73")
    tw.geometry("600x130+560+520")
    ent = tk.Entry(tw, font=("Consolas", 22), width=32)
    ent.pack(padx=16, pady=34)
    tw.attributes("-topmost", True)
    tw.update()
    tw.lift()
    tw.focus_force()
    tw.update()
    ent.focus_force()
    tw.update()
    time.sleep(0.5)

    root_hwnd = user32.GetAncestor(tw.winfo_id(), 2) or tw.winfo_id()
    print(f"目标窗口 hwnd={root_hwnd:#x}  布局前=0x{lang_of(root_hwnd):04X}")

    # 把目标窗口切到俄语布局（模拟用户按 Win+Space）
    for _ in range(10):
        user32.PostMessageW(root_hwnd, WM_INPUTLANGCHANGEREQUEST, 0, HKL_RU)
        time.sleep(0.15)
        tw.update()
        if lang_of(root_hwnd) == 0x0419:
            break
    cur = lang_of(root_hwnd)
    print(f"切换后布局=0x{cur:04X}  {'OK 俄语' if cur == 0x0419 else '失败'}")
    if cur != 0x0419:
        print("无法切到俄语布局，测试中止（真实环境需要用户手动切）")
        tw.destroy()
        app.root.destroy()
        return 1

    if not app.start():
        print("钩子安装失败")
        return 1
    app.root.after(40, app.pump)

    # 确保焦点真的在目标框上，否则按键会跑去别处
    fg = win32gui.GetForegroundWindow()
    if fg != root_hwnd:
        print(f"前台是 {win32gui.GetWindowText(fg)[:30]!r}，点击目标框抢回焦点")
        l, t, r, b = win32gui.GetWindowRect(root_hwnd)
        from pynput.mouse import Button, Controller as Ms
        ms = Ms()
        x, y = l + (r - l) // 2, t + (b - t) // 2
        under = win32gui.GetAncestor(win32gui.WindowFromPoint((x, y)), 2)
        if under != root_hwnd:
            print(f"  ⛔ 坐标 ({x},{y}) 不属于目标窗口，中止")
            app.hook.stop()
            tw.destroy()
            app.root.destroy()
            return 1
        ms.position = (x, y)
        time.sleep(0.15)
        ms.click(Button.left, 1)
        tw.update()
        time.sleep(0.4)

    fg = win32gui.GetForegroundWindow()
    print(f"打字前前台: hwnd={fg:#x} 是目标={fg == root_hwnd} "
          f"布局=0x{lang_of(fg):04X}")
    if fg != root_hwnd:
        print("焦点仍不在目标窗口，测试无效")
        app.hook.stop()
        tw.destroy()
        app.root.destroy()
        return 1

    # 用真实虚拟键码打字（pynput 会发 VK_PACKET，钩子转不出字符）
    VK = {"l": 0x4C, "h": 0x48, "e": 0x45, "u": 0x55}
    import input_sim
    for ch in KEYS:
        input_sim.send_vk(VK[ch])
        for _ in range(6):
            app.root.update()
            time.sleep(0.03)

    # 等 debounce 触发
    for _ in range(40):
        app.root.update()
        time.sleep(0.02)

    typed = ent.get()
    shown = app.bar.visible
    print("\n" + "=" * 58)
    print(f"  输入框内容 : {typed!r}   (期望 'другу')")
    print(f"  钩子缓冲   : {app.hook.buffer!r}")
    print(f"  候选条显示 : {shown}")
    if app.bar.cells:
        print(f"  候选词     : {[it['form'] for _, it in app.bar.cells]}")
    print("=" * 58)

    ok = typed == "другу" and shown
    print("结论:", "端到端可用 ✅" if ok else "端到端不通 ❌")
    if not ok:
        print("排查方向：")
        if typed != "другу":
            print("  - 键没进目标框 → 注入/焦点问题")
        if app.hook.buffer.strip() != "другу":
            print(f"  - 钩子读到 {app.hook.buffer!r} → 布局过滤或转字符问题")
        if not shown:
            print("  - 候选条没弹 → 引擎或显示问题")

    app.hook.stop()
    tw.destroy()
    app.root.destroy()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
