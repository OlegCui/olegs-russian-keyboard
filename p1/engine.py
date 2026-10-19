# -*- coding: utf-8 -*-
"""
P1-b 引擎层：把 P0 验证过的两块能力包成输入法可调用的 API。

  analyze(word)  → 这个词有哪些读法（词元 + 词性 + 格/数/时态）
  paradigm(word) → 这个词元的完整词形表（给候选条用）
  check(text)    → 规则卡检查（给提示用）

设计原则：
  - 只读，无副作用，可被任何界面调用
  - 输出带中文标签，界面直接渲染
"""
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
import pymorphy3

HERE = os.path.dirname(os.path.abspath(__file__))
try:
    from paths import RULES_FILE as RULES
except Exception:
    RULES = os.path.join(HERE, "..", "p0", "rules.json")
PUNCT = ".,!?;:()\"«»—–-\n\t "

CASE_ZH = {"nomn": "主格", "gent": "属格", "datv": "与格",
           "accs": "宾格", "ablt": "造格", "loct": "前置格"}
CASE_ORDER = ["nomn", "gent", "datv", "accs", "ablt", "loct"]
POS_ZH = {"NOUN": "名词", "ADJF": "形容词", "VERB": "动词", "INFN": "不定式",
          "NPRO": "代词", "NUMR": "数词", "ADVB": "副词", "PREP": "前置词",
          "PRTF": "形动词", "ADJS": "短形容词", "COMP": "比较级"}


def resolve_rules():
    """规则卡：用户目录优先（可改、免打包），找不到才用内置的。"""
    try:
        import paths
        if os.path.exists(paths.RULES_USER):
            return paths.RULES_USER
        return paths.RULES_FILE
    except Exception:
        return os.path.join(HERE, "..", "p0", "rules.json")


class Engine:
    def __init__(self, rules_path=None):
        self.rules_path = rules_path or resolve_rules()
        self.morph = pymorphy3.MorphAnalyzer()
        self.cards = []
        try:
            with open(self.rules_path, encoding="utf-8-sig") as fh:
                self.cards = json.load(fh)["cards"]
        except Exception as e:
            print(f"[engine] 规则卡加载失败: {e}", file=sys.stderr)
        self._compiled = []
        for c in self.cards:
            try:
                self._compiled.append((c, re.compile(c["pattern"], re.IGNORECASE)))
            except Exception:
                pass

    # ---------- 读法 ----------
    def analyze(self, word, limit=5):
        w = word.strip(PUNCT).lower()
        if not w:
            return []
        out = []
        for p in self.morph.parse(w)[:limit]:
            t = p.tag
            out.append({
                "form": p.word,
                "lemma": p.normal_form,
                "pos": str(t.POS),
                "pos_zh": POS_ZH.get(str(t.POS), str(t.POS)),
                "case": str(t.case) if t.case else None,
                "case_zh": CASE_ZH.get(str(t.case)) if t.case else None,
                "number": str(t.number) if t.number else None,
                "score": round(p.score, 3),
            })
        return out

    # ---------- 词形表 ----------
    def paradigm(self, word, want="auto", limit=8):
        w = word.strip(PUNCT).lower()
        if not w:
            return []
        p = self.morph.parse(w)[0]
        pos = str(p.tag.POS)

        if want == "auto":
            if pos in ("NOUN", "ADJF", "NPRO", "NUMR"):
                want = "cases"
            elif pos in ("VERB", "INFN", "PRTF"):
                want = "verb"
            else:
                want = "cases"

        items = []
        if want == "cases":
            seen = set()
            for f in p.lexeme:
                c = str(f.tag.case) if f.tag.case else None
                n = str(f.tag.number) if f.tag.number else None
                if c in CASE_ZH and n == "sing" and c not in seen:
                    seen.add(c)
                    items.append({"form": f.word, "label": CASE_ZH[c],
                                  "case": c})
            items.sort(key=lambda x: CASE_ORDER.index(x["case"]))
        else:
            def add(f, label):
                if f is not None and f.word not in [i["form"] for i in items]:
                    items.append({"form": f.word, "label": label})

            if pos != "INFN":
                inf = p.inflect({"INFN"})
                add(inf, "不定式")
            else:
                add(p, "不定式")
            for per, lbl in [({"1per", "sing"}, "我"), ({"2per", "sing"}, "你"),
                             ({"3per", "sing"}, "他/她"), ({"1per", "plur"}, "我们"),
                             ({"2per", "plur"}, "你们"), ({"3per", "plur"}, "他们")]:
                add(p.inflect(per | {"pres"}), lbl)
            if len(items) < 3:
                for g, lbl in [({"past", "masc"}, "过去(阳)"), ({"past", "femn"}, "过去(阴)"),
                               ({"past", "plur"}, "过去(复)")]:
                    add(p.inflect(g), lbl)

        return items[:limit]

    # ---------- 规则检查 ----------
    def check(self, text):
        out = []
        if not text:
            return out
        for card, pat in self._compiled:
            for m in pat.finditer(text):
                if card["type"] == "tag_check":
                    phrase = m.group(card["capture"])
                    pos_list = card["expect"]["POS"]
                    limit = card.get("scan_words", 1)
                    req = set(card.get("require_any", []))
                    hit = None
                    for raw in phrase.split()[:limit]:
                        w = raw.strip(PUNCT).lower()
                        if not w:
                            continue
                        cands = [q for q in self.morph.parse(w)
                                 if str(q.tag.POS) in pos_list]
                        if not cands:
                            continue
                        ok = any(req & set(q.tag.grammemes) for q in cands)
                        if not ok:
                            hit = w
                        break
                    if hit:
                        out.append({"id": card["id"], "title": card["title_zh"],
                                    "hit": hit, "msg": card["message_zh"],
                                    "why": card.get("explain_zh", ""),
                                    "level": card.get("level", "")})
                elif card["type"] in ("missing_token", "phrase_replace", "snippet"):
                    out.append({"id": card["id"], "title": card["title_zh"],
                                "hit": m.group().strip(), "msg": card["message_zh"],
                                "why": card.get("explain_zh", ""),
                                "suggest": card.get("suggest"),
                                "level": card.get("level", "")})
        out.sort(key=lambda x: x["hit"])
        return out

    # ---------- 给候选条用的一站式接口 ----------
    def suggest(self, token):
        readings = self.analyze(token)
        if not readings:
            return {"token": token, "items": [], "readings": [], "findings": []}
        top = readings[0]
        items = self.paradigm(token)
        return {
            "token": token,
            "lemma": top["lemma"],
            "pos_zh": top["pos_zh"],
            "current": top,
            "items": items,
            "readings": readings,
            "findings": self.check(token),
        }


