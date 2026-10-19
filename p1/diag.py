# -*- coding: utf-8 -*-
"""
诊断工具：搞清楚"为什么打了俄语没反应"

两种模式：
  --static   不交互，列出已安装键盘布局、显示器、当前前台控件（我可以自己跑）
  --capture  交互 8 秒，记录你敲的每个键：布局 ID、转出的字符、缓冲区（需要你跑）
"""
import argparse
import ctypes
import sys
import time
from ctypes import wintypes as wt

sys.stdout.reconfigure(encoding="utf-8")

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.GetKeyboardLayoutList.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
user32.GetKeyboardLayoutList.restype = ctypes.c_int

LANG_NAMES = {
    0x0409: "英语(美国)", 0x0419: "俄语", 0x0804: "中文(简体,中国)",
    0x0404: "中文(繁体,台湾)", 0x0411: "日语", 0x0412: "韩语",
    0x0407: "德语", 0x040C: "法语", 0x040A: "西班牙语",
}


def layouts():
    n = user32.GetKeyboardLayoutList(0, None)
    arr = (ctypes.c_void_p * n)()
    user32.GetKeyboardLayoutList(n, arr)
    out = []
    for h in arr:
        if not h:
            continue
        langid = h & 0xFFFF
        out.append((h, langid, LANG_NAMES.get(langid, f"未知(0x{langid:04X})")))
    return out


def current_lang():
    fg = user32.GetForegroundWindow()
    tid = user32.GetWindowThreadProcessId(fg, None)
    hkl = user32.GetKeyboardLayout(tid)
    return (hkl & 0xFFFF) if hkl else 0


def monitors():
    out = []

    def cb(hmon, hdc, rect, data):
        r = rect.contents
        out.append((r.left, r.top, r.right, r.bottom))
        return 1

    MONITORENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_int, wt.HMONITOR, wt.HDC,
                                         ctypes.POINTER(wt.RECT), wt.LPARAM)
    user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(cb), 0)
    return out


def static():
    print("=" * 58)
    print("1) 已安装的键盘布局")
    print("=" * 58)
    ls = layouts()
    has_ru = False
    for h, langid, name in ls:
        mark = ""
        if langid == 0x0419:
            has_ru = True
            mark = "  ← 俄语，有"
        print(f"  0x{langid:04X}  {name:20} hkl=0x{h:X}{mark}")
    if not has_ru:
        print("\n  ❌ 没有俄语布局！这就是没反应的原因。")
        print("     解决：设置 → 时间和语言 → 语言和区域 → 添加语言 → 俄语")

    print("\n" + "=" * 58)
    print("2) 显示器")
    print("=" * 58)
    for i, m in enumerate(monitors()):
        print(f"  #{i}: {m}  尺寸 {m[2]-m[0]}x{m[3]-m[1]}")

    print("\n" + "=" * 58)
    print("3) 当前前台窗口 / 布局 / 焦点控件")
    print("=" * 58)
    fg = user32.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(fg, buf, 256)
    print(f"  前台窗口: {buf.value[:40]!r}")
    lid = current_lang()
    print(f"  当前布局: 0x{lid:04X}  {LANG_NAMES.get(lid, '未知')}")
    try:
        import uiautomation as auto
        c = auto.GetFocusedControl()
        if c:
            r = c.BoundingRectangle
            print(f"  焦点控件: {c.ControlTypeName} rect={r}")
        else:
            print("  焦点控件: 无")
    except Exception as e:
        print(f"  焦点控件查询失败: {e}")


def capture(seconds=8):
    sys.path.insert(0, "D:/Tools/俄语输入法/p1")
    import hook as hook_mod

    print("=" * 58)
    print(f"请在 {seconds} 秒内：点进记事本 → 切俄语布局 → 打几个俄语词")
    print("=" * 58)

    seen = []
    orig = hook_mod.KeyboardCapture._on_key

    def traced(self, vk, scan):
        lid = self._lang_id()
        ch = self._char_of(vk, scan)
        seen.append((vk, scan, lid, ch))
        print(f"  vk=0x{vk:02X} scan=0x{scan:02X} lang=0x{lid:04X} char={ch!r}")
        return orig(self, vk, scan)

    hook_mod.KeyboardCapture._on_key = traced

    cap = hook_mod.KeyboardCapture(require_lang=None)
    if not cap.start():
        print("钩子安装失败")
        return
    try:
        t0 = time.time()
        while time.time() - t0 < seconds:
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    cap.stop()

    print("\n" + "=" * 58)
    print("4) 结果")
    print("=" * 58)
    print(f"  捕获按键 {len(seen)} 个")
    print(f"  缓冲区   {cap.buffer!r}")
    lset = sorted({x[2] for x in seen})
    print(f"  出现的布局 ID: {[f'0x{x:04X}' for x in lset]}")
    if 0x0419 not in lset:
        print("\n  ❌ 打字期间没有出现 0x0419（俄语）布局")
        print("     → 说明当时布局不是俄语，或被 0x0419 以外的俄语变体占用")
    else:
        print("\n  ✅ 出现了俄语布局，钩子能读到")
    cyr = [x[3] for x in seen if x[3] and "\u0400" <= x[3] <= "\u04FF"]
    if not cyr:
        print("  ⚠ 但没有任何西里尔字符被转出 → ToUnicodeEx 转换失败")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--static", action="store_true")
    ap.add_argument("--capture", action="store_true")
    ap.add_argument("--seconds", type=int, default=8)
    a = ap.parse_args()
    if a.capture:
        capture(a.seconds)
    else:
        static()


if __name__ == "__main__":
    main()
