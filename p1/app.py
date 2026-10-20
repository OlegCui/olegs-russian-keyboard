# -*- coding: utf-8 -*-
"""
P1-b 整合：钩子 → 引擎 → 悬浮候选条

架构：
   [键盘钩子线程] --queue--> [Tk 主线程 pump] --> [引擎] --> [候选条]
   跨线程只走队列，Tk 只在主线程操作。

用法：
  python app.py                 # 正式模式：只在俄语布局下工作
  python app.py --lang none     # 调试模式：任何布局都工作
  python app.py --selftest      # 自动自测（不依赖真实键盘注入）
"""
import argparse
import ctypes
import os
import queue
import re
import sys
import time

# 必须在一切其它导入之前：--windowed 打包后 sys.stdout/stderr 是 None，
# 任何模块在导入期 print 一句都会让程序直接死在隐藏的错误对话框里（双击无反应）。
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = sys.stdout

import tkinter as tk
from ctypes import wintypes as wt

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import engine as engine_mod
import hook as hook_mod
import input_sim
import probe as probe_mod

user32 = ctypes.WinDLL("user32", use_last_error=True)
try:
    dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
except Exception:              # 很老的 Windows 没有 dwmapi
    dwmapi = None
GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008

LANG_RU = 0x0419
VERSION = "0.6.0"
DEBOUNCE_MS = 120       # 停止输入多久后弹出候选条
BAR_FONT_PX = 28        # 候选条固定字号（像素），不再跟随正文

# 这些程序里一律不弹候选条（密码管理器）
DEFAULT_EXCLUDE = {
    "keepass.exe", "keepassxc.exe", "1password.exe", "bitwarden.exe",
    "lastpass.exe", "dashlane.exe", "enpass.exe", "roboform.exe",
}
SEP = set(" \t\r\n.,;:!?()\"«»—–-")

try:
    import paths as path_mod
    LOGFILE = path_mod.LOG_FILE
except Exception:
    path_mod = None
    LOGFILE = os.path.join(HERE, "app.log")
_LOG_FH = None


def log(msg):
    """同时写屏幕和日志文件，方便用户回传。"""
    global _LOG_FH
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    try:
        print(line, flush=True)
    except Exception:
        pass
    try:
        if _LOG_FH is None:
            _LOG_FH = open(LOGFILE, "a", encoding="utf-8")
        _LOG_FH.write(line + "\n")
        _LOG_FH.flush()
    except Exception as e:
        # 写不进主日志时留个线索，否则打包后完全看不到问题
        try:
            import tempfile
            with open(os.path.join(tempfile.gettempdir(), "olegs_log_fail.txt"),
                      "a", encoding="utf-8") as fh:
                fh.write(f"{line}   [写日志失败: {e}]\n")
        except Exception:
            pass


def installed_layouts():
    n = user32.GetKeyboardLayoutList(0, None)
    arr = (ctypes.c_void_p * n)()
    user32.GetKeyboardLayoutList(n, arr)
    return sorted({int(h) & 0xFFFF for h in arr if h})


def foreground_lang():
    fg = user32.GetForegroundWindow()
    tid = user32.GetWindowThreadProcessId(fg, None)
    hkl = user32.GetKeyboardLayout(tid)
    return (int(hkl) & 0xFFFF) if hkl else 0


def foreground_title():
    fg = user32.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(128)
    user32.GetWindowTextW(fg, buf, 128)
    return buf.value[:40]


def current_word(text):
    i = len(text)
    while i > 0 and text[i - 1] not in SEP:
        i -= 1
    return text[i:]


def previous_word(text):
    """刚打完一个词（以空格/标点结尾）时，取它前面的那个词，用于预测下一个词。"""
    body = text.rstrip()
    if not body:
        return ""
    if body == text and text[-1:] not in SEP:
        # 末尾没有分隔符 = 正在打词，不是"词已结束"
        return ""
    body = body.rstrip("".join(SEP))
    m = re.search(r"[А-Яа-яЁё\-]{2,}$", body)
    return m.group(0).lower() if m else ""


def previous_words(text, n=2):
    """取结尾处最近 n 个完整词（从旧到新）。用于三元组预测。

    和 previous_word 的区别：这里允许单字母词（я / в / и / с / к），
    它们在俄语里是最常见的预测起点。
    """
    body = text.rstrip()
    if not body:
        return []
    if body == text and text[-1:] not in SEP:
        return []                     # 还在打词，词没结束
    body = body.rstrip("".join(SEP))
    words = re.findall(r"[А-Яа-яЁё\-]{1,24}", body)
    return [w.lower() for w in words[-n:]]


def focused_rect():
    try:
        import uiautomation as auto
        c = auto.GetFocusedControl()
        if c is None:
            return None
        r = c.BoundingRectangle
        if r is None or r.right - r.left < 2 or r.bottom - r.top < 2:
            return None
        return (r.left, r.top, r.right, r.bottom)
    except Exception:
        return None


HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020


def _top_hwnd(win):
    """Tk 的 winfo_id() 是子窗口，真正的顶层窗口要用 GetAncestor 取。"""
    win.update_idletasks()
    child = win.winfo_id()
    return user32.GetAncestor(child, 2) or child


THEMES = {
    "dark": {
        "bg": "#252525", "border": "#3d3d3d", "cell": "#323232",
        "cell_hover": "#3d3d3d", "text": "#ffffff", "sub": "#a8a8a8",
        "hint": "#7a7a7a", "warn_bg": "#332a1f", "warn_fg": "#ffb74d",
        "dot": "#ffb74d", "pill": "#e6e6e6",
    },
    "light": {
        "bg": "#f3f3f3", "border": "#d4d4d4", "cell": "#ffffff",
        "cell_hover": "#e8e8e8", "text": "#1b1b1b", "sub": "#5c5c5c",
        "hint": "#8a8a8a", "warn_bg": "#fff4e5", "warn_fg": "#8a5a00",
        "dot": "#c77700", "pill": "#1b1b1b",
    },
}


def system_is_light():
    """Windows 系统是浅色还是深色（个性化 → 颜色）。"""
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as k:
            v, _ = winreg.QueryValueEx(k, "AppsUseLightTheme")
            return bool(v)
    except Exception:
        return False


def resolve_theme(name):
    """'auto' 按系统来，其余原样返回（不认识就当深色）。"""
    n = (name or "dark").lower()
    if n == "auto":
        return "light" if system_is_light() else "dark"
    return n if n in THEMES else "dark"


def round_corners(win):
    """Windows 11 圆角（DWMWA_WINDOW_CORNER_PREFERENCE = 33，ROUND = 2）。"""
    try:
        h = _top_hwnd(win)
        pref = ctypes.c_int(2)
        dwmapi.DwmSetWindowAttribute(h, 33, ctypes.byref(pref),
                                     ctypes.sizeof(pref))
    except Exception:
        pass


