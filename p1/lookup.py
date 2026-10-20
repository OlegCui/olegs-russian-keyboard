# -*- coding: utf-8 -*-
"""
形式词典：查一个俄语词，告诉你它是什么形式、能变成哪些形式。

不含中文释义（那是另一件事），专注"这个词现在是什么、该怎么变"。
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")

CASE_ORDER = ["nomn", "gent", "datv", "accs", "ablt", "loct", "voct"]
CASE_ZH = {"nomn": "主格", "gent": "属格", "datv": "与格", "accs": "宾格",
           "ablt": "工具格", "loct": "前置格", "voct": "呼格",
           "gen1": "属格②", "gen2": "属格②", "acc2": "宾格②",
           "loc1": "前置格", "loc2": "前置格②"}
NUM_ZH = {"sing": "单数", "plur": "复数"}
GENDER_ZH = {"masc": "阳性", "femn": "阴性", "neut": "中性", "ms-f": "通性"}
TENSE_ZH = {"pres": "现在时", "past": "过去时", "futr": "将来时"}
PERSON_ZH = {"1per": "第一人称", "2per": "第二人称", "3per": "第三人称"}
MOOD_ZH = {"indc": "陈述式", "impr": "命令式"}


def _case_label(c):
    return CASE_ZH.get(c, c)


def format_card(eng, word):
    """把查询结果格式化成文本。"""
    w = (word or "").strip()
    if not w:
        return "输入一个俄语词，按回车查询。"
    read = eng.analyze(w, limit=5)
    if not read:
        return f"「{w}」查不到——可能不是俄语词，或拼写有误。"

    lines = []
    top = read[0]
    lines.append(f"{w}")
    lines.append("─" * 46)
    lines.append(f"原形    {top['lemma']}")
    lines.append(f"词性    {top['pos_zh']}")
    if top.get("number"):
        lines.append(f"数      {NUM_ZH.get(top['number'], top['number'])}")
    if top.get("case_zh"):
        lines.append(f"格      {top['case_zh']}")

    if len(read) > 1:
        lines.append("")
        lines.append("其他可能的解析（按可能性）")
        for r in read[1:]:
            bits = [r["lemma"], r["pos_zh"]]
            if r.get("case_zh"):
                bits.append(r["case_zh"])
            if r.get("number"):
                bits.append(NUM_ZH.get(r["number"], r["number"]))
            lines.append(f"  · {' / '.join(bits)}   ({r['score']})")

    # 词形表
    try:
        p = eng.morph.parse(w)[0]
        pos = str(p.tag.POS)
        lines.append("")
        if pos in ("NOUN", "ADJF", "NPRO", "PRTF", "PRTS"):
            lines.append("词形变化")
            table = {}
            for f in p.lexeme:
                c = str(f.tag.case) if f.tag.case else None
                n = str(f.tag.number) if f.tag.number else None
                if c and n:
                    table.setdefault(c, {})[n] = f.word
            for c in CASE_ORDER + [k for k in table if k not in CASE_ORDER]:
                if c not in table:
                    continue
                sg = table[c].get("sing", "")
                pl = table[c].get("plur", "")
                if sg or pl:
                    lines.append(f"  {_case_label(c):<8}{sg:<16}{pl}")
            if table:
                lines.insert(lines.index("词形变化") + 1,
                             f"  {'':<8}{'单数':<16}{'复数'}")
        else:
            lines.append("词形变化")
            seen = []
            for f in p.lexeme:
                if f.word in seen:
                    continue
                seen.append(f.word)
                t = f.tag
                bits = []
                if t.tense:
                    bits.append(TENSE_ZH.get(str(t.tense), str(t.tense)))
                if t.person:
                    bits.append(PERSON_ZH.get(str(t.person), str(t.person)))
                if t.number:
                    bits.append(NUM_ZH.get(str(t.number), str(t.number)))
                if t.mood:
                    bits.append(MOOD_ZH.get(str(t.mood), str(t.mood)))
                label = " · ".join(bits)
                lines.append(f"  {f.word:<18}{label}")
                if len(seen) >= 24:
                    lines.append("  …（还有更多）")
                    break
    except Exception as e:
        lines.append(f"（词形表生成失败: {e}）")

    # 规则提示
    try:
        fs = eng.check(w)
        if fs:
            lines.append("")
            lines.append("规则提示")
            for f in fs[:3]:
                lines.append(f"  ⚠ {f['title']}")
    except Exception:
        pass

    return "\n".join(lines)


class LookupWindow:
    _instances = {}

    @classmethod
    def show(cls, root, eng, word=None):
        key = id(root)
        win = cls._instances.get(key)
        if win is not None:
            try:
                if win.win.winfo_exists():
                    if word:
                        win.query(word)
                    win.win.deiconify()
                    win.win.attributes("-topmost", True)
                    win.win.lift()
                    win.win.focus_force()
                    win.win.after(400, lambda: win.win.attributes("-topmost", False))
                    return win
            except Exception:
                pass
        win = cls(root, eng)
        cls._instances[key] = win
        if word:
            win.query(word)
        return win

    def __init__(self, root, eng):
        import tkinter as tk
        import tkinter.ttk as ttk
        self.eng = eng
        self.win = tk.Toplevel(root)
        self.win.title("俄语形式词典")
        self.win.geometry("680x620+360+120")
        # 不能 transient：root 是 withdraw 状态，transient 子窗口会被一起藏掉
        self.win.attributes("-topmost", True)
        self.win.after(400, lambda: self.win.attributes("-topmost", False))

        try:
            ttk.Style(self.win).theme_use("vista")   # 原生 Windows 控件外观
        except Exception:
            pass

        top = tk.Frame(self.win)
        top.pack(fill="x", padx=12, pady=10)
        self.entry = tk.Entry(top, font=("Segoe UI", 14), relief="solid",
                              bd=1, highlightthickness=0)
        self.entry.pack(side="left", fill="x", expand=True, ipady=4)
        self.entry.bind("<Return>", lambda e: self.query(self.entry.get()))
        ttk.Button(top, text="查询", command=lambda: self.query(self.entry.get())
                   ).pack(side="left", padx=(8, 0))

        body = tk.Frame(self.win)
        body.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        sb = ttk.Scrollbar(body)
        sb.pack(side="right", fill="y")
        self.text = tk.Text(body, font=("Consolas", 12), wrap="none",
                            relief="solid", bd=1, yscrollcommand=sb.set,
                            padx=10, pady=8, highlightthickness=0)
        self.text.pack(side="left", fill="both", expand=True)
        sb.config(command=self.text.yview)
        self.text.insert("1.0", "输入一个俄语词，按回车查询。")
        self.text.config(state="disabled")

        btns = tk.Frame(self.win)
        btns.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(btns, text="复制结果", command=self._copy).pack(side="left")
        ttk.Button(btns, text="清空",
                   command=lambda: self.query("")).pack(side="left", padx=8)

        self.entry.focus_set()

    def _copy(self):
        """复制到剪贴板。

        优先走 win32clipboard 的 CF_UNICODETEXT：Tk 的 clipboard_append 在某些
        程序里粘出来会变成问号或乱码（俄语、中文都踩过），显式写 Unicode 才稳。
        """
        text = self.text.get("1.0", "end").strip()
        try:
            import win32clipboard as cb
            cb.OpenClipboard()
            try:
                cb.EmptyClipboard()
                cb.SetClipboardData(cb.CF_UNICODETEXT, text)
            finally:
                cb.CloseClipboard()
            return
        except Exception:
            pass
        try:
            self.win.clipboard_clear()
            self.win.clipboard_append(text)
        except Exception:
            pass

    def query(self, word):
        w = (word or "").strip()
        self.entry.delete(0, "end")
        self.entry.insert(0, w)
        out = format_card(self.eng, w)
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", out)
        self.text.config(state="disabled")
        return out


def show_lookup(root, eng, word=None):
    return LookupWindow.show(root, eng, word)


if __name__ == "__main__":
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import engine as E
    e = E.Engine()
    for w in sys.argv[1:] or ["другу", "помочь", "красивого"]:
        print(format_card(e, w))
        print()
