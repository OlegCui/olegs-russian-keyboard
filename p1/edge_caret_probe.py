# -*- coding: utf-8 -*-
"""
Edge/Chromium 光标专项探测

已知：Chromium 的空选区（就是光标）调用 GetBoundingRectangles() 返回空数组。
候选解法：
  A. ExpandToEnclosingUnit(Character)  → 扩到整字，取该字矩形
  B. MoveEndpointByUnit(Start, Character, -1) → 向左扩一个字
  C. 取 GetVisibleRanges 首块

本脚本把三种都试一遍，打印实际返回，确定哪种在 Edge 上可用。
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

import uiautomation as auto

kb = Kb()
ms = Ms()
PID_TP1 = auto.PatternId.TextPattern


def snapshot():
    s = set()

    def cb(h, _):
        s.add(h)
        return True

    win32gui.EnumWindows(cb, None)
    return s


def find_new(before, cls_contains, min_w=300):
    cands = []

    def cb(h, _):
        try:
            if h in before or not win32gui.IsWindowVisible(h):
                return True
            l, t, r, b = win32gui.GetWindowRect(h)
            if (r - l) < min_w or cls_contains not in win32gui.GetClassName(h):
                return True
            title = win32gui.GetWindowText(h)
            if not title.strip():          # 无标题的多半是宿主/隐藏窗口
                return True
            cands.append(((r - l) * (b - t), h, title))
        except Exception:
            pass
        return True

    win32gui.EnumWindows(cb, None)
    if not cands:
        return None
    cands.sort(reverse=True)               # 取面积最大的那一个
    print(f"    候选窗口 {len(cands)} 个，最大: {cands[0][2][:40]!r}")
    return cands[0][1]


def safe_click(hwnd, x, y):
    under = win32gui.WindowFromPoint((int(x), int(y)))
    if win32gui.GetAncestor(under, win32con.GA_ROOT) != hwnd:
        print("    ⛔ 坐标不属于目标窗口，放弃点击")
        return False
    ms.position = (int(x), int(y))
    time.sleep(0.2)
    ms.click(Button.left, 1)
    time.sleep(0.5)
    return True


def nums(obj):
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
        out.extend(nums(x))
    return out


def show(tag, rng):
    try:
        raw = rng.GetBoundingRectangles()
    except Exception as e:
        print(f"  {tag}: rects_error {e}")
        return
    n = nums(raw)
    print(f"  {tag}: len={len(n)}  raw={n[:12]}")

    for meth, args in [
        ("ExpandToEnclosingUnit", (auto.TextUnit.Character,)),
        ("MoveEndpointByUnit", (auto.TextPatternRangeEndpoint.Start, auto.TextUnit.Character, -1)),
    ]:
        fn = getattr(rng, meth, None)
        if fn is None:
            print(f"    {meth}: 不存在")
            continue
        try:
            r2 = rng.Clone() if hasattr(rng, "Clone") else rng
        except Exception:
            r2 = rng
        try:
            ret = fn(*args) if r2 is rng else getattr(r2, meth)(*args)
            n2 = nums(r2.GetBoundingRectangles())
            print(f"    {meth}{args} -> ret={ret}  len={len(n2)}  {n2[:8]}")
        except Exception as e:
            print(f"    {meth}: 失败 {e}")


def main():
    edge = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    if not os.path.exists(edge):
        print("没有 Edge")
        return
    td = tempfile.mkdtemp(prefix="edgecaret_")
    html = os.path.join(td, "t.html")
    with open(html, "w", encoding="utf-8") as fh:
        fh.write("<body style='margin:60px' onload=\"document.getElementById('q').focus()\">"
                 "<input id=q style='font:32px monospace;width:900px;padding:16px;"
                 "border:3px solid #666'></body>")
    before = snapshot()
    p = subprocess.Popen([edge, "--user-data-dir=" + td, "--no-first-run",
                          "--no-default-browser-check", "--disable-sync",
                          "--disable-features=msEdgeFirstRunExperience,msEdgeSyncPromo,"
                          "msEdgeBrowserSignInPromo,msEdgeIdentityFeatures",
                          "--force-renderer-accessibility",
                          "--new-window", "file:///" + html.replace("\\", "/")])
    try:
        time.sleep(7.0)
        from pynput.keyboard import Key
        for _ in range(3):                    # 关掉可能弹出的首启/同步对话框
            kb.press(Key.esc)
            kb.release(Key.esc)
            time.sleep(0.6)
        hwnd = find_new(before, "Chrome_WidgetWin")
        if not hwnd:
            print("找不到 Edge 窗口")
            return
        print(f"Edge 窗口 {hwnd:#x} 标题={win32gui.GetWindowText(hwnd)[:40]!r}")
        l, t, r, b = win32gui.GetWindowRect(hwnd)
        if not safe_click(hwnd, l + (r - l) / 2, t + 12):
            return
        fg = win32gui.GetForegroundWindow()
        print(f"点击后前台: hwnd={fg:#x} cls={win32gui.GetClassName(fg)!r} "
              f"title={win32gui.GetWindowText(fg)[:36]!r}")
        if fg != hwnd:
            print("  前台不是目标窗口，改点页面中心")
            safe_click(hwnd, l + (r - l) / 2, t + (b - t) / 2)
            fg = win32gui.GetForegroundWindow()
            print(f"  再试前台: hwnd={fg:#x} title={win32gui.GetWindowText(fg)[:36]!r}")

        kb.type("AAAAA")
        time.sleep(0.8)
        c = auto.GetFocusedControl()
        print(f"\n焦点控件: {c.ControlTypeName} cls={getattr(c,'ClassName','')!r} "
              f"name={getattr(c,'Name','')!r}")

        tp = c.GetPattern(PID_TP1)
        print(f"TextPattern: {tp}")
        if tp is None:
            print("该控件没有 TextPattern —— 换焦点控件或判定为不支持")
            return

        sel = tp.GetSelection()
        print(f"GetSelection -> {type(sel)} len={len(sel) if sel else 0}")
        if sel:
            rng = sel[-1] if isinstance(sel, (list, tuple)) else sel
            print("选区方法:", [m for m in dir(rng) if not m.startswith('_')])
            show("selection", rng)

            # 关键兜底：即使拿不到光标矩形，控件本身有矩形
            try:
                print(f"\n控件 BoundingRectangle = {c.BoundingRectangle}")
            except Exception as e:
                print("BoundingRectangle 失败:", e)
            try:
                print(f"range.GetText(-1) = {rng.GetText(-1)!r}")
            except Exception as e:
                print("GetText 失败:", e)
            try:
                rng.ScrollIntoView(True)
                n = nums(rng.GetBoundingRectangles())
                print(f"ScrollIntoView 后 rects len={len(n)} {n[:8]}")
            except Exception as e:
                print("ScrollIntoView 失败:", e)

        try:
            vr = tp.GetVisibleRanges()
            print(f"\nGetVisibleRanges -> {len(vr)} 块")
            if vr:
                show("visible[0]", vr[0])
        except Exception as e:
            print("GetVisibleRanges 失败:", e)

        kb.type("BBBBB")
        time.sleep(0.8)
        sel2 = tp.GetSelection()
        if sel2:
            rng2 = sel2[-1] if isinstance(sel2, (list, tuple)) else sel2
            show("selection(打完后)", rng2)
    finally:
        try:
            p.terminate()
        except Exception:
            pass


if __name__ == "__main__":
    main()