def accent_color():
    """系统强调色（设置 → 个性化 → 颜色）。取不到就用 Win11 默认蓝。"""
    try:
        val = ctypes.c_uint32()
        opaque = ctypes.c_int()
        dwmapi.DwmGetColorizationColor(ctypes.byref(val), ctypes.byref(opaque))
        v = val.value
        r, g, b = (v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF
        if r + g + b < 90:          # 太暗（近黑）时用默认蓝，否则看不出选中
            return "#0067c0"
        # 稍微提亮，深色背景上才醒目
        r = min(255, int(r * 1.15) + 10)
        g = min(255, int(g * 1.15) + 10)
        b = min(255, int(b * 1.15) + 10)
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        return "#0067c0"


def make_no_activate(win):
    """WS_EX_NOACTIVATE 必须加在**顶层**窗口上，加在子窗口上完全无效。"""
    h = _top_hwnd(win)
    ex = user32.GetWindowLongW(h, GWL_EXSTYLE)
    user32.SetWindowLongW(h, GWL_EXSTYLE,
                          ex | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST)
    user32.SetWindowPos(h, HWND_TOPMOST, 0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_FRAMECHANGED)
    return h


class Bar:
    """悬浮候选条：无边框、置顶、**不抢焦点**（否则点选后没法往目标程序打字）。"""

    def __init__(self, root, theme="dark"):
        self.visible = False
        self.last = None
        self.on_pick = None          # 点选回调：回调参数是该候选词
        self.cells = []              # [(frame, item)] 供自测定位
        self.items = []
        self.data = None
        self.selected = 0
        self.navigated = False       # 用户是否用 ←/→ 动过高亮
        self.font_px = 14            # 由 App 根据光标高度设置
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.withdraw()
        self.accent = accent_color()
        self.outer = None
        self.apply_theme(theme)
        make_no_activate(self.win)

    def apply_theme(self, name):
        """换主题：只改配色，控件结构不变。"""
        self.theme = resolve_theme(name)
        self.t = THEMES[self.theme]
        self.bg = self.t["bg"]
        self.border = self.t["border"]
        self.cell_bg = self.t["cell"]
        self.cell_hover = self.t["cell_hover"]
        self.win.configure(bg=self.bg)
        if self.outer is None:
            self.outer = tk.Frame(self.win, bg=self.bg,
                                  highlightbackground=self.border,
                                  highlightthickness=1)
            self.outer.pack(fill="both", expand=True)
        else:
            self.outer.configure(bg=self.bg, highlightbackground=self.border)
        if self.visible and self.data:
            self.render(self.data, keep_sel=True)
            self.show_at(*self.last[:2])

    def hwnd(self):
        return _top_hwnd(self.win)

    def _click(self, item):
        if self.on_pick:
            try:
                self.on_pick(item)
            except Exception as e:
                log(f"[bar] on_pick 异常: {e}")

    def set_font_size(self, px):
        self.font_px = max(11, min(48, int(px)))

    def render(self, data, keep_sel=False):
        fs = self.font_px
        limit = 6 if fs <= 20 else (5 if fs <= 26 else 4)
        if not keep_sel or data is not self.data:
            self.selected = 0
            self.navigated = False
            for i, it in enumerate(data["items"][:limit]):
                if it["form"] == data["token"].lower():
                    self.selected = i
                    break
        self.data = data
        self.items = data["items"][:limit]

        for c in self.outer.winfo_children():
            c.destroy()

        head = tk.Frame(self.outer, bg=self.bg)
        head.pack(fill="x", padx=12, pady=(9, 2))
        tk.Label(head, text=data.get("lemma", data["token"]), bg=self.bg,
                 fg=self.t["text"],
                 font=("Segoe UI Semibold", -max(13, int(fs * 0.76)), "bold")
                 ).pack(side="left")
        cur = data.get("current") or {}
        tag = " · ".join(x for x in [cur.get("pos_zh"), cur.get("case_zh")] if x)
        if tag:
            tk.Label(head, text="  " + tag, bg=self.bg, fg=self.t["sub"],
                     font=("Microsoft YaHei UI", -max(10, int(fs * 0.58)))
                     ).pack(side="left")
        tk.Label(head, text="空格选1 · 1-6 · ←/→ · Enter 保留",
                 bg=self.bg, fg=self.t["hint"],
                 font=("Microsoft YaHei UI", -max(9, int(fs * 0.5)))
                 ).pack(side="right")

        row = tk.Frame(self.outer, bg=self.bg)
        row.pack(fill="x", padx=7, pady=(3, 8))
        self.cells = []
        for i, it in enumerate(self.items):
            sel = (i == self.selected)
            cell = tk.Frame(row, bg=self.accent if sel else self.cell_bg,
                            cursor="hand2", highlightthickness=0)
            cell.pack(side="left", padx=3)
            l1 = tk.Label(cell, text=it["form"],
                          bg=cell["bg"], fg="#ffffff" if sel else self.t["text"],
                          font=("Segoe UI Semibold", -fs, "bold"))
            l1.pack(padx=max(10, int(fs * 0.7)), pady=(5, 0))
            l2 = tk.Label(cell, text=f"{i + 1}  {it['label']}", bg=cell["bg"],
                          fg="#ffffff" if sel else self.t["sub"],
                          font=("Microsoft YaHei UI", -max(10, int(fs * 0.56))))
            l2.pack(padx=10, pady=(0, 5))
            for w in (cell, l1, l2):
                w.bind("<Button-1>", lambda e, x=it: self._click(x))
            if not sel:                      # 鼠标悬停
                for w in (cell, l1, l2):
                    w.bind("<Enter>", lambda e, c=cell, a=l1, b=l2:
                           self._hover(c, a, b, True))
                    w.bind("<Leave>", lambda e, c=cell, a=l1, b=l2:
                           self._hover(c, a, b, False))
            self.cells.append((cell, it))

        findings = data.get("findings") or []
        if findings:
            f = findings[0]
            tk.Label(self.outer, text=f"⚠ {f['title']}", bg=self.t["warn_bg"],
                     fg=self.t["warn_fg"],
                     font=("Microsoft YaHei UI", -max(10, int(fs * 0.58))),
                     anchor="w").pack(fill="x", padx=12, pady=(0, 6))

        hint = data.get("hint")
        if hint:
            tk.Label(self.outer, text=hint, bg=self.bg, fg=self.t["hint"],
                     font=("Microsoft YaHei UI", -max(9, int(fs * 0.5))),
                     anchor="e").pack(fill="x", padx=12, pady=(0, 6))

        self.win.update_idletasks()
        self.visible = True

    def move(self, d):
        if not self.items:
            return
        self.selected = (self.selected + d) % len(self.items)
        self.navigated = True
        self.render(self.data, keep_sel=True)

    def _hover(self, cell, l1, l2, on):
        """鼠标移上去给一点反馈，不然看不出哪块能点。"""
        try:
            if cell["bg"] == self.accent:
                return                    # 选中项不跟随悬停变色
            bg = self.cell_hover if on else self.cell_bg
            for w in (cell, l1, l2):
                w.configure(bg=bg)
        except Exception:
            pass

    def show_at(self, x, y):
        w = self.win.winfo_reqwidth()
        h = self.win.winfo_reqheight()
        l, t, r, b = work_area()
        x = max(l + 4, min(int(x), r - w - 4))
        y = max(t + 4, min(int(y), b - h - 4))
        self.win.geometry(f"{w}x{h}+{x}+{y}")
        self.win.deiconify()
        make_no_activate(self.win)     # 每次显示后重刷，防止被 Tk 重置
        round_corners(self.win)        # Win11 圆角
        self.last = (x, y, w, h)

    def hide(self):
        if self.visible or self.win.state() != "withdrawn":
            self.win.withdraw()
        self.visible = False


class StatusPill:
    """屏幕底部居中的轻量状态条：几秒后自动消失，右键有菜单。"""

    def __init__(self, root, app=None, theme="dark"):
        self.root = root
        self.app = app
        self._hide_job = None
        self._hover = False
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.frame = None
        self.apply_theme(theme)
        make_no_activate(self.win)
        self.win.deiconify()
        self.set("已启动 · 右键这里可退出", None, autohide=9000)

    def apply_theme(self, name):
        self.theme = resolve_theme(name)
        self.t = THEMES[self.theme]
        self.bg = self.t["bg"]
        self.win.configure(bg=self.bg)
        if self.frame is None:
            self.frame = tk.Frame(self.win, bg=self.bg,
                                  highlightbackground=self.t["border"],
                                  highlightthickness=1)
            self.frame.pack()
            self.dot = tk.Label(self.frame, text="●", bg=self.bg,
                                fg=self.t["dot"], font=("Segoe UI", -12))
            self.dot.pack(side="left", padx=(10, 4), pady=6)
            self.label = tk.Label(self.frame, text="启动中…", bg=self.bg,
                                  fg=self.t["pill"],
                                  font=("Microsoft YaHei UI", -12))
            self.label.pack(side="left", padx=(0, 10), pady=6)
            for w in (self.win, self.frame, self.dot, self.label):
                w.bind("<Button-3>", self._menu)
                w.bind("<Button-1>", self._click)
                w.bind("<Enter>", self._on_enter)
                w.bind("<Leave>", self._on_leave)
            self.win.protocol("WM_DELETE_WINDOW", self.hide)
        else:
            self.frame.configure(bg=self.bg, highlightbackground=self.t["border"])
            self.dot.configure(bg=self.bg, fg=self.t["dot"])
            self.label.configure(bg=self.bg, fg=self.t["pill"])

    # ---------- 位置：桌面工作区底部居中 ----------
    def _place(self):
        self.win.update_idletasks()
        w = self.win.winfo_reqwidth()
        h = self.win.winfo_reqheight()
        l, t, r, b = work_area()
        x = l + max(0, (r - l - w) // 2)
        y = b - h - 24
        self.win.geometry(f"{w}x{h}+{x}+{y}")
        round_corners(self.win)

    # ---------- 显示 / 隐藏 ----------
    def set(self, text, ok=None, autohide=6000):
        try:
            self.update_text(text, ok)
            self.win.deiconify()
            self._place()
            make_no_activate(self.win)
            if autohide:
                self._schedule_hide(autohide)
            if not getattr(self, "_logged", False):
                self._logged = True
                log(f"[pill] 状态条已显示 {self.win.geometry()}")
        except Exception:
            pass

    def update_text(self, text, ok=None):
        try:
            self.label.config(text=text)
            self.dot.config(fg="#4caf50" if ok is True else
                            ("#ff6b6b" if ok is False else "#ffb74d"))
        except Exception:
            pass

    def hide(self):
        self._cancel_hide()
        try:
            self.win.withdraw()
        except Exception:
            pass

    def _schedule_hide(self, ms):
        self._cancel_hide()
        try:
            self._hide_job = self.win.after(ms, self.hide)
        except Exception:
            pass

    def _cancel_hide(self):
        if self._hide_job is not None:
            try:
                self.win.after_cancel(self._hide_job)
            except Exception:
                pass
            self._hide_job = None

    def _on_enter(self, _e=None):
        self._hover = True
        self._cancel_hide()

    def _on_leave(self, _e=None):
        self._hover = False
        self._schedule_hide(2500)

    def _click(self, _e=None):
        if self.app is not None:
            self.app.show_menu(self.win, _e.x_root if _e else 0,
                               _e.y_root if _e else 0)

    def _menu(self, e):
        if self.app is not None:
            self.app.show_menu(self.win, e.x_root, e.y_root)

    def destroy(self):
        self._cancel_hide()
        try:
            self.win.destroy()
        except Exception:
            pass


def _flatten(obj):
    out = []
    if obj is None:
        return out
    if isinstance(obj, (int, float)):
        return [float(obj)]
    try:
        seq = list(obj)
    except Exception:
        return out
    for x in seq:
        out.extend(_flatten(x))
    return out


UIA_FONT_SIZE_ID = 40014          # UIA_FontSizeAttributeId（单位：磅）


def anchor_from_uia():
    """一次拿到 UIA 的光标位置和字号。返回 (pos, 字号磅值) 或 None。"""
    try:
        import uiautomation as auto
        c = auto.GetFocusedControl()
        if c is None:
            return None
        tp = c.GetPattern(auto.PatternId.TextPattern)
        if tp is None:
            return None
        sel = tp.GetSelection()
        if not sel:
            return None
        rng = sel[-1] if isinstance(sel, (list, tuple)) else sel
        pos = None
        nums = _flatten(rng.GetBoundingRectangles())
        if len(nums) >= 4:
            x1, y1, x2, y2 = nums[-4:]
            if not (x2 <= 0 and y2 <= 0):
                pos = (int(x1), int(y2) + 4)
        pt = None
        try:
            v = float(rng.GetAttributeValue(UIA_FONT_SIZE_ID))
            if 4.0 <= v <= 72.0:
                pt = v
        except Exception:
            pass
        if pos is None and pt is None:
            return None
        return pos, pt
    except Exception:
        return None


def caret_from_win32():
    """GetGUIThreadInfo 的光标 → (x, y, 高度)。Word 走这条。"""
    try:
        s = probe_mod.sample()
        c = (s or {}).get("caret")
        if not c:
            return None
        h = int(c.get("h") or 0)
        return (int(c["x"]), int(c["y"]) + max(h, 18), h)
    except Exception:
        return None


def font_px_from_pt(pt):
    """磅 → 像素（96 DPI 基准），下限是系统 UI 字体，上限 40。"""
    if not pt:
        return 0
    lo = min_font_px()
    return max(lo, min(40, int(round(float(pt) * 96.0 / 72.0))))


def font_from_height(h):
    """光标高度 → 字号（像素）。高度 <12 视为不可靠，返回 0。"""
    if not h or h < 12:
        return 0
    return max(min_font_px(), min(40, int(round(h * 0.8))))


class LOGFONTW(ctypes.Structure):
    _fields_ = [("lfHeight", wt.LONG), ("lfWidth", wt.LONG),
                ("lfEscapement", wt.LONG), ("lfOrientation", wt.LONG),
                ("lfWeight", wt.LONG), ("lfItalic", wt.BYTE),
                ("lfUnderline", wt.BYTE), ("lfStrikeOut", wt.BYTE),
                ("lfCharSet", wt.BYTE), ("lfOutPrecision", wt.BYTE),
                ("lfClipPrecision", wt.BYTE), ("lfQuality", wt.BYTE),
                ("lfPitchAndFamily", wt.BYTE), ("lfFaceName", wt.WCHAR * 32)]


class NONCLIENTMETRICSW(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT),
                ("iBorderWidth", ctypes.c_int), ("iScrollWidth", ctypes.c_int),
                ("iScrollHeight", ctypes.c_int), ("iCaptionWidth", ctypes.c_int),
                ("iCaptionHeight", ctypes.c_int), ("lfCaptionFont", LOGFONTW),
                ("iSmCaptionWidth", ctypes.c_int), ("iSmCaptionHeight", ctypes.c_int),
                ("lfSmCaptionFont", LOGFONTW),
                ("iMenuWidth", ctypes.c_int), ("iMenuHeight", ctypes.c_int),
                ("lfMenuFont", LOGFONTW), ("lfStatusFont", LOGFONTW),
                ("lfMessageFont", LOGFONTW), ("iPaddedBorderWidth", ctypes.c_int)]


def system_ui_font_px():
    """系统界面字体大小（像素）。跟随 Windows 的「文本大小」和 DPI 缩放。"""
    try:
        ncm = NONCLIENTMETRICSW()
        ncm.cbSize = ctypes.sizeof(ncm)
        if user32.SystemParametersInfoW(0x0029, ncm.cbSize,
                                        ctypes.byref(ncm), 0):
            h = abs(int(ncm.lfMessageFont.lfHeight))
            if 6 <= h <= 60:
                return h
    except Exception:
        pass
    try:
        gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
        hf = gdi32.GetStockObject(17)          # DEFAULT_GUI_FONT
        lf = LOGFONTW()
        if gdi32.GetObjectW(hf, ctypes.sizeof(lf), ctypes.byref(lf)):
            h = abs(int(lf.lfHeight))
            if 6 <= h <= 60:
                return h
    except Exception:
        pass
    return 12


_MIN_FONT_PX = None


def min_font_px():
    """候选条字号下限：低于这个就看不清了。"""
    global _MIN_FONT_PX
    if _MIN_FONT_PX is None:
        _MIN_FONT_PX = max(12, system_ui_font_px())
    return _MIN_FONT_PX


def font_from_wm_getfont():
    """问焦点控件要它的字体（WM_GETFONT）。记事本、多数 Win32 控件支持。"""
    try:
        h = user32.GetFocus()
        if not h:
            return 0
        hf = user32.SendMessageW(h, 0x0031, 0, 0)      # WM_GETFONT
        if not hf:
            return 0
        gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
        lf = LOGFONTW()
        if gdi32.GetObjectW(hf, ctypes.sizeof(lf), ctypes.byref(lf)):
            hgt = abs(int(lf.lfHeight))
            if 6 <= hgt <= 120:
                return max(14, min(40, hgt))
    except Exception:
        pass
    return 0


class RECT(ctypes.Structure):
    _fields_ = [("left", wt.LONG), ("top", wt.LONG),
                ("right", wt.LONG), ("bottom", wt.LONG)]


def work_area():
    """Windows 桌面工作区（已排除任务栏）。比 winfo_screen* 更靠谱。"""
    try:
        r = RECT()
        if user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0):
            if r.right > r.left and r.bottom > r.top:
                return (r.left, r.top, r.right, r.bottom)
    except Exception:
        pass
    return (0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))


