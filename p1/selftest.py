# -*- coding: utf-8 -*-
"""
P1-a 自测 v4（安全 + 双通路）

安全铁律：
  - 绝不向未经确认属于目标的坐标发点击
  - 点击前用 WindowFromPoint 校验：该点下的根窗口必须就是目标窗口，否则跳过
  - 绝不向用户已存在的窗口输入任何内容

两条通路同时测：
  Win32 = GetGUIThreadInfo 的 caret
  UIA   = TextPattern 选区矩形
"""
import os
import subprocess
import sys
import tempfile
import time

sys.stdout.reconfigure(encoding="utf-8")
import win32con
import win32gui
import win32process
from pynput.keyboard import Controller as Kb
from pynput.mouse import Button, Controller as Ms

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import probe
import probe_uia

kb = Kb()
ms = Ms()


def snapshot():
    s = set()

    def cb(h, _):
        s.add(h)
        return True

    win32gui.EnumWindows(cb, None)
    return s


def safe_click(hwnd, x, y):
    """只有确认该坐标落在 hwnd 上才点击。返回是否点了。"""
    try:
        under = win32gui.WindowFromPoint((int(x), int(y)))
        root = win32gui.GetAncestor(under, win32con.GA_ROOT)
    except Exception as e:
        print(f"    校验失败，放弃点击: {e}")
        return False
    if root != hwnd:
        print(f"    ⛔ 坐标 ({int(x)},{int(y)}) 下是 {root:#x}，不是目标 {hwnd:#x}，放弃点击")
        return False
    ms.position = (int(x), int(y))
    time.sleep(0.2)
    ms.click(Button.left, 1)
    time.sleep(0.45)
    return True


def find_new(before, pids, hint=None, min_w=200, cls_contains=None):
    found = []

    def cb(h, _):
        try:
            if h in before or not win32gui.IsWindowVisible(h):
                return True
            p = win32process.GetWindowThreadProcessId(h)[0]
            if pids is not None and p not in pids:
                return True
            l, t, r, b = win32gui.GetWindowRect(h)
            if (r - l) < min_w or (b - t) < 120:
                return True
            if hint and hint.lower() not in win32gui.GetWindowText(h).lower():
                return True
            if cls_contains and cls_contains not in win32gui.GetClassName(h):
                return True
            found.append(h)
        except Exception:
            pass
        return True

    win32gui.EnumWindows(cb, None)
    return found[0] if found else None


def pid_tree(pid):
    """用 psutil 取进程树（Win11 24H2 已移除 wmic，不能再用它）。"""
    out = {pid}
    try:
        import psutil
        p = psutil.Process(pid)
        for c in p.children(recursive=True):
            out.add(c.pid)
    except Exception as e:
        print(f"    (psutil 取进程树失败: {e})")
    return out


def measure(hwnd, tag):
    w = probe.sample(hwnd)
    u, uw = probe_uia.caret()
    print(f"  [{tag}] Win32: {w.get('caret') if w else None}"
          + ("" if (w and w.get("caret")) else f"  ({w.get('why') if w else 'no window'})"))
    print(f"  [{tag}] UIA  : {u}  ({uw or 'ok'})")
    return w.get("caret") if w else None, u, uw


def verdict(w1, w2, u1, u2, uw):
    v = []
    if w1 and w2:
        dx = w2["x"] - w1["x"]
        v.append(f"Win32 {'PASS' if dx > 5 else 'FAIL'}(dx={dx})")
    else:
        v.append("Win32 FAIL(no caret)")
    if u1 and u2:
        dx = u2["x"] - u1["x"]
        v.append(f"UIA {'PASS' if dx > 5 else 'FAIL'}(dx={dx})")
    else:
        v.append(f"UIA FAIL({uw})")
    return v


