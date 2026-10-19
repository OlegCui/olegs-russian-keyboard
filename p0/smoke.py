# -*- coding: utf-8 -*-
"""P0 smoke test: 确认 pymorphy3 的分析、反查、生成三条能力都在。"""
import sys

sys.stdout.reconfigure(encoding="utf-8")

import pymorphy3

m = pymorphy3.MorphAnalyzer()
print("pymorphy3", getattr(pymorphy3, "__version__", "?"))


def show(w):
    print(f"\n--- {w} ---")
    for p in m.parse(w)[:4]:
        t = p.tag
        print(
            f"  form={p.word!r:20} lemma={p.normal_form!r:15}"
            f" pos={str(t.POS):8} case={str(t.case):6}"
            f" num={str(t.number):6} score={p.score:.3f}"
        )


for w in ["другу", "привет", "хочу", "помочь", "стола", "Москве", "Иванову"]:
    show(w)

print("\n=== 生成：друг 的六个格 ===")
p = m.parse("друг")[0]
for g in [{"nomn"}, {"gent"}, {"datv"}, {"accs"}, {"ablt"}, {"loct"}]:
    r = p.inflect(g)
    print(f"  {list(g)[0]:6} -> {r.word if r else None}")

print("\n=== 生成：делать 的现在时 ===")
v = m.parse("делать")[0]
print("  lemma:", v.normal_form, "aspect:", v.tag.aspect)
for person in [{"1per", "sing"}, {"2per", "sing"}, {"3per", "sing"}, {"1per", "plur"}]:
    r = v.inflect(person | {"pres"})
    print(f"  {sorted(person)} -> {r.word if r else None}")

print("\n=== 生成：хотеть 的过去时（性数）===")
h = m.parse("хотеть")[0]
for g in [{"past", "masc"}, {"past", "femn"}, {"past", "neut"}, {"past", "plur"}]:
    r = h.inflect(g)
    print(f"  {sorted(g)} -> {r.word if r else None}")
