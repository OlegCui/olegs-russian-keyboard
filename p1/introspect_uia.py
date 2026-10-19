# -*- coding: utf-8 -*-
import sys

sys.stdout.reconfigure(encoding="utf-8")
import uiautomation as auto

print("uiautomation", getattr(auto, "VERSION", "?"))
print()
print("--- auto 模块里含 Pattern 的名字 ---")
print([n for n in dir(auto) if "attern" in n])
print()
print("--- Control 上含 Pattern / Text 的方法 ---")
print([m for m in dir(auto.Control) if "Pattern" in m or "Text" in m])
print()
pid = getattr(auto, "PatternId", None)
print("PatternId:", pid)
if pid:
    print("  TextPattern =", getattr(pid, "TextPattern", None))
    print("  ValuePattern =", getattr(pid, "ValuePattern", None))
print()
print("--- 试取一次焦点控件的 TextPattern ---")
c = auto.GetFocusedControl()
print("focused:", c.ControlTypeName if c else None)
if c:
    for candidate in ("GetTextPattern", "GetPattern"):
        print(f"  has {candidate}:", hasattr(c, candidate))