def main():
    print("P1-a 自测 v4（点击前校验坐标归属）")
    out = []

    # ---------- 1) 自建 Tk 窗口：用 topmost 置顶，不靠点击 ----------
    import tkinter as tk

    before = snapshot()
    root = tk.Tk()
    root.title("caret-selftest-c4d1")
    root.geometry("660x200+340+300")
    ent = tk.Entry(root, font=("Consolas", 22), width=44)
    ent.pack(padx=24, pady=52)
    root.attributes("-topmost", True)
    root.update()
    root.lift()
    root.focus_force()
    time.sleep(0.9)
    try:
        hwnd = find_new(before, None, hint="caret-selftest-c4d1")
        fg = win32gui.GetForegroundWindow()
        print(f"\n=== Tk(对照) ===\n  目标={hwnd and hex(hwnd)}  前台={hex(fg)}")
        if not hwnd:
            out.append(("Tk(对照)", ["SKIP: no window"]))
        elif fg != hwnd:
            out.append(("Tk(对照)", [f"SKIP: 焦点未拿到(前台={win32gui.GetWindowText(fg)[:24]!r})"]))
            print("  ⛔ 焦点不在自建窗口，跳过（不让 AAAAA 打到别处）")
        else:
            kb.type("AAAAA")
            root.update()
            time.sleep(0.6)
            w1, u1, uw1 = measure(hwnd, "1")
            kb.type("BBBBB")
            root.update()
            time.sleep(0.6)
            w2, u2, uw2 = measure(hwnd, "2")
            v = verdict(w1, w2, u1, u2, uw2 or uw1)
            print("  → " + " | ".join(v))
            out.append(("Tk(对照)", v))
    finally:
        try:
            root.destroy()
        except Exception:
            pass

    # ---------- 2) Edge ----------
    edge = None
    for c in [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]:
        if os.path.exists(c):
            edge = c
            break
    if not edge:
        out.append(("Edge/Chromium", ["SKIP: no msedge.exe"]))
    else:
        print("\n=== Edge/Chromium ===")
        td = tempfile.mkdtemp(prefix="edgeprobe_")
        html = os.path.join(td, "t.html")
        with open(html, "w", encoding="utf-8") as fh:
            fh.write("<body style='margin:50px' onload=\"document.getElementById('q').focus()\">"
                     "<input id=q style='font:30px monospace;width:900px;padding:14px;"
                     "border:3px solid #666'></body>")
        before = snapshot()
        p = subprocess.Popen([edge, "--user-data-dir=" + td, "--no-first-run",
                              "--disable-features=msEdgeFirstRunExperience",
                              "--new-window", "file:///" + html.replace("\\", "/")])
        try:
            time.sleep(7.0)
            pids = pid_tree(p.pid)
            print(f"    进程树 {len(pids)} 个 pid")
            hwnd = find_new(before, pids, min_w=300)
            if not hwnd:
                hwnd = find_new(before, None, min_w=300, cls_contains="Chrome_WidgetWin")
                if hwnd:
                    print(f"    (按 Chromium 窗口类兜底命中 {hwnd:#x})")
            if not hwnd:
                print("  找不到新窗口")
                out.append(("Edge/Chromium", ["SKIP: no new window"]))
            else:
                l, t, r, b = win32gui.GetWindowRect(hwnd)
                clicked = safe_click(hwnd, l + (r - l) / 2, t + 12)
                fg = win32gui.GetForegroundWindow()
                print(f"  点击={clicked}  前台={win32gui.GetWindowText(fg)[:36]!r}")
                if fg != hwnd:
                    print("  ⛔ 焦点不在 Edge，跳过输入")
                    out.append(("Edge/Chromium", ["SKIP: focus not acquired"]))
                else:
                    kb.type("AAAAA")
                    time.sleep(0.6)
                    w1, u1, uw1 = measure(hwnd, "1")
                    kb.type("BBBBB")
                    time.sleep(0.6)
                    w2, u2, uw2 = measure(hwnd, "2")
                    v = verdict(w1, w2, u1, u2, uw2 or uw1)
                    print("  → " + " | ".join(v))
                    out.append(("Edge/Chromium", v))
        finally:
            try:
                p.terminate()
            except Exception:
                pass
            time.sleep(1.0)

    print("\n" + "=" * 66)
    print("汇总")
    for name, v in out:
        print(f"  {name:18}{' | '.join(v)}")
    print("=" * 66)


if __name__ == "__main__":
    main()
