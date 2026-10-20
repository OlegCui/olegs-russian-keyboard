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
    def show_window(self, root=None, eng=None, examples=None):
        import tkinter as tk
        import tkinter.ttk as ttk
        from tkinter import messagebox
        own = root is None
        win = tk.Toplevel(root) if root else tk.Tk()
        win.title(f"生词本 · {len(self.words)} 词")
        win.geometry("1060x660+240+110")

        try:
            ttk.Style(win).theme_use("vista")
        except Exception:
            pass

        if eng is None:
            try:
                import engine as _e
                eng = _e.Engine()
            except Exception:
                eng = None

        if examples is None:
            try:
                import paths as _p
                from examples import Examples
                examples = Examples(getattr(_p, "EXAMPLES_FILE", None))
            except Exception:
                examples = None

        # ---------- 顶部：统计 + 搜索 + 分组 ----------
        top = tk.Frame(win)
        top.pack(fill="x", padx=12, pady=(10, 6))

        stat = self.review_stats()
        tk.Label(top, text=f"共 {stat['total']} 词 · 待复习 {stat['due']} · "
                           f"已掌握 {stat['learned']}",
                 font=("Microsoft YaHei UI", 10)).pack(side="left")

        self._query = tk.StringVar()
        self._group = tk.StringVar(value="全部")
        combo = ttk.Combobox(top, textvariable=self._group, width=10,
                             state="readonly",
                             values=("全部", "待复习", "按词性", "按日期"))
        combo.pack(side="right", padx=(8, 0))
        ent = tk.Entry(top, textvariable=self._query, width=22,
                       font=("Segoe UI", 11), relief="solid", bd=1,
                       highlightthickness=0)
        ent.pack(side="right", ipady=3)
        tk.Label(top, text="搜索", font=("Microsoft YaHei UI", 9)).pack(side="right", padx=(0, 6))

        paned = tk.PanedWindow(win, orient="horizontal", sashwidth=6)
        paned.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        left = tk.Frame(paned)
        sb = ttk.Scrollbar(left)
        sb.pack(side="right", fill="y")
        lb = tk.Listbox(left, font=("Segoe UI", 12), yscrollcommand=sb.set,
                        width=44, activestyle="none", relief="solid", bd=1,
                        highlightthickness=0)
        lb.pack(side="left", fill="both", expand=True)
        sb.config(command=lb.yview)
        paned.add(left, minsize=300)

        right = tk.Frame(paned)
        dsb = ttk.Scrollbar(right)
        dsb.pack(side="right", fill="y")
        detail = tk.Text(right, font=("Consolas", 11), wrap="none",
                         relief="solid", bd=1, yscrollcommand=dsb.set,
                         padx=10, pady=8, highlightthickness=0)
        detail.pack(side="left", fill="both", expand=True)
        dsb.config(command=detail.yview)
        paned.add(right, minsize=400)

        view = []          # 当前列表里显示的词条，和 Listbox 顺序一一对应

        def wanted():
            q = (self._query.get() or "").strip().lower()
            group = self._group.get()
            now = time.time()
            rows = []
            for it in reversed(self.words):          # 新的在前
                if q and q not in it.get("word", "").lower() \
                        and q not in (it.get("lemma") or "").lower():
                    continue
                if group == "待复习" and it.get("due", 0) > now:
                    continue
                rows.append(it)
            return rows

        def label_of(it):
            tag = " · ".join(x for x in [it.get("pos"), it.get("case")] if x)
            due = it.get("due", 0)
            now = time.time()
            if due <= now:
                mark = "●"                       # 到期
            else:
                days = max(1, int(round((due - now) / 86400)))
                mark = f"{days}d"
            return (f"{mark:<4} {it['word']:<15} {(it.get('lemma') or ''):<15} "
                    f"{tag:<12} ×{it.get('count', 1)}")

        def refresh(keep=None):
            view.clear()
            lb.delete(0, "end")
            group = self._group.get()
            rows = wanted()
            if group in ("按词性", "按日期"):
                def key(it):
                    if group == "按词性":
                        return (it.get("pos") or "未分类", -it.get("added", 0))
                    return (time.strftime("%Y-%m-%d", time.localtime(
                        it.get("added", 0))), it.get("word", ""))
                rows.sort(key=key)
                last = None
                for it in rows:
                    head = (it.get("pos") or "未分类") if group == "按词性" \
                        else time.strftime("%Y-%m-%d",
                                           time.localtime(it.get("added", 0)))
                    if head != last:
                        lb.insert("end", f"── {head} ──")
                        view.append(None)
                        last = head
                    lb.insert("end", label_of(it))
                    view.append(it)
            else:
                for it in rows:
                    lb.insert("end", label_of(it))
                    view.append(it)
            win.title(f"生词本 · {len(self.words)} 词"
                      f"（显示 {sum(1 for x in view if x)}）")
            if keep:
                for i, it in enumerate(view):
                    if it and it.get("word") == keep:
                        lb.selection_clear(0, "end")
                        lb.selection_set(i)
                        lb.see(i)
                        break

        def current_item():
            sel = lb.curselection()
            if not sel:
                return None
            i = sel[0]
            return view[i] if i < len(view) else None

        def show_detail(item=None):
            it = item or current_item()
            if not it:
                return
            w = it.get("word", "")
            txt = ""
            if eng is not None:
                try:
                    import lookup
                    txt = lookup.format_card(eng, w)
                except Exception as e:
                    txt = f"（词典加载失败: {e}）"
            else:
                txt = "（形态引擎未就绪）"
            sent = ""
            if examples is not None:
                try:
                    sent = examples.get(it.get("lemma") or w,
                                        getattr(eng, "morph", None))
                except Exception:
                    sent = ""
            if sent:
                txt += f"\n\n例句\n────\n{sent}\n"
            if it.get("due"):
                import datetime
                when = datetime.datetime.fromtimestamp(it["due"])
                txt += (f"\n复习\n────\n"
                        f"下次到期 {when.strftime('%Y-%m-%d %H:%M')}\n"
                        f"间隔 {it.get('interval', 0)} 天 · "
                        f"已复习 {it.get('reps', 0)} 次 · "
                        f"忘记 {it.get('lapses', 0)} 次\n")
            detail.config(state="normal")
            detail.delete("1.0", "end")
            detail.insert("1.0", txt)
            try:
                import lookup
                lookup.apply_cjk_font(detail, 11)
            except Exception:
                pass
            detail.config(state="disabled")

        def on_select(_e=None):
            show_detail()

        def on_delete():
            it = current_item()
            if not it:
                return
            self.remove(it.get("word", ""))
            refresh()

        def on_export():
            self.export_md()
            messagebox.showinfo("导出", f"已导出到\n{self.md_path}")

        def on_anki():
            p = self.export_anki()
            if p:
                messagebox.showinfo("Anki", f"已导出到\n{p}")

        def on_review():
            try:
                import review as rv
                win_ = rv.open_review(win, self, eng=eng, examples=examples,
                                     on_done=lambda n: refresh())
                if win_ is None:
                    messagebox.showinfo("复习", "现在没有到期的词。")
                else:
                    win_.win.bind("<Destroy>", lambda e: refresh())
            except Exception as e:
                messagebox.showerror("复习", str(e))

        lb.bind("<<ListboxSelect>>", on_select)
        lb.bind("<Double-Button-1>", lambda e: show_detail())
        ent.bind("<KeyRelease>", lambda e: refresh())
        combo.bind("<<ComboboxSelected>>", lambda e: refresh())

        btns = tk.Frame(win)
        btns.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(btns, text="复习到期", command=on_review).pack(side="left")
        ttk.Button(btns, text="删除选中", command=on_delete).pack(side="left", padx=8)
        ttk.Button(btns, text="导出 Markdown", command=on_export).pack(side="left")
        ttk.Button(btns, text="导出 Anki", command=on_anki).pack(side="left", padx=8)
        tk.Label(btns, text="● 会到期  ·  5d 表示 5 天后", fg="#888",
                 font=("Microsoft YaHei UI", 8)).pack(side="right")

        refresh()
        if view:
            lb.selection_set(0)
            show_detail()

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
