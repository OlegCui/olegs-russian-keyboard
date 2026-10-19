# -*- coding: utf-8 -*-
"""
P0 实验②-修正版：把 top1 误差拆开，并改用"产品真正需要的指标"。

上一版发现 top1 只有 56%，但翻看失败样本后发现，绝大部分不是引擎错误，而是：
  A类 词元约定   —— 分词（бывший）被当成独立词元，与动词 быть 分列
  B类 同形多义   —— им 既是 он 的造格又是 они 的与格，排序选了后者
  C类 真错误     —— 需要单独找出

对输入法产品来说，top1 本来就是**错的指标**：用户打 друга，
正确行为是同时显示"属格 / 宾格"，而不是替他选一个。所以改用：
  coverage  = 正确解析是否存在（生成是否自洽）
  top3      = 正确解析是否在前 3（UI 最多展示 3 个读法）
  歧义度     = 每个词形平均有几个读法（决定 UI 怎么排）
"""
import collections
import glob
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
import pymorphy3

N_FORMS_SCAN = 3000
N_LEMMAS = 500

KEY = {
    "nomn", "gent", "datv", "accs", "ablt", "loct", "voct",
    "gen1", "gen2", "acc2", "loc1", "loc2",
    "sing", "plur", "masc", "femn", "neut", "ms-f",
    "1per", "2per", "3per",
    "pres", "past", "futr", "indc", "impr",
    "perf", "impf",
}
VERBISH = {"INFN", "VERB"}


def find_wordlist():
    base = r"D:\Tools\俄语输入法\data\russian-words"
    files = [f for f in glob.glob(os.path.join(base, "**", "*.txt"), recursive=True) if ".git" not in f]
    return max(files, key=os.path.getsize)


def is_cyr(s):
    return bool(s) and all("\u0400" <= c <= "\u04FF" or c == "-" for c in s)


def load(path, limit):
    out, seen = [], set()
    for line in open(path, encoding="utf-8-sig"):
        t = line.strip().split()[0] if line.strip() else ""
        if not t or not is_cyr(t) or t.lower() in seen:
            continue
        seen.add(t.lower())
        out.append(t.lower())
        if len(out) >= limit:
            break
    return out


def gm(m):
    return frozenset(set(m.tag.grammemes) & KEY)


def main():
    morph = pymorphy3.MorphAnalyzer()
    words = load(find_wordlist(), N_FORMS_SCAN)

    lemmas, seen = [], set()
    for w in words:
        p = morph.parse(w)[0]
        k = (p.normal_form, str(p.tag.POS))
        if k in seen:
            continue
        seen.add(k)
        lemmas.append((p.normal_form, str(p.tag.POS), p))
        if len(lemmas) >= N_LEMMAS:
            break

    total = c_any = c3 = c1 = 0
    by_pos = collections.defaultdict(lambda: [0, 0, 0, 0])
    cls = collections.Counter()
    ambiguity = []
    samples = {"A": [], "B": [], "C": []}

    for lemma, pos, p in lemmas:
        for f in p.lexeme:
            w = f.word
            if not w or not is_cyr(w):
                continue
            want = gm(f)
            parses = morph.parse(w)
            total += 1
            by_pos[pos][0] += 1
            idx = -1
            for i, q in enumerate(parses):
                if q.normal_form == lemma and gm(q) == want:
                    idx = i
                    break
            ambiguity.append(len(parses))
            if idx >= 0:
                c_any += 1
                by_pos[pos][1] += 1
                if idx < 3:
                    c3 += 1
                    by_pos[pos][2] += 1
                if idx == 0:
                    c1 += 1
                    by_pos[pos][3] += 1
                elif idx < 3:
                    cls["B_排序"] += 1
                    if len(samples["B"]) < 12:
                        samples["B"].append((lemma, w, parses[0].normal_form,
                                             str(parses[0].tag.POS)))
                continue

            top = parses[0]
            if str(top.tag.POS) in {"PRTF", "PRTS"} and pos in VERBISH:
                cls["A_分词词元"] += 1
                if len(samples["A"]) < 6:
                    samples["A"].append((lemma, w, top.normal_form, str(top.tag.POS)))
            else:
                cls["C_未进结果"] += 1
                if len(samples["C"]) < 20:
                    samples["C"].append((lemma, w, top.normal_form, str(top.tag.POS),
                                         ",".join(sorted(want))[:36]))

    print(f"测试词元 {len(lemmas)} / 生成词形 {total}")
    print("=" * 66)
    print(f"coverage(任意位置) : {c_any:6}/{total} = {c_any/total*100:6.2f}%")
    print(f"top3(前三个读法内) : {c3:6}/{total} = {c3/total*100:6.2f}%")
    print(f"top1(第一位)       : {c1:6}/{total} = {c1/total*100:6.2f}%")
    print(f"平均读法数         : {sum(ambiguity)/len(ambiguity):.2f}")
    ones = sum(1 for a in ambiguity if a == 1)
    print(f"无歧义(仅1个读法)  : {ones}/{len(ambiguity)} = {ones/len(ambiguity)*100:.1f}%")
    print("=" * 66)
    print()
    print(f"{'POS':8} {'forms':>7} {'cover%':>8} {'top3%':>8} {'top1%':>8}")
    for pos, (n, a, t3, t1) in sorted(by_pos.items(), key=lambda kv: -kv[1][0]):
        if n < 20:
            continue
        print(f"{pos:8} {n:7} {a/n*100:7.2f}% {t3/n*100:7.2f}% {t1/n*100:7.2f}%")
    print()
    print("--- 失败归类 ---")
    for k, v in cls.most_common():
        print(f"{k:14} {v}")
    print()
    for tag, title in [("A", "A类 分词词元约定（非错误）"),
                       ("B", "B类 同形多义排序（真实，但 UI 本应全展示）"),
                       ("C", "C类 真正丢失（需要关注）")]:
        if not samples[tag]:
            continue
        print(f"--- {title} ---")
        for row in samples[tag]:
            print("   " + " | ".join(str(x) for x in row))
        print()


if __name__ == "__main__":
    main()
