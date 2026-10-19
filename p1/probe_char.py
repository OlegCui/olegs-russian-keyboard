# -*- coding: utf-8 -*-
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "D:/Tools/俄语输入法/p1")
import ctypes
from hook import KeyboardCapture, user32

cap = KeyboardCapture(require_lang=None)
fg = user32.GetForegroundWindow()
tid = user32.GetWindowThreadProcessId(fg, None)
print(f"前台 hwnd={fg:#x} tid={tid}")
print(f"_lang_id() = 0x{cap._lang_id():04X}")
print(f"GetKeyboardLayout(tid) = 0x{(user32.GetKeyboardLayout(tid) or 0):X}")
print()

state = (ctypes.c_ubyte * 256)()
r = user32.GetKeyboardState(state)
print(f"GetKeyboardState ret={r}  前 8 字节={[state[i] for i in range(8)]}")
print()

hkl = user32.GetKeyboardLayout(tid)
for vk, name in [(0x4C, "L"), (0x48, "H"), (0x45, "E"), (0x55, "U"), (0x20, "SPACE")]:
    buf = ctypes.create_unicode_buffer(8)
    n = user32.ToUnicodeEx(vk, 0, state, buf, 8, 0, hkl)
    print(f"vk=0x{vk:02X} ({name}) ToUnicodeEx -> n={n} char={buf[0]!r}")
    print(f"        _char_of -> {cap._char_of(vk, 0)!r}")
