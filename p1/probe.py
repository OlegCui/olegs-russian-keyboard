# -*- coding: utf-8 -*-
"""
光标位置探针（P1-a 核心）

目的：在真实应用里，能不能稳定拿到「输入光标」的屏幕坐标。
方法：纯轮询（不挂键盘钩子，零侵入、零杀软风险），每 100ms 读一次前台窗口，
      用 GetGUIThreadInfo 取 caret，再 ClientToScreen 换算成屏幕坐标。

两种用法：
  python probe.py --duration 180 --out log.jsonl     # 采集（给用户跑）
  from probe import sample                            # 被 selftest 调用
"""
import argparse
import ctypes
import json
import os
import sys
import time
from ctypes import wintypes as wt

sys.stdout.reconfigure(encoding="utf-8")

user32 = ctypes.WinDLL("user32", use_last_error=True)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.DWORD),
        ("flags", wt.DWORD),
        ("hwndActive", wt.HWND),
        ("hwndFocus", wt.HWND),
        ("hwndCapture", wt.HWND),
        ("hwndMenuOwner", wt.HWND),
        ("hwndMoveSize", wt.HWND),
        ("hwndCaret", wt.HWND),
        ("rcCaret", wt.RECT),
    ]


def _exe_of(pid):
    h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return "?"
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wt.DWORD(1024)
        if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value)
        return "?"
    finally:
        k32.CloseHandle(h)


def _cls_of(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _title_of(hwnd):
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _pid_of(hwnd):
    pid = wt.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def window_rect(hwnd):
    r = wt.RECT()
    if user32.GetWindowRect(hwnd, ctypes.byref(r)):
        return (r.left, r.top, r.right, r.bottom)
    return None


def sample(hwnd=None):
    """返回一次采样；拿不到 caret 时 caret 字段为 None，但窗口信息仍然返回。"""
    fg = hwnd or user32.GetForegroundWindow()
    if not fg:
        return None
    pid = _pid_of(fg)
    tid = user32.GetWindowThreadProcessId(fg, None)
    out = {
        "t": round(time.time(), 3),
        "hwnd": fg,
        "pid": pid,
        "exe": _exe_of(pid),
        "cls": _cls_of(fg),
        "title": _title_of(fg)[:40],
        "wrect": window_rect(fg),
        "caret": None,
        "why": None,
    }
    gti = GUITHREADINFO()
    gti.cbSize = ctypes.sizeof(GUITHREADINFO)
    if not user32.GetGUIThreadInfo(tid, ctypes.byref(gti)):
        out["why"] = f"GetGUIThreadInfo failed err={ctypes.get_last_error()}"
        return out
    if not gti.hwndCaret:
        out["why"] = "hwndCaret=0(该线程没有可见光标)"
        return out
    pt = wt.POINT(gti.rcCaret.left, gti.rcCaret.top)
    if not user32.ClientToScreen(gti.hwndCaret, ctypes.byref(pt)):
        out["why"] = "ClientToScreen failed"
        return out
    out["caret"] = {
        "hwnd": gti.hwndCaret,
        "x": pt.x,
        "y": pt.y,
        "h": gti.rcCaret.bottom - gti.rcCaret.top,
    }
    return out


def summarize(samples):
    """按 exe 聚合：多少次采样有有效 caret、坐标是否落在窗口内。"""
    agg = {}
    for s in samples:
        if not s:
            continue
        e = agg.setdefault(s["exe"], {"n": 0, "ok": 0, "xs": set(), "inside": 0, "why": {}})
        e["n"] += 1
        c = s["caret"]
        if not c:
            if s.get("why"):
                e["why"][s["why"]] = e["why"].get(s["why"], 0) + 1
            continue
        e["ok"] += 1
        e["xs"].add((c["x"], c["y"]))
        wr = s.get("wrect")
        if wr and wr[0] <= c["x"] <= wr[2] and wr[1] <= c["y"] <= wr[3]:
            e["inside"] += 1
    rows = []
    for exe, e in sorted(agg.items(), key=lambda kv: -kv[1]["n"]):
        rows.append({
            "exe": exe,
            "samples": e["n"],
            "caret_ok": e["ok"],
            "ok_rate": round(e["ok"] / e["n"] * 100, 1) if e["n"] else 0,
            "distinct_pos": len(e["xs"]),
            "inside_window": e["inside"],
            "top_reason": max(e["why"], key=e["why"].get) if e["why"] else "",
        })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--duration", type=int, default=180)
    ap.add_argument("--out", default="caret_log.jsonl")
    ap.add_argument("--interval", type=float, default=0.1)
    a = ap.parse_args()

    print("=" * 60)
    print(" 光标探针已启动")
    print(f" 采集 {a.duration} 秒，每 {a.interval}s 采样一次")
    print("")
    print(" 请依次做：")
    print("   1. 切到 Word 或记事本，打几个字")
    print("   2. 切到 Chrome，点进网页里的输入框，打几个字")
    print("   3. 切到微信/QQ 聊天框，打几个字")
    print("   4. 每隔 5 秒随便切一下窗口")
    print("")
    print(" 到时间会自动结束；也可直接按 Ctrl+C 提前结束。")
    print("=" * 60)

    samples = []
    last_key = None
    t0 = time.time()
    try:
        while time.time() - t0 < a.duration:
            s = sample()
            if s:
                key = (s["hwnd"], s["caret"]["x"] if s["caret"] else None,
                       s["caret"]["y"] if s["caret"] else None)
                if key != last_key:          # 去重：只在变化时记录
                    samples.append(s)
                    last_key = key
            time.sleep(a.interval)
    except KeyboardInterrupt:
        print("\n手动结束。")

    with open(a.out, "w", encoding="utf-8") as fh:
        for s in samples:
            fh.write(json.dumps(s, ensure_ascii=False) + "\n")

    print(f"\n采样点 {len(samples)} 条 -> {a.out}")
    rows = summarize(samples)
    if not rows:
        print("没有采到任何窗口。")
        return
    print(f"\n{'exe':22}{'samples':>9}{'caret_ok':>10}{'rate%':>7}{'pos':>6}{'in_win':>8}  原因")
    for r in rows:
        print(f"{r['exe']:22}{r['samples']:>9}{r['caret_ok']:>10}"
              f"{r['ok_rate']:>7}{r['distinct_pos']:>6}{r['inside_window']:>8}  {r['top_reason']}")
    print("\n判读标准：")
    print("  rate% 高 + pos>1  = 该应用能拿到光标（可用）")
    print("  rate% 0            = 该应用拿不到（需要 UIA 兜底）")


if __name__ == "__main__":
    main()
