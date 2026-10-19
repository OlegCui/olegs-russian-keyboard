# -*- coding: utf-8 -*-
"""
P1-b 输入捕获层：低级键盘钩子

要点：
  - WH_KEYBOARD_LL，独立线程 + 消息循环
  - **不吞键**：始终 CallNextHookEx，用户打字完全不受影响
  - 用 ToUnicodeEx 按「前台线程的键盘布局」转字符，俄语/英语都能拿到正确字符
  - 维护滚动缓冲，遇到分隔符（空格/回车/标点）就认为一个词结束，触发回调

安全：只读取按键，不拦截、不修改、不发送。用户感知为零。
"""
import ctypes
import sys
import threading
import time
from ctypes import wintypes as wt

sys.stdout.reconfigure(encoding="utf-8")

user32 = ctypes.WinDLL("user32", use_last_error=True)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104

VK_BACK = 0x08
VK_RETURN = 0x0D
VK_SPACE = 0x20
VK_TAB = 0x09
VK_PACKET = 0xE7

SEPARATORS = set(" \t\r\n.,;:!?()\"«»—–-/\\")

LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wt.WPARAM, wt.LPARAM)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wt.DWORD),
                ("scanCode", wt.DWORD),
                ("flags", wt.DWORD),
                ("time", wt.DWORD),
                ("dwExtraInfo", ctypes.POINTER(wt.ULONG))]


