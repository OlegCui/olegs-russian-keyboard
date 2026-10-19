# -*- coding: utf-8 -*-
"""
P1-b 原型：悬浮候选条

设计要点（来自 P1-a 探测结论）：
  - 锚定「焦点控件的矩形」，不依赖像素级光标
  - 窗口不抢焦点：overrideredirect + WS_EX_NOACTIVATE + WS_EX_TOOLWINDOW
  - 永远置顶，但不进任务栏

用法：
  python popup.py                    # 演示：在屏幕中央弹一个候选条，3 秒后消失
  python popup.py --follow 5         # 跟随焦点控件 5 秒
"""
import argparse
import ctypes
import sys
import time
import tkinter as tk
from ctypes import wintypes as wt

sys.stdout.reconfigure(encoding="utf-8")

user32 = ctypes.WinDLL("user32", use_last_error=True)
GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008


def no_activate(win):
    """让窗口永远不抢焦点、不进 Alt+Tab、不进任务栏。"""
    win.update_idletasks()
    hwnd = win.winfo_id()
    ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                          ex | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST)


class CandidateBar:
    ITEMS = [
        ("другу", "与格"),
        ("друга", "属格 · 宾格"),
        ("другом", "造格"),
    ]

    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.win = tk.Toplevel(self.root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)

        bg = "#1f2226"
        self.win.configure(bg=bg)
        frame = tk.Frame(self.win, bg=bg, highlightbackground="#3a3f45",
                         highlightthickness=1)
        frame.pack(fill="both", expand=True)

        head = tk.Label(frame, text="друг", bg=bg, fg="#8a9199",
                        font=("Segoe UI", 9), anchor="w")
        head.pack(fill="x", padx=10, pady=(7, 2))

        row = tk.Frame(frame, bg=bg)
        row.pack(fill="x", padx=6, pady=(0, 8))

        for i, (form, tag) in enumerate(self.ITEMS):
            cell = tk.Frame(row, bg="#2c3136" if i else "#3b6ea5")
            cell.pack(side="left", padx=3)
            tk.Label(cell, text=form, bg=cell["bg"], fg="#ffffff",
                     font=("Consolas", 15, "bold")).pack(padx=9, pady=(5, 0))
            tk.Label(cell, text=tag, bg=cell["bg"], fg="#c8d0d8",
                     font=("Microsoft YaHei", 8)).pack(padx=9, pady=(0, 5))

        no_activate(self.win)

    def show_at(self, x, y):
        self.win.update_idletasks()
        w = self.win.winfo_reqwidth()
        h = self.win.winfo_reqheight()
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        x = max(4, min(x, sw - w - 4))
        y = max(4, min(y, sh - h - 4))
        self.win.geometry(f"{w}x{h}+{int(x)}+{int(y)}")
        self.win.deiconify()
        self.win.lift()
        return w, h

    def hide(self):
        self.win.withdraw()

    def run(self, seconds):
        end = time.time() + seconds
        while time.time() < end:
            self.root.update()
            time.sleep(0.03)


def focused_rect():
    """取焦点控件矩形（P1-a 结论：这是最可靠的锚点）。"""
    try:
        import uiautomation as auto
        c = auto.GetFocusedControl()
        if c is None:
            return None
        r = c.BoundingRectangle
        if r is None:
            return None
        left, top, right, bottom = r.left, r.top, r.right, r.bottom
        if right - left < 2 or bottom - top < 2:
            return None
        return left, top, right, bottom
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--follow", type=int, default=0, help="跟随焦点控件的秒数")
    ap.add_argument("--x", type=int, default=None)
    ap.add_argument("--y", type=int, default=None)
    a = ap.parse_args()

    bar = CandidateBar()

    if a.follow:
        print(f"跟随焦点控件 {a.follow} 秒…（把光标放进任意输入框）")
        end = time.time() + a.follow
        last = None
        shown = False
        while time.time() < end:
            r = focused_rect()
            if r:
                l, t, rr, b = r
                pos = (l, b + 6)
                if pos != last:
                    bar.show_at(*pos)
                    last = pos
                    shown = True
                    print(f"  锚定 {pos}  (控件 {rr-l}×{b-t})")
            bar.root.update()
            time.sleep(0.15)
        bar.hide()
        print("结束。" if shown else "没拿到焦点控件矩形。")
        return

    if a.x is not None and a.y is not None:
        x, y = a.x, a.y
        print(f"使用指定坐标 ({x},{y})")
    else:
        x = a.x if a.x is not None else 400
        y = a.y if a.y is not None else 400
        r = focused_rect()
        if r:
            x, y = r[0], r[3] + 6
            print(f"检测到焦点控件，锚定到 ({x},{y})")
        else:
            print(f"没有焦点控件矩形，用固定坐标 ({x},{y})")
    bar.show_at(x, y)
    bar.run(3.0)


if __name__ == "__main__":
    main()
