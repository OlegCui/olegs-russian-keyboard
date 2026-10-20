# -*- coding: utf-8 -*-
"""
反馈报告：把运行状态和日志整理成一份可以直接贴到 GitHub Issue 的文本。

隐私
----
日志里原本会出现前台窗口标题、你打的词。这里统一脱敏：
- 丢掉逐键记录（[key]）
- 引号里超过 12 字符的内容（窗口标题、词）替换成 '…'
- 用户名路径替换成 %USER%

发出去之前用户还能自己看一遍（窗口预览 + 复制），不做偷偷上传。
"""
import os
import platform
import re
import sys

REPO = "https://github.com/OlegCui/olegs-russian-keyboard"
ISSUE_URL = REPO + "/issues/new"

MAX_LOG_LINES = 160


def _redact(line):
    line = re.sub(r"'([^']{13,})'", "'…'", line)
    try:
        user = os.environ.get("USERNAME") or ""
        if user:
            line = line.replace(user, "%USER%")
    except Exception:
        pass
    return line


def _tail(path, limit=MAX_LOG_LINES):
    try:
        if not path or not os.path.exists(path):
            return []
        with open(path, encoding="utf-8", errors="ignore") as fh:
            lines = fh.readlines()[-limit:]
        out = []
        for line in lines:
            if "[key]" in line:
                continue
            out.append(_redact(line.rstrip("\n")))
        return out
    except Exception:
        return []


def build(app, version, logpath=None):
    """生成报告文本。app 可以是 None（这时只报环境）。"""
    bits = []
    bits.append("## 环境")
    bits.append(f"- 版本: {version}")
    frozen = getattr(sys, "frozen", False)
    bits.append(f"- 运行方式: {'打包 exe' if frozen else '源码'}")
    bits.append(f"- Python: {sys.version.split()[0]}")
    bits.append(f"- Windows: {platform.platform()}")
    try:
        import ctypes
        u = ctypes.WinDLL("user32")
        bits.append(f"- 屏幕: {u.GetSystemMetrics(0)}x{u.GetSystemMetrics(1)}")
    except Exception:
        pass

    if app is not None:
        bits.append("")
        bits.append("## 状态")
        try:
            d = app.eng.dic
            n_words = len(getattr(d, "words", []) or [])
            if not n_words:
                n_words = len(d)
            bits.append(f"- 词表: {n_words} 词")
        except Exception:
            pass
        try:
            p = app.eng.predictor
            if p:
                bits.append(f"- 预测: 二元组 {len(p.bigram)} / 三元组 {len(p.trigram)}")
        except Exception:
            pass
        try:
            if app.examples is not None:
                bits.append(f"- 例句库: {len(app.examples)}")
        except Exception:
            pass
        try:
            bits.append(f"- 生词本: {len(app.wb)} 词 "
                        f"(待复习 {app.wb.review_stats()['due']})")
        except Exception:
            pass
        try:
            bits.append(f"- 候选字号: {app.bar.font_px}px · 主题: {app.cfg_theme}")
        except Exception:
            pass
        try:
            bits.append(f"- 服务状态: {'已暂停' if app.paused else '运行中'}")
        except Exception:
            pass

    bits.append("")
    bits.append("## 日志（已脱敏）")
    bits.append("```")
    tail = _tail(logpath)
    bits.extend(tail or ["(没有日志)"])
    bits.append("```")
    bits.append("")
    bits.append("<!-- 上面没有逐键记录和窗口标题；还有不想公开的内容就删掉再提交 -->")
    return "\n".join(bits)


def issue_url(report, title="问题反馈"):
    """预填 Issue 地址。正文只放摘要，完整日志由用户从剪贴板粘贴。"""
    import urllib.parse
    head = report.split("## 日志")[0].strip()
    if len(head) > 1200:
        head = head[:1200] + "\n…"
    body = head + "\n\n## 日志\n\n完整日志已复制到剪贴板，请粘贴在这里。\n"
    url = f"{ISSUE_URL}?{urllib.parse.urlencode({'title': title, 'body': body})}"
    if len(url) > 7500:
        url = (f"{ISSUE_URL}?{urllib.parse.urlencode({'title': title, 'body': '（日志见剪贴板）'})}")
    return url


def _copy_text(text):
    try:
        import win32clipboard as cb
        cb.OpenClipboard()
        try:
            cb.EmptyClipboard()
            cb.SetClipboardData(cb.CF_UNICODETEXT, text)
        finally:
            cb.CloseClipboard()
        return True
    except Exception:
        return False


def show_preview(root, report, url, title="反馈报告"):
    """让用户先看一遍再发：预览 + 复制 + 打开 GitHub。"""
    import tkinter as tk
    import tkinter.ttk as ttk
    import webbrowser

    win = tk.Toplevel(root)
    win.title(title)
    win.geometry("820x620+300+120")
    try:
        ttk.Style(win).theme_use("vista")
    except Exception:
        pass

    tk.Label(win, text="下面这些内容会被发到 GitHub。逐键记录和窗口标题已删除。",
             font=("Microsoft YaHei UI", 10)).pack(anchor="w", padx=12, pady=(10, 4))

    body = tk.Frame(win)
    body.pack(fill="both", expand=True, padx=12)
    sb = ttk.Scrollbar(body)
    sb.pack(side="right", fill="y")
    txt = tk.Text(body, font=("Consolas", 10), wrap="word", relief="solid",
                  bd=1, yscrollcommand=sb.set, padx=8, pady=8,
                  highlightthickness=0)
    txt.pack(side="left", fill="both", expand=True)
    sb.config(command=txt.yview)
    txt.insert("1.0", report)
    txt.config(state="disabled")

    bar = tk.Frame(win)
    bar.pack(fill="x", padx=12, pady=10)

    def do_copy(open_after):
        txt.config(state="normal")
        data = txt.get("1.0", "end").strip()
        txt.config(state="disabled")
        ok = _copy_text(data)
        if open_after:
            try:
                webbrowser.open(url)
            except Exception:
                pass
        win.destroy()
        return ok

    ttk.Button(bar, text="复制并打开 GitHub",
               command=lambda: do_copy(True)).pack(side="left")
    ttk.Button(bar, text="只复制",
               command=lambda: do_copy(False)).pack(side="left", padx=8)
    ttk.Button(bar, text="取消", command=win.destroy).pack(side="left")
    tk.Label(bar, text="GitHub 上是公开的", fg="#888",
             font=("Microsoft YaHei UI", 8)).pack(side="right")

    try:
        win.attributes("-topmost", True)
        win.lift()
        win.focus_force()
        win.after(400, lambda: win.attributes("-topmost", False))
    except Exception:
        pass
    return win