# ---- 显式声明签名，否则 64 位下 lParam 会被当成 32 位整型而溢出 ----
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wt.HINSTANCE, wt.DWORD]
user32.SetWindowsHookExW.restype = ctypes.c_void_p
user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wt.WPARAM, wt.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
user32.UnhookWindowsHookEx.restype = wt.BOOL
user32.GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT]
user32.GetMessageW.restype = ctypes.c_int
user32.TranslateMessage.argtypes = [ctypes.POINTER(wt.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wt.MSG)]
user32.DispatchMessageW.restype = LRESULT
user32.PostThreadMessageW.argtypes = [wt.DWORD, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.GetKeyboardLayout.argtypes = [wt.DWORD]
user32.GetKeyboardLayout.restype = ctypes.c_void_p
user32.ToUnicodeEx.argtypes = [wt.UINT, wt.UINT, ctypes.POINTER(ctypes.c_ubyte),
                               ctypes.c_wchar_p, ctypes.c_int, wt.UINT, ctypes.c_void_p]
user32.ToUnicodeEx.restype = ctypes.c_int
user32.GetForegroundWindow.restype = wt.HWND
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.GetWindowThreadProcessId.restype = wt.DWORD


class KeyboardCapture:
    def __init__(self, on_word=None, on_text=None, keep=300, debug=False,
                 require_lang=None, on_key=None, intercept=None):
        self.on_word = on_word
        self.on_text = on_text
        self.on_key = on_key          # 调试用：每个按键都回调（含被过滤掉的）
        self.intercept = intercept    # 返回 True = 吞掉这个键（候选条导航用）
        self.keep = keep
        self.debug = debug
        # 只在这些语言布局下工作。0x0419 = ru-RU。
        # 必须设：否则会和中文输入法抢输入（实测：拉丁字母会被中文 IME 转成汉字）
        self.require_lang = require_lang
        self.buffer = ""
        self._paused = False          # 注入文本时暂停，避免把自己发的键当成用户输入
        self._enabled = True          # 托盘里的总开关
        self._lock = threading.Lock()
        self._thread = None
        self._hook = None
        self._proc = None
        self._running = False

    def _lang_id(self):
        fg = user32.GetForegroundWindow()
        tid = user32.GetWindowThreadProcessId(fg, None)
        hkl = user32.GetKeyboardLayout(tid)
        return int(hkl) & 0xFFFF if hkl else 0

    def _char_of(self, vk, scan):
        state = (ctypes.c_ubyte * 256)()
        user32.GetKeyboardState(state)
        fg = user32.GetForegroundWindow()
        tid = user32.GetWindowThreadProcessId(fg, None)
        hkl = user32.GetKeyboardLayout(tid)
        buf = ctypes.create_unicode_buffer(8)
        n = user32.ToUnicodeEx(vk, scan, state, buf, 8, 0, hkl)
        if n == 1 and buf[0]:
            return buf[0]
        return ""

    def _push(self, ch):
        with self._lock:
            if ch:
                self.buffer = (self.buffer + ch)[-self.keep:]

    def _current_word(self):
        with self._lock:
            b = self.buffer
        i = len(b)
        while i > 0 and b[i - 1] not in SEPARATORS:
            i -= 1
        return b[i:]

    def _emit(self, word):
        if word and self.on_word:
            try:
                self.on_word(word)
            except Exception as e:
                print(f"[hook] on_word 异常: {e}", file=sys.stderr)

    def _fire_text(self):
        if self.on_text:
            with self._lock:
                t = self.buffer
            try:
                self.on_text(t)
            except Exception:
                pass

    def _on_key(self, vk, scan):
        if self._paused or not self._enabled:
            return False
        lid = self._lang_id()
        # VK_PACKET：Unicode 注入（别的输入法/宏/远程桌面发出的文本），
        # 字符直接放在 scanCode 里，ToUnicodeEx 对它无效。
        if vk == VK_PACKET and scan:
            ch = chr(scan) if 0 < scan < 0x110000 else ""
        else:
            ch = self._char_of(vk, scan)
        if self.on_key:
            try:
                self.on_key(vk, scan, lid, ch)
            except Exception:
                pass
        if self.intercept is not None:
            try:
                if self.intercept(vk):
                    return True
            except Exception:
                pass
        if self.require_lang is not None and lid != self.require_lang:
            # 容错：布局 ID 对不上时，只要转出来是西里尔字母也放行。
            # 有些宿主（Electron/微信）报上来的布局 ID 可能不是 0x0419，
            # 但字符是对的，按字符判断更可靠。
            if not (ch and "\u0400" <= ch <= "\u04FF"):
                return
        if vk == VK_BACK:
            with self._lock:
                self.buffer = self.buffer[:-1]
            self._fire_text()
            return
        if vk in (VK_RETURN, VK_SPACE, VK_TAB):
            self._emit(self._current_word())
            self._push(" " if vk == VK_SPACE else "\n")
            self._fire_text()
            return
        if not ch:
            return
        if self.debug:
            print(f"[hook] vk={vk} -> {ch!r}", file=sys.stderr)
        if ch in SEPARATORS:
            self._emit(self._current_word())
        self._push(ch)
        self._fire_text()

    def _loop(self):
        def proc(nCode, wParam, lParam):
            # 低层钩子的标准写法：nCode<0 必须转交；其余处理完显式返回 0 = 放行
            if nCode < 0:
                return user32.CallNextHookEx(None, nCode, wParam, lParam)
            swallow = False
            try:
                if wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                    kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                    swallow = bool(self._on_key(int(kb.vkCode), int(kb.scanCode)))
            except Exception as e:
                print(f"[hook] proc 异常: {e}", file=sys.stderr)
            return 1 if swallow else 0

        self._proc = HOOKPROC(proc)
        self._hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, None, 0)
        if not self._hook:
            print(f"[hook] 安装失败 err={ctypes.get_last_error()}", file=sys.stderr)
            return
        self._running = True
        msg = wt.MSG()
        while self._running:
            r = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if r in (0, -1):
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        user32.UnhookWindowsHookEx(self._hook)
        self._hook = None

    def start(self):
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        for _ in range(50):
            if self._hook:
                return True
            time.sleep(0.02)
        return bool(self._hook)

    def stop(self):
        self._running = False
        try:
            user32.PostThreadMessageW(self._thread.ident, 0x0012, 0, 0)  # WM_QUIT
        except Exception:
            pass

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def set_enabled(self, on):
        self._enabled = bool(on)


if __name__ == "__main__":
    words = []
    cap = KeyboardCapture(on_word=lambda w: (words.append(w), print(f"[word] {w}")))
    if not cap.start():
        print("钩子安装失败")
        sys.exit(1)
    print("钩子已启动，10 秒内随便打字（Ctrl+C 结束）…")
    try:
        t0 = time.time()
        while time.time() - t0 < 10:
            time.sleep(0.3)
    except KeyboardInterrupt:
        pass
    cap.stop()
    print(f"捕获到的词: {words}")
