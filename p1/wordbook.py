# -*- coding: utf-8 -*-
"""
生词本：按快捷键把当前词记下来，带原形/词性/格，导出成 Markdown。

存储：wordbook.json（纯本地）
导出：生词本.md（给人看、可粘到笔记里）
"""
import json
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
try:
    from paths import WORDBOOK_FILE, WORDBOOK_MD
    DEFAULT_JSON, DEFAULT_MD = WORDBOOK_FILE, WORDBOOK_MD
except Exception:
    DEFAULT_JSON = os.path.join(HERE, "wordbook.json")
    DEFAULT_MD = os.path.join(os.path.dirname(HERE), "生词本.md")


class WordBook:
    def __init__(self, path=DEFAULT_JSON, md_path=DEFAULT_MD):
        self.path = path
        self.md_path = md_path
        self.words = []          # 按加入顺序
        self._load()

    # ---------- 持久化 ----------
    def _load(self):
        try:
            if os.path.exists(self.path):
                with open(self.path, encoding="utf-8-sig") as fh:
                    raw = json.load(fh)
                ws = raw.get("words") or []
                if isinstance(ws, list):
                    self.words = [w for w in ws
                                  if isinstance(w, dict) and w.get("word")]
                    self._migrate()
        except Exception as e:
            print(f"[wordbook] 读取失败: {e}", file=__import__("sys").stderr)

    def save(self):
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump({"version": 1, "words": self.words}, fh,
                          ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
        except Exception as e:
            print(f"[wordbook] 保存失败: {e}", file=__import__("sys").stderr)

    # ---------- 增删 ----------
    def add(self, word, lemma="", pos="", case="", app=""):
        w = (word or "").strip()
        if not w:
            return False
        key = w.lower()
        for it in self.words:
            if it["word"].lower() == key:
                it["count"] = it.get("count", 1) + 1
                it["last"] = time.time()
                self.save()
                self.export_md()
                return False          # 已存在，只加计数
        now = time.time()
        self.words.append({
            "word": w, "lemma": lemma, "pos": pos, "case": case,
            "app": app, "added": now, "last": now, "count": 1,
            # 间隔重复：due 是"下次该复习的时间"，新词立刻到期
            "due": now, "interval": 0.0, "ease": 2.5,
            "reps": 0, "lapses": 0,
        })
        self.save()
        self.export_md()
        return True

    def _migrate(self):
        """老版本存下来的词没有 SRS 字段，补上默认值（due=现在，立刻可复习）。"""
        now = time.time()
        for it in self.words:
            it.setdefault("due", it.get("added", now))
            it.setdefault("interval", 0.0)
            it.setdefault("ease", 2.5)
            it.setdefault("reps", 0)
            it.setdefault("lapses", 0)

    # ---------- 间隔重复 ----------
    def due_words(self, now=None):
        """到期该复习的词，最久没复习的排前面。"""
        now = time.time() if now is None else now
        due = [w for w in self.words if w.get("due", 0) <= now]
        return sorted(due, key=lambda w: (w.get("due", 0), w.get("reps", 0)))

    def next_due(self):
        """最近一个到期时间（没有词就返回 None）。"""
        if not self.words:
            return None
        return min(w.get("due", 0) for w in self.words)

    def review(self, word, grade):
        """复习一个词。grade: 0 忘了 / 1 勉强 / 2 记得 / 3 太简单。"""
        key = (word or "").lower()
        for it in self.words:
            if it["word"].lower() != key:
                continue
            iv = float(it.get("interval", 0.0))
            ease = float(it.get("ease", 2.5))
            if grade <= 0:
                iv, ease = 1.0, max(1.3, ease - 0.20)
                it["lapses"] = it.get("lapses", 0) + 1
            elif grade == 1:
                iv, ease = max(1.0, (iv or 1.0) * 1.2), max(1.3, ease - 0.05)
            elif grade == 2:
                iv = max(1.0, (iv or 1.0) * 2.0)
            else:
                iv, ease = max(2.0, (iv or 2.0) * 3.0), min(3.0, ease + 0.10)
            iv = min(180.0, iv)
            it["interval"] = round(iv, 2)
            it["ease"] = round(ease, 2)
            it["reps"] = it.get("reps", 0) + 1
            it["last"] = time.time()
            it["due"] = time.time() + iv * 86400
            self.save()
            self.export_md()
            return True
        return False

    def review_stats(self):
        now = time.time()
        total = len(self.words)
        due = sum(1 for w in self.words if w.get("due", 0) <= now)
        learned = sum(1 for w in self.words if w.get("interval", 0) >= 7)
        return {"total": total, "due": due, "learned": learned}

    # ---------- Anki 导出 ----------
    def export_anki(self, path=None):
        """制表符分隔，Anki 可直接导入：正面=词，背面=原形·语法·例句。"""
        path = path or (self.path.rsplit(".", 1)[0] + "-anki.tsv")
        try:
            lines = ["#separator:tab", "#html:false",
                     "#columns:Word\tBack"]
            for it in self.words:
                tag = " · ".join(x for x in [it.get("pos"), it.get("case")] if x)
                back_bits = [it.get("lemma") or "", tag,
                             f"复习 {it.get('reps', 0)} 次"]
                back = " | ".join(x for x in back_bits if x)
                lines.append(f"{it['word']}\t{back}")
            with open(path, "w", encoding="utf-8-sig", newline="\n") as fh:
                fh.write("\n".join(lines) + "\n")
            return path
        except Exception as e:
            print(f"[wordbook] Anki 导出失败: {e}", file=__import__("sys").stderr)
            return ""

    def remove(self, word):
        key = (word or "").lower()
        n = len(self.words)
        self.words = [w for w in self.words if w["word"].lower() != key]
        if len(self.words) != n:
            self.save()
            self.export_md()
            return True
        return False

    def clear(self):
        self.words = []
        self.save()
        self.export_md()

    def __len__(self):
        return len(self.words)

    # ---------- 导出 ----------
    def export_md(self):
        try:
            lines = ["# 生词本", "",
                     f"共 {len(self.words)} 个词 · 更新于 "
                     f"{time.strftime('%Y-%m-%d %H:%M')}", "",
                     "| 词 | 原形 | 词性 / 格 | 次数 | 加入时间 |",
                     "|---|---|---|---|---|"]
            for it in self.words:
                tag = " · ".join(x for x in [it.get("pos"), it.get("case")] if x)
                t = time.strftime("%Y-%m-%d",
                                  time.localtime(it.get("added") or 0))
                lines.append(f"| {it['word']} | {it.get('lemma', '')} | {tag} "
                             f"| {it.get('count', 1)} | {t} |")
            with open(self.md_path, "w", encoding="utf-8-sig") as fh:
                fh.write("\n".join(lines) + "\n")
        except Exception as e:
            print(f"[wordbook] 导出 md 失败: {e}", file=__import__("sys").stderr)

    # ---------- 查看窗口（列表 + 词形详情） ----------
    def show_window(self, root=None, eng=None):
        import tkinter as tk
        import tkinter.ttk as ttk
        from tkinter import messagebox
        own = root is None
        win = tk.Toplevel(root) if root else tk.Tk()
        win.title(f"生词本 · {len(self.words)} 词")
        win.geometry("1000x620+240+120")

        try:
            ttk.Style(win).theme_use("vista")     # 原生 Windows 控件外观
        except Exception:
            pass

        if eng is None:
            try:
                import engine as _e
                eng = _e.Engine()
            except Exception:
                eng = None

        bar = tk.Frame(win)
        bar.pack(fill="x", padx=12, pady=10)
        tk.Label(bar, text=f"共 {len(self.words)} 个词",
                 font=("Microsoft YaHei UI", 10)).pack(side="left")
        tk.Label(bar, text=f"  导出: {self.md_path}",
                 fg="#888", font=("Microsoft YaHei UI", 8)).pack(side="left")

        paned = tk.PanedWindow(win, orient="horizontal", sashwidth=6)
        paned.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        # 左：词表
        left = tk.Frame(paned)
        sb = ttk.Scrollbar(left)
        sb.pack(side="right", fill="y")
        lb = tk.Listbox(left, font=("Segoe UI", 12), yscrollcommand=sb.set,
                        width=42, activestyle="none", relief="solid", bd=1,
                        highlightthickness=0)
        lb.pack(side="left", fill="both", expand=True)
        sb.config(command=lb.yview)
        paned.add(left, minsize=280)

        # 右：词形详情
        right = tk.Frame(paned)
        dsb = ttk.Scrollbar(right)
        dsb.pack(side="right", fill="y")
        detail = tk.Text(right, font=("Consolas", 11), wrap="none",
                         relief="solid", bd=1, yscrollcommand=dsb.set,
                         padx=10, pady=8, highlightthickness=0)
        detail.pack(side="left", fill="both", expand=True)
        dsb.config(command=detail.yview)
        paned.add(right, minsize=380)

        def refresh():
            lb.delete(0, "end")
            for it in reversed(self.words):
                tag = " · ".join(x for x in [it.get("pos"), it.get("case")] if x)
                lb.insert("end", f"{it['word']:<16} {it.get('lemma', ''):<16} "
                                 f"{tag:<12} ×{it.get('count', 1)}")
            win.title(f"生词本 · {len(self.words)} 词")

        def current_word():
            sel = lb.curselection()
            if not sel:
                return None
            idx = len(self.words) - 1 - sel[0]
            return self.words[idx]["word"]

        def show_detail(word=None):
            w = word or current_word()
            if not w:
                return
            txt = ""
            if eng is not None:
                try:
                    import lookup
                    txt = lookup.format_card(eng, w)
                except Exception as e:
                    txt = f"（词典加载失败: {e}）"
            else:
                txt = "（形态引擎未就绪）"
            detail.config(state="normal")
            detail.delete("1.0", "end")
            detail.insert("1.0", txt)
            detail.config(state="disabled")

        def on_select(_e=None):
            show_detail()

        def on_delete():
            w = current_word()
            if not w:
                return
            self.remove(w)
            refresh()
            detail.config(state="normal")
            detail.delete("1.0", "end")
            detail.config(state="disabled")

        def on_export():
            self.export_md()
            messagebox.showinfo("导出", f"已导出到\n{self.md_path}")

        lb.bind("<<ListboxSelect>>", on_select)
        lb.bind("<Double-Button-1>", lambda e: show_detail())

        btns = tk.Frame(win)
        btns.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(btns, text="删除选中", command=on_delete).pack(side="left")
        ttk.Button(btns, text="重新导出 Markdown", command=on_export
                   ).pack(side="left", padx=8)

        refresh()
        if self.words:
            lb.selection_set(0)
            lb.activate(0)
            show_detail()

        # 主窗口是 withdraw 的，Toplevel 可能被别的程序压在后面，主动置前
        try:
            win.deiconify()
            win.attributes("-topmost", True)
            win.lift()
            win.focus_force()
            win.after(300, lambda: win.attributes("-topmost", False))
        except Exception:
            pass

        if own:
            win.mainloop()
        return win


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    wb = WordBook()
    print(f"生词本: {len(wb)} 词")
    for it in wb.words[:10]:
        print(f"  {it['word']:16} {it.get('lemma', ''):16} "
              f"{it.get('pos', '')} {it.get('case', '')} ×{it.get('count', 1)}")
    if "--window" in sys.argv:
        wb.show_window()
