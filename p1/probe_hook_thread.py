# -*- coding: utf-8 -*-
"""在钩子线程内部打印 ToUnicodeEx 的真实返回，定位 _char_of 失效原因。"""
import ctypes
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "D:/Tools/俄语输入法/p1")
import input_sim
from hook import KeyboardCapture, user32


def cb(vk, scan, lang, ch):
    state = (ctypes.c_ubyte * 256)()
    r = user32.GetKeyboardState(state)
    fg = user32.GetForegroundWindow()
    tid = user32.GetWindowThreadProcessId(fg, None)
    hkl = user32.GetKeyboardLayout(tid)
    buf = ctypes.create_unicode_buffer(8)
    n = user32.ToUnicodeEx(vk, scan, state, buf, 8, 0, hkl)
    err = ctypes.get_last_error()
    print(f"  [hook线程] vk=0x{vk:02X} scan=0x{scan:02X} "
          f"lang=0x{lang:04X} hkl=0x{(hkl or 0):X} "
          f"GetKeyboardState={r} ToUnicodeEx.n={n} ch={ch!r} err={err}",
          flush=True)


cap = KeyboardCapture(require_lang=None, on_key=cb)
print("安装钩子:", cap.start())
time.sleep(0.5)
print("发送两次 L 键 …")
for _ in range(2):
    input_sim.send_vk(0x4C)
    time.sleep(0.25)
time.sleep(0.8)
cap.stop()
print("done")