def clipboard_word():
    """剪贴板里最后一个俄语词。只在按 Ctrl+D / Ctrl+L 时调用，不碰打字流程。"""
    try:
        import re
        import win32clipboard as cb
    except Exception:
        return ""
    try:
        cb.OpenClipboard()
    except Exception:
        return ""
    try:
        if not cb.IsClipboardFormatAvailable(cb.CF_UNICODETEXT):
            return ""
        txt = cb.GetClipboardData(cb.CF_UNICODETEXT) or ""
    except Exception:
        return ""
    finally:
        try:
            cb.CloseClipboard()
        except Exception:
            pass
    runs = re.findall(r"[\u0400-\u04FF\u0451\u0401\-]{2,}", txt)
    return runs[-1] if runs else ""


def foreground_exe():
    """前台程序的可执行文件名（小写）。"""
    try:
        import psutil
        import win32process
        hwnd = user32.GetForegroundWindow()
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        return (psutil.Process(pid).name() or "").lower()
    except Exception:
        return ""


def is_password_focus():
    """焦点是不是密码框（银行/登录页绝不能把词送出去）。"""
    try:
        import uiautomation as auto
        c = auto.GetFocusedControl()
        return bool(getattr(c, "IsPassword", False))
    except Exception:
        return False


def best_anchor():
    """返回 (坐标, 策略名, 字号px)。字号 0 表示没测到。"""
    pos, px = None, 0
    u = anchor_from_uia()
    how = "none"
    if u:
        upos, pt = u
        px = font_px_from_pt(pt)
        if upos:
            pos, how = upos, "caret-uia"
    if not px:
        px = font_from_wm_getfont()
    if pos is None:
        w = caret_from_win32()
        if w:
            pos, how = (w[0], w[1]), "caret-win32"
            if not px:
                px = font_from_height(w[2])
    if pos is None:
        rect = focused_rect()
        if rect:
            rw, rh = rect[2] - rect[0], rect[3] - rect[1]
            if rw < 1400 and rh < 900:
                pos, how = (rect[0], rect[3] + 6), "control"
            else:
                how = "control-huge"
    if pos is None:
        try:
            import win32api
            mx, my = win32api.GetCursorPos()
            sw = user32.GetSystemMetrics(0)
            sh = user32.GetSystemMetrics(1)
            mx = max(8, min(mx + 16, sw - 120))
            my = max(8, min(my + 18, sh - 80))
            pos, how = (mx, my), "mouse"
        except Exception:
            pos, how = None, "none"
    return pos, how, px


