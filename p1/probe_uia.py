# -*- coding: utf-8 -*-
"""
UIA 光标探针 v2

关键：取光标要用 TextPattern2.GetCaretRange()，不是 TextPattern.GetSelection()。
      GetSelection 在「没有选中内容」时返回空，而光标恰恰就是空选区状态。

三级策略：
  1. TextPattern2.GetCaretRange()   ← 首选，Win8.1+ 起可用，Chromium 支持
  2. TextPattern.GetSelection()     ← 老应用
  3. TextEditPattern 的选区
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")
import uiautomation as auto

PID_TP1 = auto.PatternId.TextPattern
PID_TP2 = getattr(auto.PatternId, "TextPattern2", 10024)
PID_TE = getattr(auto.PatternId, "TextEditPattern", 10032)


def _flatten_numbers(obj):
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
        out.extend(_flatten_numbers(x))
    return out


def _rect_of(rng):
    try:
        raw = rng.GetBoundingRectangles()
    except Exception as e:
        return None, f"rects_failed:{e}"
    nums = _flatten_numbers(raw)
    if len(nums) < 4:
        return None, f"bad_rects(len={len(nums)})"
    n = len(nums) // 4
    x1, y1, x2, y2 = nums[(n - 1) * 4:(n - 1) * 4 + 4]
    return {"x": int(round(x1)), "y": int(round(y2)),
            "w": int(round(x2 - x1)), "h": int(round(y2 - y1))}, None


def _pick_range(res):
    """GetCaretRange 可能返回 (isActive, range) 或 range。"""
    if res is None:
        return None
    if isinstance(res, (tuple, list)):
        for x in reversed(res):
            if hasattr(x, "GetBoundingRectangles"):
                return x
        return res[0] if res else None
    return res


def _try_caret_range(ctrl):
    try:
        tp2 = ctrl.GetPattern(PID_TP2)
    except Exception as e:
        return None, f"TP2_unavailable:{e}"
    if tp2 is None:
        return None, "TP2_none"
    fn = getattr(tp2, "GetCaretRange", None)
    if fn is None:
        methods = [m for m in dir(tp2) if not m.startswith("_")]
        return None, f"no_GetCaretRange; TP2 methods={methods[:12]}"
    try:
        res = fn()
    except Exception as e:
        return None, f"GetCaretRange_failed:{e}"
    rng = _pick_range(res)
    if rng is None:
        return None, "caret_range_none"
    rect, err = _rect_of(rng)
    if rect is None:
        return None, f"caret_{err}"
    return rect, None


def _try_selection(ctrl, pid, tag):
    try:
        tp = ctrl.GetPattern(pid)
    except Exception as e:
        return None, f"{tag}_unavailable:{e}"
    if tp is None:
        return None, f"{tag}_none"
    try:
        sel = tp.GetSelection()
    except Exception as e:
        return None, f"{tag}_GetSelection_failed:{e}"
    if not sel:
        return None, f"{tag}_empty_selection"
    rng = sel[-1] if isinstance(sel, (list, tuple)) else sel
    rect, err = _rect_of(rng)
    if rect is None:
        return None, f"{tag}_{err}"
    return rect, None


def caret():
    c = auto.GetFocusedControl()
    if c is None:
        return None, "no_focused_control"
    info = {"ctrl": c.ControlTypeName,
            "cls": (getattr(c, "ClassName", "") or "")[:40],
            "name": (getattr(c, "Name", "") or "")[:40]}
    reasons = []

    rect, why = _try_caret_range(c)
    if rect:
        rect.update(info)
        rect["via"] = "TextPattern2.GetCaretRange"
        return rect, None
    reasons.append(why)

    for pid, tag in [(PID_TP1, "TP1"), (PID_TE, "TE")]:
        rect, why = _try_selection(c, pid, tag)
        if rect:
            rect.update(info)
            rect["via"] = tag + ".GetSelection"
            return rect, None
        reasons.append(why)

    return None, f"{info['ctrl']}: " + " | ".join(reasons)


def diagnose():
    c = auto.GetFocusedControl()
    if c is None:
        return "no focus"
    lines = [f"ControlType={c.ControlTypeName} ClassName={getattr(c,'ClassName','')!r}",
             f"Name={getattr(c,'Name','')!r}"]
    for name in ["TextPattern", "TextPattern2", "TextEditPattern", "ValuePattern"]:
        pid = getattr(auto.PatternId, name, None)
        if pid is None:
            continue
        try:
            p = c.GetPattern(pid)
        except Exception as e:
            lines.append(f"  {name}: error {e}")
            continue
        if p is None:
            lines.append(f"  {name}: none")
        else:
            ms = [m for m in dir(p) if not m.startswith("_")]
            lines.append(f"  {name}: OK methods={ms[:10]}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(diagnose())
    r, w = caret()
    print("caret:", r)
    print("why  :", w)
