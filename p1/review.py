# -*- coding: utf-8 -*-
"""
生词本复习窗口（间隔重复）。

一张卡片一个词：词 → 原形 · 词性/格 · 例句
四个按钮：忘了 / 勉强 / 记得 / 太简单
选完自动排下一次复习时间，全部过完显示总结。

调度（SM-2 简化版，够用且不会把间隔拉得太疯）：
   忘了    → 间隔 1 天，ease -0.20
   勉强    → 间隔 ×1.2，ease -0.05
   记得    → 间隔 ×2.0
   太简单  → 间隔 ×3.0，ease +0.10
间隔上限 180 天，ease 限制在 1.3–3.0。
"""
import time

import tkinter as tk
import tkinter.ttk as ttk

BG = "#ffffff"
FG = "#202020"
MUTED = "#6b6b6b"
CARD = "#f6f7f9"
LINE = "#d8dade"
ACCENT = "#1b8d1b"

GRADES = (
    ("忘了", 0, "#c62828"),
    ("勉强", 1, "#ef6c00"),
    ("记得", 2, "#2e7d32"),
    ("太简单", 3, "#1565c0"),
)


class ReviewWindow:
    def __init__(self, root, wb, eng=None, examples=None, on_done=None):
        self.root = root
        self.wb = wb
        self.eng = eng
        self.examples = examples
        self.on_done = on_done
        self.queue = wb.due_words()
        self.index = 0
        self.done = 0

        self.win = tk.Toplevel(root)
        self.win.title("生词本 · 复习")
        self.win.configure(bg=BG)
        self.win.geometry("560x420")
        self.win.minsize(480, 380)

        try:
            style = ttk.Style(self.win)
            if "vista" in style.theme_names():
                style.theme_use("vista")
        except Exception:
            pass

        head = ttk.Frame(self.win, padding=(16, 12, 16, 4))
        head.pack(fill="x")
        self.lbl_count = ttk.Label(head, text="", font=("Microsoft YaHei UI", 11))
        self.lbl_count.pack(side="left")
        self.lbl_stat = ttk.Label(head, text="", foreground=MUTED,
                                 font=("Microsoft YaHei UI", 9))
        self.lbl_stat.pack(side="right")

        body = tk.Frame(self.win, bg=CARD, highlightthickness=1,
                        highlightbackground=LINE)
        body.pack(fill="both", expand=True, padx=16, pady=8)

        self.lbl_word = tk.Label(body, text="", bg=CARD, fg=FG,
                                 font=("Segoe UI Semibold", 30, "bold"))
        self.lbl_word.pack(pady=(26, 4))
        self.lbl_meta = tk.Label(body, text="", bg=CARD, fg=MUTED,
                                 font=("Microsoft YaHei UI", 10))
        self.lbl_meta.pack()
        self.lbl_example = tk.Label(body, text="", bg=CARD, fg="#3a3a3a",
                                    font=("Segoe UI", 11), wraplength=470,
                                    justify="center")
        self.lbl_example.pack(pady=(14, 10), padx=18)

        btns = ttk.Frame(self.win, padding=(16, 4, 16, 14))
        btns.pack(fill="x")
        self.buttons = []
        for label, grade, color in GRADES:
            b = tk.Button(btns, text=label, bg=color, fg="#ffffff",
                          activebackground=color, activeforeground="#ffffff",
                          relief="flat", font=("Microsoft YaHei UI", 10),
                          padx=14, pady=6, cursor="hand2",
                          command=lambda g=grade: self.grade(g))
            b.pack(side="left", expand=True, fill="x", padx=4)
            self.buttons.append(b)

        self.win.bind("<space>", lambda e: self.grade(2))
        self.win.bind("<Escape>", lambda e: self.close())
        self.win.bind("1", lambda e: self.grade(0))
        self.win.bind("2", lambda e: self.grade(1))
        self.win.bind("3", lambda e: self.grade(2))
        self.win.bind("4", lambda e: self.grade(3))

        self._lift()
        self.render()

    def _lift(self):
        try:
            self.win.deiconify()
            self.win.attributes("-topmost", True)
            self.win.lift()
            self.win.focus_force()
            self.win.after(400, lambda: self.win.attributes("-topmost", False))
        except Exception:
            pass

    def _current(self):
        if self.index >= len(self.queue):
            return None
        return self.queue[self.index]

    def render(self):
        total = len(self.queue)
        item = self._current()
        if item is None:
            self.show_summary()
            return
        self.lbl_count.configure(text=f"{self.index + 1} / {total}")
        self.lbl_stat.configure(
            text=f"本轮已复习 {self.done} · 生词本共 {len(self.wb.words)} 词")
        self.lbl_word.configure(text=item.get("word", ""))
        bits = [item.get("lemma") or ""]
        tag = " · ".join(x for x in [item.get("pos"), item.get("case")] if x)
        if tag:
            bits.append(tag)
        self.lbl_meta.configure(text="  |  ".join(x for x in bits if x))
        sent = ""
        if self.examples is not None:
            morph = getattr(self.eng, "morph", None) if self.eng else None
            sent = self.examples.get(item.get("lemma") or item.get("word", ""),
                                     morph)
        self.lbl_example.configure(text=sent or "（这个词暂时没有例句）")
        for b in self.buttons:
            b.configure(state="normal")

    def grade(self, g):
        item = self._current()
        if item is None:
            return
        self.wb.review(item.get("word", ""), g)
        self.done += 1
        self.index += 1
        self.render()

    def show_summary(self):
        self.lbl_count.configure(text="复习完成")
        self.lbl_stat.configure(text="")
        self.lbl_word.configure(text="✓", fg=ACCENT)
        remain = len(self.wb.due_words())
        self.lbl_meta.configure(
            text=f"今天复习了 {self.done} 个词 · 还有 {remain} 个到期")
        self.lbl_example.configure(
            text="按 Esc 关闭。明天再来，间隔会自己变长。")
        for b in self.buttons:
            b.configure(state="disabled")
        if self.on_done:
            try:
                self.on_done(self.done)
            except Exception:
                pass

    def close(self):
        try:
            self.win.destroy()
        except Exception:
            pass


def open_review(root, wb, eng=None, examples=None, on_done=None):
    """打开复习窗口；没有到期的词就返回 None（由调用方提示）。"""
    if not wb.due_words():
        return None
    return ReviewWindow(root, wb, eng=eng, examples=examples, on_done=on_done)