class App:
    def __init__(self, require_lang=LANG_RU, verbose=False, font_override=None):
        self.q = queue.Queue()
        self.verbose = verbose
        self.font_override = font_override
        self.eng = engine_mod.Engine()
        self.root = tk.Tk()
        self.root.withdraw()
        self.cfg_theme = "dark"          # dark / light / auto
        self.next_word = True            # 下一个词预测
        self.theme = resolve_theme(self.cfg_theme)
        self.bar = Bar(self.root, theme=self.theme)
        self.bar.on_pick = self._accept
        self._timer = None
        self._hide_timer = None
        self.updates = 0
        self.key_count = 0
        self._variants = {}
        self._mode = "cases"
        self._word = ""
        self._picked_word = None          # 记录当前候选条对应的词，供 accept 校验
        self.paused = False
        self.version = VERSION
        self.logpath = LOGFILE
        self.tray = None
        self._wb_win = None
        self.exclude = set(DEFAULT_EXCLUDE)
        self.auto_space = True         # 选词后自动补空格
        self.auto_capital = True       # 句首/专有名词首字母大写
        self.font_by_app = {}
        self._font_seen = set()
        self._skip_seen = set()
        self.layout_ru = None
        self._guard = (0, 0.0, False)
        try:
            from wordbook import WordBook
            self.wb = WordBook()
        except Exception as e:
            log(f"[wordbook] 初始化失败: {e}")
            self.wb = None
        self.pill = StatusPill(self.root, self, theme=self.theme)
        self.hook = hook_mod.KeyboardCapture(
            on_text=lambda t: self.q.put(("text", t)),
            on_word=lambda w: self.q.put(("word", w)),
            require_lang=require_lang,
            on_key=self._trace_key,
            intercept=self._maybe_intercept,
        )

    def _maybe_intercept(self, vk):
        """候选条显示时截下导航键；Ctrl+D / Ctrl+L 只要在打俄语就管。"""
        ctrl = bool(user32.GetAsyncKeyState(0x11) & 0x8000)
        # 这两个键候选条收起后也得管（条子 1.5 秒就自动隐藏了），
        # 但不能在中文/英文布局下抢走浏览器的 Ctrl+D / Ctrl+L
        if ctrl and vk in (0x44, 0x4C):
            word = current_word(getattr(self.hook, "buffer", ""))
            # 没在打字（或词是复制来的）→ 用剪贴板里的词
            # 只在按这两个键时读一次剪贴板，不影响 Ctrl+V
            if not word:
                word = clipboard_word()
            has_ru = any("\u0400" <= c <= "\u04FF" for c in word)
            # 候选条可见 = 显然在打俄语，布局 ID 报错也认；
            # 条子收起时必须真的在俄语布局，否则浏览器会丢快捷键
            ru = (foreground_lang() == LANG_RU) or (self.bar.visible and has_ru)
            if ru and word:
                key = "D" if vk == 0x44 else "L"
                log(f"[hotkey] Ctrl+{key} word={word!r}")
                self.q.put(("save" if vk == 0x44 else "lookup", word))
                return True
            return False
        if not self.bar.visible:
            return False
        if vk == 0x1B:                       # Esc
            self.q.put(("hide", None))
            return True
        if vk in (0x25, 0x27):               # ← →
            self.q.put(("move", -1 if vk == 0x25 else 1))
            return True
        if 0x31 <= vk <= 0x36:               # 数字 1-6 直选
            self.q.put(("pick", vk - 0x31))
            return True
        if vk == 0x20:                       # 空格：直接选 1 号候选，并补一个空格
            if (self.bar.visible and self._mode == "complete"
                    and self.bar.items):
                word = current_word(self.hook.buffer).lower()
                first = self.bar.items[0]["form"].lower()
                d = self.eng.dic
                rank_w = d.rank.get(word, 10 ** 9) if d else 10 ** 9
                rank_1 = d.rank.get(first, 10 ** 9) if d else 10 ** 9
                # 只在"1 号候选明显比已打的词更常用（3 倍以上）"时接管空格。
                # 这样 зав(10470)→зависеть(892) 会被接管，
                # 而 завтра(934)→завтрак(2931)、друг(95)→другой(42) 不会。
                if first != word and rank_1 * 3 < rank_w:
                    self.q.put(("pick_space", None))
                    log(f"[space] 接管空格：{word!r}(#{rank_w}) -> {first!r}(#{rank_1})")
                    return True
            return False                # 已打的是完整常用词，空格照常输入
        if vk == 0x0D:                       # Enter：没动过高亮就保留原样，动过就确认
            if self.bar.navigated:
                self.q.put(("pick", self.bar.selected))
            else:
                self.q.put(("keep", None))
            return True
        if vk == 0x09:                       # Tab：有第二种视图就切换，否则确认
            if len(self._variants) > 1:
                self.q.put(("toggle", None))
            else:
                self.q.put(("pick", self.bar.selected))
            return True
        return False

    def _trace_key(self, vk, scan, lang, ch):
        self.key_count += 1
        if self.key_count == 1 or self.key_count % 10 == 0:
            self.pill.set(f"俄语助手 运行中 · 已收 {self.key_count} 键", True)
        if not self.verbose:
            return
        want = self.hook.require_lang
        flag = "OK " if (want is None or lang == want) else "SKIP"
        log(f"[key] vk=0x{vk:02X} lang=0x{lang:04X} ch={ch!r:6} {flag}")

    def start(self):
        return self.hook.start()

    def pump(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "text":
                    self._schedule(payload)
                elif kind == "word":
                    self._word_end(payload)
                elif kind == "move":
                    self.bar.move(payload)
                elif kind == "pick":
                    self._pick(payload)
                elif kind == "pick_space":
                    self._pick_space()
                elif kind == "keep":
                    self._keep_typed()
                elif kind == "toggle":
                    self._toggle()
                elif kind == "save":
                    self._save_word(payload)
                elif kind == "lookup":
                    self._open_lookup(payload)
                elif kind == "hide":
                    self.bar.hide()
                elif kind == "ui":                 # 托盘线程投递过来的 UI 动作
                    try:
                        payload()
                    except Exception as e:
                        log(f"[ui] 动作异常: {e}")
        except queue.Empty:
            pass
        self.root.after(40, self.pump)

    def _schedule(self, text):
        # 新输入取消待执行的收起动作，否则用户连续打字时候选条会闪
        if self._hide_timer:
            try:
                self.root.after_cancel(self._hide_timer)
            except Exception:
                pass
            self._hide_timer = None
        if self._timer:
            try:
                self.root.after_cancel(self._timer)
            except Exception:
                pass
        # 补全计算本身只要 0.1–5ms，延迟主要来自这里的 debounce。
        # 原来是 320ms，打字快时会明显"慢半拍"，降到 120ms。
        self._timer = self.root.after(DEBOUNCE_MS, lambda: self._update(text))

    def _word_end(self, word):
        # 用户自己打完并确认的词，算一次弱信号
        if word and self.eng.uf:
            self.eng.uf.add(word, 1)
        if self._hide_timer:
            try:
                self.root.after_cancel(self._hide_timer)
            except Exception:
                pass
        self._hide_timer = self.root.after(1500, self.bar.hide)

    def _save_word(self, word=None):
        """Ctrl+D：把当前词加入生词本。"""
        if self.wb is None:
            return
        word = (word
                or current_word(getattr(self.hook, "buffer", ""))
                or self._word or "")
        if not word:
            return
        info = self.eng.analyze(word)
        top = info[0] if info else {}
        new = self.wb.add(word, lemma=top.get("lemma") or "",
                          pos=top.get("pos_zh") or "",
                          case=top.get("case_zh") or "",
                          app=foreground_title())
        msg = "已加入生词本" if new else "已在生词本（次数 +1）"
        self.pill.set(f"{msg}：{word}", True, autohide=3000)
        log(f"[wordbook] {word} lemma={top.get('lemma')} new={new} "
            f"共 {len(self.wb)} 词")

    def log(self, msg):
        """给托盘等其他模块用的日志入口。"""
        log(msg)

    def _watch_layout(self):
        """盯着前台键盘布局：切到俄语就就绪，切走就待命。"""
        try:
            if not self.paused:
                lang = foreground_lang()
                is_ru = (lang == LANG_RU)
                if is_ru != self.layout_ru:
                    self.layout_ru = is_ru
                    self._on_layout(is_ru, lang)
        except Exception:
            pass
        try:
            self.root.after(500, self._watch_layout)
        except Exception:
            pass

    def _on_layout(self, is_ru, lang):
        log(f"[layout] 前台布局 -> {'俄语 0x0419' if is_ru else f'0x{lang:04X}'}")
        if is_ru:
            self.pill.set("俄语布局 · 助手已就绪", True, autohide=2500)
        else:
            self.bar.hide()
            self.pill.set(f"布局 0x{lang:04X} · 助手待命", None, autohide=2000)
        if self.tray is not None:
            try:
                import tray
                tray.set_active(self, is_ru)
            except Exception:
                pass

    def show_menu(self, parent, x, y):
        """状态条的右键菜单（托盘看不到时的备用出口）。"""
        try:
            m = tk.Menu(parent, tearoff=0)
            m.add_command(label="▶ 继续" if self.paused else "⏸ 暂时关闭",
                          command=lambda: self.set_paused(not self.paused))
            m.add_separator()
            m.add_command(label="生词本…", command=self.open_wordbook)
            m.add_command(label="查词…", command=self.open_lookup_window)
            m.add_command(label="编辑规则卡…", command=self.open_rules)
            sub = tk.Menu(m, tearoff=0)
            sub.add_command(label="增大 +2", command=lambda: self.bump_font(+2))
            sub.add_command(label="减小 -2", command=lambda: self.bump_font(-2))
            sub.add_command(label="恢复默认", command=lambda: self.bump_font(0))
            m.add_cascade(label=f"候选字号（当前 {self.bar.font_px}px）", menu=sub)
            tsub = tk.Menu(m, tearoff=0)
            tsub.add_command(label="深色", command=lambda: self.apply_theme("dark"))
            tsub.add_command(label="浅色", command=lambda: self.apply_theme("light"))
            tsub.add_command(label="跟随系统",
                             command=lambda: self.apply_theme("auto"))
            m.add_cascade(label=f"主题（当前 {self.cfg_theme}）", menu=tsub)
            m.add_separator()
            m.add_command(label="隐藏状态条", command=self.pill.hide)
            m.add_separator()
            m.add_command(label="退出", command=self.quit)
            m.tk_popup(x, y)
        except Exception as e:
            log(f"[menu] 菜单打开失败: {e}")

    def show_pill(self):
        self.pill.set(f"运行中 v{VERSION} · 右键这里可退出", True, autohide=6000)

    def set_paused(self, p):
        """托盘开关：暂停后钩子完全不处理按键。"""
        self.paused = bool(p)
        self.hook.set_enabled(not self.paused)
        if self.paused:
            self.bar.hide()
            self.pill.set("已暂停 · 右键状态条恢复", False, autohide=4000)
        else:
            self.pill.set("已恢复", True, autohide=3000)
        log(f"[state] {'暂停' if self.paused else '继续'}")

    def open_rules(self):
        """打开规则卡文件供编辑；用户目录没有就先从内置复制一份。"""
        try:
            import shutil
            import subprocess
            import paths
            target = paths.RULES_USER
            if not os.path.exists(target):
                # 不能直接 copyfile：内置 rules.json 没有 BOM，记事本按 GBK 打开会乱码。
                # 统一写成带 BOM 的 UTF-8，记事本/Word 都能正确识别中文和俄语。
                try:
                    with open(paths.RULES_FILE, encoding="utf-8-sig") as src:
                        text = src.read()
                    with open(target, "w", encoding="utf-8-sig") as dst:
                        dst.write(text)
                except Exception:
                    shutil.copyfile(paths.RULES_FILE, target)
                log(f"[rules] 已复制默认规则到 {target}")
            subprocess.Popen(["notepad.exe", target])
            self.pill.set("已打开规则卡，改完重启生效", True, autohide=4000)
        except Exception as e:
            log(f"[rules] 打开失败: {e}")

    def open_wordbook(self):
        try:
            if self._wb_win is not None:
                try:
                    if self._wb_win.winfo_exists():
                        self._wb_win.deiconify()
                        self._wb_win.lift()
                        return
                except Exception:
                    pass
            if self.wb is None:
                return
            self._wb_win = self.wb.show_window(self.root, self.eng)
        except Exception:
            import traceback
            log("[wordbook] 打开失败:\n        " +
                traceback.format_exc().replace("\n", "\n        "))

    def open_lookup_window(self):
        self._open_lookup()

    def quit(self):
        log("[exit] 退出程序")
        try:
            self.hook.stop()
        except Exception:
            pass
        try:
            if self.wb is not None:
                self.wb.export_md()
        except Exception:
            pass
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass

    def _open_lookup(self, word=None):
        """Ctrl+L：打开形式词典查当前词。"""
        try:
            import lookup
            w = (word or current_word(getattr(self.hook, "buffer", ""))
                 or self._word or "")
            lookup.show_lookup(self.root, self.eng, w)
            log(f"[lookup] 查词 {w!r}")
        except Exception:
            import traceback
            log("[lookup] 打开失败:\n        " +
                traceback.format_exc().replace("\n", "\n        "))

    def _pick(self, idx):
        if 0 <= idx < len(self.bar.items):
            log(f"[pick] 索引 {idx} -> {self.bar.items[idx]['form']!r}")
            self._accept(self.bar.items[idx])
        else:
            log(f"[pick] 索引 {idx} 越界（共 {len(self.bar.items)} 项）")

    def _autocap(self, new, word):
        """句首、或专有名词 → 首字母大写。"""
        if not new or new[:1].isupper():
            return new
        buf = ""
        try:
            buf = self.hook.buffer
        except Exception:
            pass
        if self.auto_capital:
            core = buf.rstrip()
            if word:
                idx = buf.rfind(word)
                before = buf[:idx].rstrip() if idx >= 0 else core
            else:
                # 插入的是新词（下一个词预测）：句子状态看整个缓冲的结尾
                before = core
            at_start = (not before) or (before[-1] in ".!?…\n\r")
            if at_start:
                return new[:1].upper() + new[1:]
            try:
                if self.eng.is_proper(new):
                    return new[:1].upper() + new[1:]
            except Exception:
                pass
        return new

    def _keep_typed(self):
        """回车：不动已打的字母，只补空格并收起候选条。"""
        word = current_word(getattr(self.hook, "buffer", ""))
        log(f"[keep] 保留原样 {word!r}")
        if self.auto_space and word:
            try:
                self.hook.pause()
                time.sleep(0.02)
                input_sim.send_text(" ")
                time.sleep(0.03)
            finally:
                self.hook.resume()
            self.hook.buffer += " "
        self.bar.hide()

    def _pick_space(self):
        """空格选 1 号候选（和点选走同一条路径，带自动空格）。"""
        if not self.bar.items:
            return
        item = self.bar.items[0]
        log(f"[space] 空格选 1 号 {item['form']!r}")
        self._accept(item)

    def _accept(self, item, add_space=None):
        """选中候选词：删掉已输入的部分，注入选中的词形（可自动空格）。"""
        try:
            buf = self.hook.buffer
            word = current_word(buf)
            n = len(word)
            new = item["form"]
            if word[:1].isupper() and new:
                new = new[:1].upper() + new[1:]
            else:
                new = self._autocap(new, word)
            if add_space is None:
                add_space = self.auto_space
            fg_before = user32.GetForegroundWindow()
            log(f"[accept] 选了 {item['form']!r} -> {new!r} | 当前词={word!r} 退格={n} "
                f"| 自动空格={add_space} | 前台={fg_before:#x} {foreground_title()!r}")
            self.hook.pause()
            try:
                ok = input_sim.replace_tail(n, new)
                time.sleep(0.05)
                if ok and add_space:
                    input_sim.send_text(" ")
                    time.sleep(0.04)
            finally:
                self.hook.resume()
            fg_after = user32.GetForegroundWindow()
            # 注入期间钩子被暂停，这里手动把缓冲对齐到真实情况
            self.hook.buffer = buf[:len(buf) - n] + new + (" " if add_space else "")
            self._accepted_at = time.time()
            # 强信号：用户从候选条里选了这个词
            if self.eng.uf:
                self.eng.uf.add(new, 2)
                self.eng.uf.save(force=True)
            log(f"[accept] 注入={ok} 前台后={fg_after:#x} "
                f"缓冲={self.hook.buffer!r}")
            if self._hide_timer:
                try:
                    self.root.after_cancel(self._hide_timer)
                except Exception:
                    pass
                self._hide_timer = None
            self.bar.hide()
            return ok
        except Exception:
            import traceback
            log("[accept] 异常:\n        " +
                traceback.format_exc().replace("\n", "\n        "))
            return False

    def _update(self, text):
        """带计时的入口：卡顿超过 80ms 会写进日志，方便定位是哪一步慢。"""
        t0 = time.perf_counter()
        try:
            self._update_inner(text)
        finally:
            ms = (time.perf_counter() - t0) * 1000.0
            if ms > 80:
                tm = getattr(self, "_timing", {}) or {}
                log(f"[perf] 更新耗时 {ms:.0f}ms  '{text[-24:]}'  "
                    f"模式={self._mode} 锚={getattr(self, '_last_how', '')}  "
                    f"分项: " + " ".join(f"{k}={v:.0f}ms" for k, v in tm.items()))

    def _update_inner(self, text):
        t = time.perf_counter
        t0 = t()
        word = current_word(text)

        # 一个词刚结束（以空格/标点收尾）→ 预测下一个词
        if self.next_word and not word.strip() and text.strip():
            if time.time() - getattr(self, "_accepted_at", 0) < 0.35:
                self.bar.hide()          # 刚选完词，别马上又弹
                return
            prevs = previous_words(text, 2)
            preds, src, used = ((self.eng.predict_ctx(prevs) if prevs
                                 else ([], "none", [])))
            if preds:
                items = [{"form": w, "label": "预测"} for w in preds]
                ctx = " ".join(used)
                self._word = ""
                self._variants = {"predict": {
                    "token": "", "lemma": ctx, "current": {},
                    "items": items, "findings": [], "mode": "predict",
                    "hint": f"「{ctx}」后面常见 · {src}",
                }}
                self._timing = {"guard": 0.0, "suggest": 0.0,
                                "complete": (t() - t0) * 1000}
                self._show("predict")
                return

        if len(word) < 2 or not any("\u0400" <= c <= "\u04FF" for c in word):
            self.bar.hide()
            return
        if self._skip_here():
            self.bar.hide()
            return
        t1 = t()
        cases = self.eng.suggest(word)
        t2 = t()
        comp = self.eng.complete(word)
        valid = self.eng.is_valid(word)
        t3 = t()
        self._timing = {"guard": (t1 - t0) * 1000, "suggest": (t2 - t1) * 1000,
                        "complete": (t3 - t2) * 1000}

        variants = {}
        if comp:
            variants["complete"] = {
                "token": word, "lemma": word, "current": {},
                "items": comp, "findings": [],
                "mode": "complete",
                "hint": "Tab 看变格" if (valid and cases.get("items")) else "",
            }
        if valid and cases.get("items"):
            c = dict(cases)
            c["mode"] = "cases"
            c["hint"] = "Tab 看补全" if comp else ""
            variants["cases"] = c
        if not variants:
            self.bar.hide()
            return

        self._word = word
        self._variants = variants
        # 规则：有补全就先帮拼写；没补全了（词已写完）才自动切到变格教学
        mode = "complete" if "complete" in variants else "cases"
        self._show(mode)
        self._timing["show"] = (time.perf_counter() - t3) * 1000

    def _skip_here(self):
        """密码框 / 排除程序里不弹候选条。

        is_password_focus() 走 UIA，在 Chromium 里单次要 70-90ms，
        所以按"前台窗口 + 1 秒"缓存，换窗口立刻重查。
        """
        try:
            hwnd = user32.GetForegroundWindow()
        except Exception:
            hwnd = 0
        now = time.time()
        h, ts, blocked = self._guard
        if h == hwnd and (now - ts) < 1.0:
            return blocked
        blocked = False
        try:
            if is_password_focus():
                self._note_skip("password")
                blocked = True
            else:
                exe = foreground_exe()
                if exe and exe in self.exclude:
                    self._note_skip(exe)
                    blocked = True
        except Exception:
            pass
        self._guard = (hwnd, now, blocked)
        return blocked

    def _note_skip(self, reason):
        if reason not in self._skip_seen:
            self._skip_seen.add(reason)
            log(f"[skip] 在 {reason} 里不弹候选条")

    def apply_theme(self, name, save=True):
        """切换主题：dark / light / auto，立即生效并写进 settings.json。"""
        self.cfg_theme = (name or "dark").lower()
        try:
            self.bar.apply_theme(self.cfg_theme)
            self.pill.apply_theme(self.cfg_theme)
        except Exception as e:
            log(f"[theme] 切换失败: {e}")
            return
        real = resolve_theme(self.cfg_theme)
        log(f"[theme] 主题={self.cfg_theme}（实际 {real}）")
        try:
            self.pill.set("主题：" + ("深色" if real == "dark" else "浅色")
                          + ("（跟随系统）" if self.cfg_theme == "auto" else ""),
                          True, autohide=2000)
        except Exception:
            pass
        if save:
            self._save_setting("theme", self.cfg_theme)

    def _save_setting(self, key, value):
        try:
            import json
            import paths
            cfg = paths.SETTINGS_FILE
            data = {}
            if os.path.exists(cfg):
                try:
                    with open(cfg, encoding="utf-8-sig") as fh:
                        data = json.load(fh) or {}
                except Exception:
                    data = {}
            data[key] = value
            with open(cfg, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
        except Exception as e:
            log(f"[配置] 保存 {key} 失败: {e}")

    def bump_font(self, delta):
        """托盘里调字号：delta=0 恢复默认，否则 ±。会写进 settings.json。"""
        if delta == 0:
            px = BAR_FONT_PX
        else:
            px = max(11, min(48, (self.bar.font_px or BAR_FONT_PX) + delta))
        self.font_override = px
        self.bar.set_font_size(px)
        if self.bar.visible:
            try:
                self.bar.render(self.bar.data, keep_sel=True)
            except Exception:
                pass
        self.pill.set(f"候选字号 {px}px（已保存）", True, autohide=2500)
        log(f"[font] 用户把候选字号调成 {px}px")
        self._save_font(px)

    def _save_font(self, px):
        try:
            import json
            import paths
            cfg = paths.SETTINGS_FILE
            data = {}
            if os.path.exists(cfg):
                try:
                    with open(cfg, encoding="utf-8-sig") as fh:
                        data = json.load(fh) or {}
                except Exception:
                    data = {}
            data["font_size"] = int(px)
            with open(cfg, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
        except Exception as e:
            log(f"[font] 保存设置失败: {e}")

    def _font_px(self, fpx=0, how=""):
        """候选条字号固定，不再跟随正文。
        优先级：命令行 > settings.font_px_by_app > settings.font_size > 默认。"""
        if self.font_override:
            return int(self.font_override)
        try:
            exe = foreground_exe()
        except Exception:
            exe = ""
        ov = self.font_by_app.get(exe) if exe else None
        if ov:
            return int(ov)
        return BAR_FONT_PX

    def _show(self, mode):
        data = self._variants.get(mode)
        if not data:
            return
        self._mode = mode
        pos, how, fpx = best_anchor()
        self._last_how = how
        x, y = pos if pos else (300, 300)
        px = self._font_px(fpx, how)
        self.bar.set_font_size(px)
        self.bar.render(data)
        self.bar.show_at(x, y)
        self.updates += 1
        if self.updates <= 10:
            log(f"[bar:{mode}] {self._word} -> "
                f"{[i['form'] for i in data['items'][:6]]} @({x},{y}) "
                f"锚={how} 字号={px}px")

    def _toggle(self):
        other = "complete" if self._mode == "cases" else "cases"
        if other in self._variants:
            log(f"[toggle] {self._mode} -> {other}")
            self._show(other)

    def run(self):
        self.root.after(40, self.pump)
        self.root.after(600, self._watch_layout)
        self.root.after(6000, self._heartbeat)
        try:
            import tray
            self.tray = tray.start(self)
        except Exception as e:
            log(f"[tray] 启动失败: {e}")
        self.root.mainloop()

    def _heartbeat(self):
        if self.key_count == 0:
            self.pill.update_text("已启动 · 还没收到按键（布局是吗？）", False)
            log(f"[心跳] 还没收到任何按键 | 前台={foreground_title()!r} "
                f"布局=0x{foreground_lang():04X}")
            log("        如果这时你正在打字，说明钩子没收到——把 app.log 发我")
        else:
            self.pill.update_text(
                f"运行中 v{VERSION} · 已收 {self.key_count} 键", True)
        self.root.after(6000, self._heartbeat)

    def stop(self):
        self.hook.stop()
        if self.tray is not None:
            try:
                self.tray.stop()
            except Exception:
                pass


def selftest():
    """不依赖真实键盘：直接把文本事件喂进管线，验证 钩子→队列→引擎→候选条。"""
    print("P1-b 自测（管线）")
    app = App(require_lang=None)
    # 用临时记忆库，别把测试词写进真实使用数据
    try:
        import tempfile
        from learn import UserFreq
        app.eng._uf = UserFreq(os.path.join(tempfile.gettempdir(),
                                            "_freq_selftest.json"))
    except Exception:
        pass
    ok_hook = app.start()
    print(f"  钩子安装: {'OK' if ok_hook else 'FAIL'}")

    cases = [
        ("другу", True, 1),          # 只有「другую」这一个补全
        ("хочу", True, 4),
        ("я", False, 0),
        ("привет мир", True, 4),
        ("привет мир ", True, 4),    # 词刚结束 → 给下一个词预测
        ("привет мир  ", True, 4),   # 再多一个空格，仍然预测同一个词
    ]
    app.root.after(40, app.pump)
    results = []
    for text, should_show, min_items in cases:
        app.q.put(("text", text))
        for _ in range(40):                 # 推进 Tk 事件循环，等 debounce 触发
            app.root.update()
            time.sleep(0.02)
        shown = app.bar.visible
        n = len(app.bar.items)              # 候选条里实际有几项（补全/变格/预测通用）
        ok = (shown == should_show) and (n >= min_items or not should_show)
        results.append((text, shown, n, ok))
        print(f"  输入 {text!r:20} 候选条显示={shown}  条目={n}  "
              f"{'PASS' if ok else 'FAIL'}")
        app.q.put(("word", current_word(text)))

    app.stop()
    app.root.destroy()
    passed = sum(1 for r in results if r[3])
    print(f"\n  管线 {passed}/{len(results)} 通过")
    return passed == len(results)


def accept_selftest():
    """验证「点候选词 → 目标输入框内容被替换」，并检查点击没抢走焦点。"""
    from pynput.mouse import Button, Controller as Ms
    import win32gui

    print("P1-b 接受建议自测")
    app = App(require_lang=None)
    app.start()

    tw = tk.Toplevel(app.root)
    tw.title("target-4f81")
    tw.geometry("620x130+520+540")
    ent = tk.Entry(tw, font=("Consolas", 20), width=34)
    ent.pack(padx=16, pady=34)
    tw.attributes("-topmost", True)
    tw.update()
    tw.lift()
    tw.focus_force()
    tw.update()
    ent.focus_force()
    tw.update()
    time.sleep(0.6)

    ok_all = True
    ms = Ms()

    def case(typed, pick_form, expect):
        nonlocal ok_all
        # 安全闸：前台必须是我们的测试窗口，否则注入会打进用户的其他程序
        fg_title = win32gui.GetWindowText(win32gui.GetForegroundWindow())
        if "target-4f81" not in fg_title:
            print(f"  ⛔ 前台是 {fg_title[:30]!r}，不是测试窗口，放弃本用例")
            ok_all = False
            return
        ent.delete(0, "end")
        ent.insert(0, typed)
        ent.icursor("end")
        tw.update()
        time.sleep(0.15)

        app.hook.buffer = typed
        data = app.eng.suggest(typed)
        app.bar.render(data)
        app.bar.show_at(120, 120)      # 远离目标输入框，避免点击时误伤
        app.root.update()
        time.sleep(0.25)

        target = None
        for cell, it in app.bar.cells:
            if it["form"] == pick_form:
                target = cell
                break
        if target is None:
            print(f"  找不到候选 {pick_form}")
            ok_all = False
            return

        x = target.winfo_rootx() + target.winfo_width() // 2
        y = target.winfo_rooty() + target.winfo_height() // 2
        under = win32gui.GetAncestor(win32gui.WindowFromPoint((x, y)), 2)
        if under != app.bar.hwnd():
            print(f"  ⛔ 坐标 ({x},{y}) 不属于候选条，放弃点击")
            ok_all = False
            return

        fg_before = win32gui.GetForegroundWindow()
        ms.position = (x, y)
        time.sleep(0.15)
        ms.click(Button.left, 1)
        for _ in range(30):
            app.root.update()
            time.sleep(0.02)
        time.sleep(0.15)
        for _ in range(20):
            app.root.update()
            time.sleep(0.02)

        got = ent.get()
        fg_after = win32gui.GetForegroundWindow()
        focus_kept = (fg_after == fg_before)
        allok = (got == expect) and focus_kept
        ok_all = ok_all and allok
        print(f"  输入 {typed!r:10} 点 {pick_form!r:10} -> 结果 {got!r:12} "
              f"期望 {expect!r:12} 焦点保持={focus_kept}  "
              f"{'PASS' if allok else 'FAIL'}")

    case("другу", "друга", "друга")
    case("другу", "другом", "другом")
    case("Другу", "друга", "Друга")     # 首字母大写要保留
    case("хочу", "хочешь", "хочешь")

    app.hook.stop()
    tw.destroy()
    app.root.destroy()
    print(f"\n  接受建议: {'全部通过' if ok_all else '有失败项'}")
    return ok_all


def main():
    # 第一件事就写日志：只要这个文件被启动过，就一定留痕
    log("=" * 58)
    log(f"[启动] python={sys.executable}")
    log(f"[启动] cwd={os.getcwd()}")
    log(f"[启动] 参数={' '.join(sys.argv[1:]) or '(无)'}")
    try:
        _run_main()
    except SystemExit:
        raise
    except Exception:
        import traceback
        log("[FATAL] 启动失败:\n        " +
            traceback.format_exc().replace("\n", "\n        "))
        raise


def _run_main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="ru", choices=["ru", "none"])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--accept-selftest", action="store_true")
    ap.add_argument("--font-size", type=int, default=None,
                    help="固定候选条字号（像素）；默认跟随正文光标高度")
    ap.add_argument("--wordbook", action="store_true",
                    help="只打开生词本窗口，不启动输入助手")
    ap.add_argument("--lookup", nargs="?", const="", default=None,
                    help="打开形式词典，可带一个词，如 --lookup другу")
    ap.add_argument("--version", action="store_true", help="打印版本号后退出")
    a = ap.parse_args()

    if a.version:
        print(f"Oleg's Russian Keyboard v{VERSION}")
        return

    if a.wordbook:
        from wordbook import WordBook
        WordBook().show_window()
        return

    if a.lookup is not None:
        import lookup
        root = tk.Tk()
        root.withdraw()
        lookup.show_lookup(root, engine_mod.Engine(), a.lookup or "")
        root.mainloop()
        return

    if a.accept_selftest:
        sys.exit(0 if accept_selftest() else 1)
    if a.selftest:
        sys.exit(0 if selftest() else 1)

    lang = LANG_RU if a.lang == "ru" else None

    # 配置：命令行 > settings.json > 默认
    cfg = (path_mod.SETTINGS_FILE if path_mod
           else os.path.join(HERE, "settings.json"))
    cfg_data = {}
    if os.path.exists(cfg):
        try:
            import json
            with open(cfg, encoding="utf-8-sig") as fh:
                cfg_data = json.load(fh) or {}
        except Exception as e:
            log(f"[配置] settings.json 读取失败: {e}")

    fs = a.font_size
    if fs is None and cfg_data.get("font_size"):
        fs = int(cfg_data["font_size"])
        log(f"[配置] 从 settings.json 读到字号 {fs}px")
    if fs:
        log(f"[配置] 候选条字号固定为 {fs}px（来自设置）")
    else:
        log(f"[配置] 候选条字号固定为 {BAR_FONT_PX}px（默认，不跟随正文）")

    app = App(require_lang=lang, verbose=True, font_override=fs)

    extra = cfg_data.get("exclude_apps") or []
    if extra:
        app.exclude |= {str(x).strip().lower() for x in extra if str(x).strip()}
    log(f"[配置] 排除程序（不弹候选条）: {sorted(app.exclude)}")

    fba = cfg_data.get("font_px_by_app") or {}
    if isinstance(fba, dict) and fba:
        app.font_by_app = {str(k).strip().lower(): int(v)
                           for k, v in fba.items() if v}
        log(f"[配置] 按程序指定字号: {app.font_by_app}")

    app.apply_theme(cfg_data.get("theme", "dark"), save=False)
    log(f"[配置] 主题={app.cfg_theme}（实际 {resolve_theme(app.cfg_theme)}）")

    if "next_word" in cfg_data:
        app.next_word = bool(cfg_data["next_word"])
    log(f"[配置] 下一个词预测={app.next_word}")
    try:
        _p = app.eng.predictor
        if _p:
            log(f"[配置] 预测模型: 二元组 {len(_p.bigram)} 前词 / "
                f"三元组 {len(_p.trigram)} 前两词")
        else:
            log("[配置] 预测模型: 无")
    except Exception as _e:
        log(f"[配置] 预测模型加载失败: {_e}")

    if "auto_space" in cfg_data:
        app.auto_space = bool(cfg_data["auto_space"])
    if "auto_capital" in cfg_data:
        app.auto_capital = bool(cfg_data["auto_capital"])
    log(f"[配置] 自动空格={app.auto_space}  自动大写={app.auto_capital}")
    log(f"[配置] 规则卡: {app.eng.rules_path}（{len(app.eng.cards)} 张）")
    _d = app.eng.dic
    if _d:
        log(f"[配置] 词表: {len(_d.words)} 词，补全可用")
    else:
        log(f"[配置] ⚠ 词表未加载，补全不可用（只有变格提示）— "
            f"找的是 {path_mod.WORDS_FILE if path_mod else '?'}")

    ls = installed_layouts()
    log("=" * 58)
    log(f" Oleg's Russian Keyboard v{VERSION}")
    log(f" 已安装键盘布局: {[f'0x{x:04X}' for x in ls]}")
    if LANG_RU not in ls:
        log(" ❌ 没装俄语布局！先添加：设置 → 时间和语言 → 语言和区域")
        log("    → 添加语言 → 俄语 → 装好后按 Win+空格 切换")
    else:
        log(" ✅ 俄语布局已安装 (0x0419)")
    log(f" 当前前台窗口: {foreground_title()!r}")
    log(f" 当前布局: 0x{foreground_lang():04X}")
    log(f" 布局过滤: {'仅俄语' if lang else '关闭（任何布局都响应）'}")
    try:
        dpi = user32.GetDpiForSystem()
    except Exception:
        dpi = 96
    log(f" 系统 DPI: {dpi}（缩放 {dpi / 96:.0%}）| "
        f"系统 UI 字体: {system_ui_font_px()}px | 候选条下限: {min_font_px()}px")
    log(f" 日志文件: {LOGFILE}")

    if not app.start():
        log(" ❌ 键盘钩子安装失败")
        sys.exit(1)
    log(" ✅ 钩子已安装")
    log("=" * 58)
    log(" 用法：切到俄语布局 → 在任意输入框打俄语 → 停 0.3 秒看候选条")
    log(" 退出：Ctrl+C")
    try:
        app.run()
    except KeyboardInterrupt:
        log("退出中…")
    finally:
        app.stop()


if __name__ == "__main__":
    main()
