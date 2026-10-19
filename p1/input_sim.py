# -*- coding: utf-8 -*-
"""
输入注入层：把文本"打"进当前前台程序。

两条路径：
  主路径 SendInput + KEYEVENTF_UNICODE —— 直接注入 Unicode 字符，不受键盘布局影响
  兜底   剪贴板 + Ctrl+V —— 某些程序（远程桌面、部分游戏）不认 Unicode 注入

本模块只负责"发"，不关心发到哪里。
"""
import ctypes
import sys
import time
from ctypes import wintypes as wt

sys.stdout.reconfigure(encoding="utf-8")

user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

VK_BACK = 0x08
VK_CONTROL = 0x11
VK_V = 0x56


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD),
                ("dwFlags", wt.DWORD), ("time", wt.DWORD),
                ("dwExtraInfo", ctypes.POINTER(wt.ULONG))]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.POINTER(wt.ULONG))]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wt.DWORD), ("wParamL", wt.WORD), ("wParamH", wt.WORD)]


class _UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wt.DWORD), ("u", _UNION)]


user32.SendInput.argtypes = [wt.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wt.UINT


def _key(vk=0, scan=0, flags=0):
    i = INPUT()
    i.type = INPUT_KEYBOARD
    i.u.ki.wVk = vk
    i.u.ki.wScan = scan
    i.u.ki.dwFlags = flags
    i.u.ki.time = 0
    i.u.ki.dwExtraInfo = None
    return i


def _send(items):
    n = len(items)
    arr = (INPUT * n)(*items)
    sent = user32.SendInput(n, arr, ctypes.sizeof(INPUT))
    return sent == n


def send_backspaces(count):
    if count <= 0:
        return True
    items = []
    for _ in range(count):
        items.append(_key(VK_BACK, 0, 0))
        items.append(_key(VK_BACK, 0, KEYEVENTF_KEYUP))
    return _send(items)


def send_vk(vk, scan=0):
    """发送真实虚拟键码（不是 VK_PACKET 的 Unicode 包）。

    钩子能通过 ToUnicodeEx 按当前布局把它转成字符，所以测试必须走这条路。
    """
    ok1 = _send([_key(vk, scan, 0)])
    time.sleep(0.005)
    ok2 = _send([_key(vk, scan, KEYEVENTF_KEYUP)])
    return ok1 and ok2


def send_text(text):
    """逐字符 Unicode 注入，不依赖当前键盘布局。"""
    if not text:
        return True
    items = []
    for ch in text:
        if ch == "\n":
            items.append(_key(0x0D, 0, 0))
            items.append(_key(0x0D, 0, KEYEVENTF_KEYUP))
            continue
        code = ord(ch)
        items.append(_key(0, code, KEYEVENTF_UNICODE))
        items.append(_key(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP))
    # 分批发送，避免超长文本一次塞爆
    ok = True
    for i in range(0, len(items), 64):
        ok = _send(items[i:i + 64]) and ok
        time.sleep(0.005)
    return ok


def replace_tail(backspaces, text):
    ok1 = send_backspaces(backspaces)
    time.sleep(0.02)
    ok2 = send_text(text)
    return ok1 and ok2


def paste_text(text):
    """兜底方案：剪贴板 + Ctrl+V，结束后恢复原剪贴板。"""
    try:
        import win32clipboard
        import win32con

        win32clipboard.OpenClipboard()
        try:
            old = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
        except Exception:
            old = None
        win32clipboard.CloseClipboard()

        def put(s):
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, s)
            win32clipboard.CloseClipboard()

        put(text)
        _send([_key(VK_CONTROL, 0, 0), _key(VK_V, 0, 0),
               _key(VK_V, 0, KEYEVENTF_KEYUP), _key(VK_CONTROL, 0, KEYEVENTF_KEYUP)])
        time.sleep(0.12)
        if old is not None:
            put(old)
        return True
    except Exception as e:
        print(f"[input] paste 失败: {e}", file=sys.stderr)
        return False
