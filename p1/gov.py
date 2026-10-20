# -*- coding: utf-8 -*-
"""
句法辅助：动词的支配关系（«управление глаголов»）。

学习者最常踩的坑不是变格本身，而是**该用哪个格**：
    помочь тебе ✅ / помочь тебя ❌
    интересоваться музыкой ✅ / интересоваться музыку ❌

做法：一张「动词原形 → 允许的格」的小表（只收最常用、争议小的），
配合 pymorphy3 判断后面那个名词的格，不匹配就提示正确形式。

为什么表要小
------------
宁少勿错。俄语里同一动词常有多个可接受格（ждать автобус / ждать автобуса），
表里把可接受的都列上；拿不准的动词直接不收。
"""
import re

CASES = {
    "nomn": "主格",
    "gent": "属格",
    "datv": "与格",
    "accs": "宾格",
    "ablt": "工具格",
    "loct": "前置格",
}

CASE_TAG = {
    "nomn": "nomn", "gent": "gent", "datv": "datv",
    "accs": "accs", "ablt": "ablt", "loct": "loct",
}

# 动词原形 → 允许的直接宾语格（可多个）
GOVERNMENT = {
    # —— 要求与格（кому） ——
    "помогать": {"datv"}, "помочь": {"datv"},
    "звонить": {"datv"}, "позвонить": {"datv"},
    "верить": {"datv"}, "поверить": {"datv"},
    "доверять": {"datv"},
    "мешать": {"datv"}, "помешать": {"datv"},
    "завидовать": {"datv"}, "позавидовать": {"datv"},
    "подражать": {"datv"},
    "сопротивляться": {"datv"},
    "следовать": {"datv"},
    "соответствовать": {"datv"},
    "принадлежать": {"datv"},
    "учиться": {"datv"}, "научиться": {"datv"},
    "радоваться": {"datv"}, "обрадоваться": {"datv"},
    "удивляться": {"datv"}, "удивиться": {"datv"},
    "уступать": {"datv"}, "уступить": {"datv"},
    "советовать": {"datv"}, "посоветовать": {"datv"},
    "запрещать": {"datv"}, "запретить": {"datv"},
    "разрешать": {"datv"}, "разрешить": {"datv"},
    "приказывать": {"datv"}, "приказать": {"datv"},
    "способствовать": {"datv"},
    "препятствовать": {"datv"},
    "содействовать": {"datv"},

    # —— 要求工具格（чем） ——
    "интересоваться": {"ablt"}, "заинтересоваться": {"ablt"},
    "увлекаться": {"ablt"}, "увлечься": {"ablt"},
    "заниматься": {"ablt"}, "заняться": {"ablt"},
    "пользоваться": {"ablt"}, "воспользоваться": {"ablt"},
    "владеть": {"ablt"},
    "обладать": {"ablt"},
    "гордиться": {"ablt"},
    "восхищаться": {"ablt"}, "восхититься": {"ablt"},
    "руководить": {"ablt"},
    "управлять": {"ablt"},
    "командовать": {"ablt"},
    "распоряжаться": {"ablt"},
    "занимать": {"ablt"},

    # —— 要求属格（кого/чего） ——
    "бояться": {"gent"},
    "избегать": {"gent"}, "избежать": {"gent"},
    "достигать": {"gent"}, "достичь": {"gent"},
    "касаться": {"gent"}, "коснуться": {"gent"},
    "лишать": {"gent"}, "лишить": {"gent"},
    "стыдиться": {"gent"},
    "добиваться": {"gent"}, "добиться": {"gent"},
    "слушаться": {"gent"},

    # —— 要求宾格（кого/что） ——
    "любить": {"accs"},
    "ненавидеть": {"accs"},
    "знать": {"accs"},
    "понимать": {"accs"}, "понять": {"accs"},
    "видеть": {"accs"}, "увидеть": {"accs"},
    "слышать": {"accs"}, "услышать": {"accs"},
    "читать": {"accs"}, "прочитать": {"accs"},
    "писать": {"accs"}, "написать": {"accs"},
    "есть": {"accs"}, "съесть": {"accs"},
    "пить": {"accs"}, "выпить": {"accs"},
    "слушать": {"accs"},
    "винить": {"accs"},
    "благодарить": {"accs"}, "поблагодарить": {"accs"},
    "предпочитать": {"accs"},
    "выбирать": {"accs"}, "выбрать": {"accs"},
    "искать": {"accs"},
    "награждать": {"accs"}, "наградить": {"accs"},

    # —— 两可（宾格 / 属格都有人说） ——
    "ждать": {"accs", "gent"},
    "требовать": {"accs", "gent"},
    "желать": {"accs", "gent"},
    "хотеть": {"accs", "gent"},
}

NOUN_TAGS = {"NOUN", "NPRO"}
SKIP_TAGS = {"PREP", "CONJ", "PRCL", "INTJ", "NUM", "VERB", "INFN",
             "ADVB", "ADJ", "PRTF", "GRND"}


def _case_of(parse):
    try:
        c = parse.tag.case
    except Exception:
        return None
    return c if c in CASES else None


def check(morph, verb_form, noun_form):
    """检查「动词 + 直接宾语」的格是否匹配。

    返回 None 表示没问题（或不认识的动词），否则返回：
        {"title": 提示语, "fix": 正确形式的词, "case": 应该用的格中文名}
    """
    if not verb_form or not noun_form:
        return None
    try:
        vp = morph.parse(verb_form)[0]
    except Exception:
        return None
    lemma = vp.normal_form
    allowed = GOVERNMENT.get(lemma)
    if not allowed:
        return None

    try:
        nps = morph.parse(noun_form)
    except Exception:
        return None
    nouns = [x for x in nps if (x.tag.POS or "") in NOUN_TAGS]
    if not nouns:
        return None
    # 一个词可能同时是主格/宾格（телефон），只要有一种解析符合就不算错
    if any(_case_of(x) in allowed for x in nouns):
        return None
    # 明确的错：给出推荐的正确形式
    for x in nouns:
        for cand in allowed:
            try:
                inf = x.inflect({cand})
            except Exception:
                inf = None
            if inf and inf.word and inf.word != noun_form.lower():
                return {
                    "title": f"«{lemma}» 要求{CASES[cand]}：{verb_form} {inf.word}",
                    "fix": inf.word,
                    "case": CASES[cand],
                    "lemma": lemma,
                }
    return None


def words_of(text):
    """取结尾处最多两个完整词。"""
    words = re.findall(r"[А-Яа-яЁё\-]{1,24}", text)
    return [w.lower() for w in words[-2:]]