# ---------------- CLI / 自测 ----------------
    # ---------- 高频词补全 / 纠错 ----------
    @property
    def dic(self):
        if getattr(self, "_dic", None) is None:
            try:
                from dict_index import WordIndex
                self._dic = WordIndex()
            except Exception as e:
                print(f"[engine] 词表加载失败: {e}", file=sys.stderr)
                self._dic = False
        return self._dic or None

    def is_valid(self, word):
        """这个词是不是真实存在的词（pymorphy3 认得 = 不是拼错）。"""
        w = word.strip(PUNCT).lower()
        if len(w) < 2:
            return False
        try:
            return bool(getattr(self.morph.parse(w)[0], "is_known", False))
        except Exception:
            return False

    @property
    def uf(self):
        """个人词频记忆（选过的词会往前提）。"""
        if getattr(self, "_uf", None) is None:
            try:
                from learn import UserFreq
                self._uf = UserFreq()
            except Exception as e:
                print(f"[engine] 记忆库加载失败: {e}", file=sys.stderr)
                self._uf = False
        return self._uf or None

    def complete(self, token, limit=6):
        """补全在前，更正在后（变格是另一套视图，Tab 切换）。"""
        w = token.strip(PUNCT).lower()
        if len(w) < 2:
            return []

        comps, corrs = [], []
        d = self.dic
        if d:
            longer = d.complete(w, 12)
            comps = [{"form": c, "label": "补全"} for c in longer]
            # 只有在"不像还在打字"时才给更正：
            # 若这个词仍是 3 个以上词的前缀，用户显然没打完，不该说它拼错
            # （否则 прив 会被"更正"成 при / приз，很不礼貌）
            if not self.is_valid(w) and len(longer) < 3:
                corrs = [{"form": c, "label": "更正"} for c in d.correct(w, 2)]

        seen = set()
        comps = [x for x in comps if not (x["form"] in seen or seen.add(x["form"]))]
        corrs = [x for x in corrs if not (x["form"] in seen or seen.add(x["form"]))]

        uf = self.uf
        if uf:
            rank = d.rank if d else {}

            def key(it):
                return uf.sort_key(it["form"], rank.get(it["form"], 10 ** 9))

            comps.sort(key=key)
            corrs.sort(key=key)
            for it in comps + corrs:
                if uf.count(it["form"]) > 0:
                    it["label"] = "常用"
        return (comps + corrs)[:limit]


def demo():
    e = Engine()
    print(f"规则卡 {len(e.cards)} 张\n")

    print("=" * 66)
    print("1) 读法识别（用户在候选条上该看到什么）")
    print("=" * 66)
    for w in ["другу", "друга", "Москве", "помочь", "хотеть"]:
        rs = e.analyze(w)
        line = " | ".join(f"{r['lemma']}·{r['pos_zh']}"
                          + (f"·{r['case_zh']}" if r["case_zh"] else "")
                          for r in rs[:3])
        print(f"  {w:10} -> {line}")

    print("\n" + "=" * 66)
    print("2) 词形表（候选条内容）")
    print("=" * 66)
    for w in ["другу", "хочу", "играть", "красивый"]:
        s = e.suggest(w)
        print(f"\n  {w}  → 词元 {s['lemma']}（{s['pos_zh']}）")
        print("     " + "  ".join(f"{i['form']}[{i['label']}]" for i in s["items"]))

    print("\n" + "=" * 66)
    print("3) 规则检查")
    print("=" * 66)
    for t in ["я хочу чтобы ты придешь",
              "Я хочу, чтобы ты пришёл.",
              "Я хочу помочь тебя.",
              "Мне не хватает время."]:
        fs = e.check(t)
        if not fs:
            print(f'  "{t}"  → ✅ 无问题')
        else:
            print(f'  "{t}"')
            for f in fs:
                print(f"      ❌ [{f['level']}] {f['title']}  命中「{f['hit']}」")

    print("\n" + "=" * 66)
    print("4) 性能")
    print("=" * 66)
    import time
    n = 200
    t0 = time.perf_counter()
    for _ in range(n):
        e.suggest("другу")
    dt = (time.perf_counter() - t0) / n * 1000
    print(f"  suggest() 平均 {dt:.2f} ms/次（候选条要 <50ms 才不卡）")


if __name__ == "__main__":
    demo()
