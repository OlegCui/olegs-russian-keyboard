# -*- coding: utf-8 -*-
"""
P0 实验③：规则卡能不能被结构化成"可机检的数据"？

验证三件事：
  1. 一张卡 = 一段 JSON，加规则不改代码
  2. 每张卡自带回归用例（wrong 必须命中 / right 必须零命中）
  3. 同一套引擎能吃下四种卡型：tag_check / missing_token / phrase_replace / snippet
"""
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
import pymorphy3

HERE = os.path.dirname(os.path.abspath(__file__))
RULES = os.path.join(HERE, "rules.json")
PUNCT = ".,!?;:()\"«»—–-\n\t "

morph = pymorphy3.MorphAnalyzer()


def load_cards():
    with open(RULES, encoding="utf-8") as fh:
        return json.load(fh)["cards"]


def clean(w):
    return w.strip(PUNCT)


def pick_word(phrase, expect_pos, limit, req):
    """从捕获串往后找第一个指定词性的词，并判断该词的全部读法里是否存在满足要求的一个。

    关键：必须看"全部读法"而不是"首选读法"。
    друга 同时是属格和宾格，若只看首选（属格）就会把 правильно 的
    "увидеть друга" 误判为错误 —— 这是规则卡最容易翻车的地方。
    """
    for raw in phrase.split()[:limit]:
        w = clean(raw)
        if not w:
            continue
        cands = [p for p in morph.parse(w) if str(p.tag.POS) in expect_pos]
        if not cands:
            continue
        ok = any(req & set(p.tag.grammemes) for p in cands)
        return w, ok
    return None, None


def check(text, cards):
    out = []
    for card in cards:
        pat = re.compile(card["pattern"], re.IGNORECASE)
        t = card["type"]
        for m in pat.finditer(text):
            if t == "tag_check":
                phrase = m.group(card["capture"])
                pos_list = card["expect"]["POS"]
                limit = card.get("scan_words", 1)
                req = set(card.get("require_any", []))
                word, ok = pick_word(phrase, pos_list, limit, req)
                if word is None or ok:
                    continue
                out.append({"card": card, "hit": word, "at": m.start(card["capture"])})
            elif t == "missing_token":
                out.append({"card": card, "hit": m.group().strip(), "at": m.start()})
            elif t in ("phrase_replace", "snippet"):
                out.append({"card": card, "hit": m.group().strip(), "at": m.start()})
    out.sort(key=lambda x: x["at"])
    return out


def render(text, findings):
    print(f'输入: "{text}"')
    if not findings:
        print("   ✅ 未发现问题")
        return
    for f in findings:
        c = f["card"]
        print(f'   ❌ [{c["level"]}] {c["title_zh"]}')
        print(f'      命中: "{f["hit"]}"')
        print(f'      说明: {c["message_zh"]}')
        if c.get("explain_zh"):
            print(f'      为什么: {c["explain_zh"]}')
        if c.get("suggest"):
            print(f'      建议: {c["suggest"].replace(chr(10), " / ")}')


def main():
    cards = load_cards()
    print(f"加载规则卡 {len(cards)} 张\n")

    # ---------- 1. 逐卡回归测试 ----------
    print("=" * 70)
    print("回归测试：每张卡的 wrong 必须命中 / right 必须零命中")
    print("=" * 70)
    passed = failed = 0
    for c in cards:
        bad = check(c["wrong"], [c])
        good_all = check(c["right"], cards)          # 正确句不能触发任何卡
        hit_ok = len(bad) > 0
        clean_ok = len(good_all) == 0
        if hit_ok and clean_ok:
            passed += 1
            print(f"  PASS  {c['id']:18} 命中wrong ✔  正确句干净 ✔")
        else:
            failed += 1
            reason = []
            if not hit_ok:
                reason.append("wrong 没命中")
            if not clean_ok:
                reason.append("right 被误报: " + ",".join(x["card"]["id"] for x in good_all))
            print(f"  FAIL  {c['id']:18} {' / '.join(reason)}")
    print(f"\n  合计: {passed} passed, {failed} failed\n")

    # ---------- 2. 真实句子演示 ----------
    print("=" * 70)
    print("演示：连续文本检查")
    print("=" * 70)
    demo = [
        "я хочу чтобы ты придешь",
        "Я хочу, чтобы ты пришёл.",
        "Я хочу прийти.",
        "Я хочу помочь тебя.",
        "Я хочу помочь тебе.",
        "Мне не хватает время.",
        "Мне не хватает времени.",
        "Спасибо ты за помощь.",
        "Спасибо тебе за помощь.",
        "Я играю в футболе.",
        "Я играю в футбол.",
        "Я имею машину.",
        "У меня есть машина.",
        "Мне нужно иду.",
        "Мне нужно идти.",
        "Это зависит от погода.",
        "Это зависит от погоды.",
        "с уважением",
    ]
    total_find = 0
    for s in demo:
        f = check(s, cards)
        total_find += len(f)
        render(s, f)
        print()
    print(f"共 {len(demo)} 句，命中 {total_find} 处\n")

    # ---------- 3. 加卡成本演示 ----------
    print("=" * 70)
    print("加一张新卡的成本：只往 rules.json 里加一段 JSON")
    print("=" * 70)
    new_card = {
        "id": "uvidet_gen",
        "title_zh": "увидеть 接宾格不是属格（对比 бояться 接属格）",
        "type": "tag_check",
        "level": "B1",
        "pattern": "увидел(?:а)?\\s+(?P<target>[а-яёА-ЯЁ]+)",
        "capture": "target",
        "expect": {"POS": ["NOUN", "NPRO"]},
        "require_any": ["accs"],
        "message_zh": "увидеть 是及物动词，直接接宾格。",
    }
    probe = "Я увидел друга."
    print(f'  不入库，临时喂给引擎: "{probe}"')
    hits = check(probe, [new_card])
    if hits:
        for f in hits:
            print(f'  → 命中 "{f["hit"]}"，说明: {f["card"]["message_zh"]}')
    else:
        print("  → 未报错。друга 是属格/宾格同形，require_any=accs 命中任一读法即放行。")
    print('  （这就是"只提示、不误报"的设计：宁可漏报，不可乱报）')


if __name__ == "__main__":
    main()
