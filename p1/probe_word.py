# -*- coding: utf-8 -*-
"""探测 Word 窗口的光标：Win32 caret 和 UIA TextPattern 哪条路可用。"""
import ctypes
import sys

sys.stdout.reconfigure(encoding="utf-8")
import win32gui
import win32process

sys.path.insert(0, "D:/Tools/俄语输入法/p1")
import probe
import probe_uia

user32 = ctypes.WinDLL("user32", use_last_error=True)

hits = []


def cb(h, _):
    try:
        if not win32gui.IsWindowVisible(h):
            return True
        n = win32gui.GetClassName(h)
        t = win32gui.GetWindowText(h)
        pid = win32process.GetWindowThreadProcessId(h)[0]
        try:
            import psutil
            name = psutil.Process(pid).name()
        except Exception:
            name = "?"
        if "WINWORD" in name.upper() and t.strip():
            hits.append((h, t, pid, n))
    except Exception:
        pass
    return True


win32gui.EnumWindows(cb, None)
print(f"找到 {len(hits)} 个 Word 窗口")
for h, t, pid, cls in hits:
    print(f"  hwnd={h:#x} pid={pid} cls={cls} title={t[:40]!r}")

if not hits:
    sys.exit(0)

h = hits[0][0]
fg = user32.GetForegroundWindow()
print(f"\n当前前台={fg:#x}  Word 是否前台={'是' if fg == h else '否'}")

print("\n--- 1) Win32 GetGUIThreadInfo ---")
s = probe.sample(h)
print(f"  caret = {s.get('caret') if s else None}")
print(f"  原因  = {s.get('why') if s else 'no sample'}")
print(f"  窗口矩形 = {s.get('wrect') if s else None}")

print("\n--- 2) UIA 焦点控件 ---")
try:
    import uiautomation as auto
    c = auto.GetFocusedControl()
    if c:
        print(f"  {c.ControlTypeName} cls={getattr(c,'ClassName','')!r} "
              f"name={getattr(c,'Name','')!r}")
        print(f"  BoundingRectangle = {c.BoundingRectangle}")
    else:
        print("  无焦点控件")
except Exception as e:
    print(f"  失败: {e}")
