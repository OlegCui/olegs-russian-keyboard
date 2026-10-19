# -*- coding: utf-8 -*-
"""
字号探测：在 Word 里跑，告诉候选条能不能读到正文的字号。

用法：
  1. 双击启动俄语助手（或直接跑本脚本）
  2. 切到 Word，把光标放到正文里（字号设成你想测的大小）
  3. 5 秒后回来看输出

它只读不写，不会改你的文档。
"""
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "D:/Tools/俄语输入法/p1")
import app as app_mod


def main():
    print("=" * 60)
    print(" 请在 6 秒内切到 Word，把光标点进正文")
    print("=" * 60)
    time.sleep(6)

    print(f"\n前台窗口: {app_mod.foreground_title()!r}")
    print(f"键盘布局: 0x{app_mod.foreground_lang():04X}")

    print("\n--- 1) UIA ---")
    try:
        import uiautomation as auto
        c = auto.GetFocusedControl()
        print(f"  焦点控件: {c.ControlTypeName if c else None}")
        if c:
            print(f"    Name={c.Name[:40]!r}")
            print(f"    BoundingRectangle={c.BoundingRectangle}")
            tp = c.GetPattern(auto.PatternId.TextPattern)
            print(f"    TextPattern: {'有' if tp else '没有'}")
            if tp:
                sel = tp.GetSelection()
                print(f"    选区数量: {len(sel) if sel else 0}")
                if sel:
                    rng = sel[-1] if isinstance(sel, (list, tuple)) else sel
                    nums = app_mod._flatten(rng.GetBoundingRectangles())
                    print(f"    选区矩形: {nums}")
                    try:
                        v = rng.GetAttributeValue(40014)
                        print(f"    FontSize 属性: {v!r}"
                              + (f"  → {app_mod.font_px_from_pt(float(v))}px"
                                 if isinstance(v, (int, float)) else ""))
                    except Exception as e:
                        print(f"    FontSize 属性: 读取失败 ({e})")
    except Exception as e:
        print(f"  UIA 失败: {e}")

    print("\n--- 2) Win32 光标 ---")
    w = app_mod.caret_from_win32()
    print(f"  caret: {w}")
    if w:
        print(f"  由光标高推算字号: {app_mod.font_from_height(w[2])}px"
              f"（0 = 不可靠）")

    print("\n--- 3) 最终决策 ---")
    pos, how, px = app_mod.best_anchor()
    print(f"  锚点={pos} 来源={how}")
    print(f"  字号={app_mod.font_from_height(0) if not px else px}px"
          f"（0 表示没测到，程序会用 15px）")

    print("\n把上面全部内容发我即可。")


if __name__ == "__main__":
    main()
