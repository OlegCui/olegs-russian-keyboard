# -*- coding: utf-8 -*-
"""
P0 实验②：pymorphy3 变格生成 / 词形反查 的准确率基线。

做法（纯自动、无人工标注）：
  1. 从词频表取前 N 个词形 → 解析出词元（lemma）
  2. 每个词元用 .lexeme 展开全部词形（这就是"我们要展示给用户的变格表"）
  3. 反查：把每个生成的词形丢回解析器，看能否还原到同一个词元 + 同一组语法特征
  4. 报两个指标：
       coverage = 正确解析出现在结果任意位置（生成是否自洽）
       top1     = 正确解析排在第一位（用户反查时看到的第一个答案是否正确）

注意：这是**往返自洽性**测试，不能替代人工标注。它能抓出"生成器与解析器互相矛盾"
的硬伤，抓不出"两者一致地错"的系统性问题。后者需要人工抽样（下一步）。
"""
import collections
import glob
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
import pymorphy3

N_FORMS_SCAN = 3000   # 从词频表扫多少个词形来挑词元
N_LEMMAS = 500        # 测试多少个词元

KEY = {
    "nomn", "gent", "datv", "accs", "ablt", "loct", "voct",
    "gen1", "gen2", "acc2", "loc1", "loc2",
    "sing", "plur", "masc", "femn", "neut", "ms-f",
    "1per", "2per", "3per",
    "pres", "past", "futr", "indc", "impr",
    "perf", "impf",
}


def find_wordlist():
    base = r"D:\Tools\俄语输入法\data\russian-words"
    files = glob.glob(os.path.join(base, "**", "*.txt"), recursive=True)
    files = [f for f in files if ".git" not in f]
    if not files:
        raise SystemExit("没找到词频文件，请先 clone hingston/russian")
    return max(files, key=os.path.getsize)


def is_cyrillic(s):
    return bool(s) and all("\u0400" <= ch <= "\u04FF" or ch in "-" for ch in s)


def load_words(path, limit):
    out, seen = [], set()
    with open(path, encoding="utf-8-sig") as fh:
        for line in fh:
            tok = line.strip().split()[0] if line.strip() else ""
            if not tok or not is_cyrillic(tok):
                continue
            low = tok.lower()
            if low in seen:
                continue
            seen.add(low)
            out.append(low)
            if len(out) >= limit:
                break
    return out


def gram(m):
    """只保留与形态变化有关的语法特征，忽略 POS 差异（lexeme 内 POS 会变）。"""
    return frozenset(set(m.tag.grammemes) & KEY)


def main():
    morph = pymorphy3.MorphAnalyzer()
    path = find_wordlist()
    print(f"词频表: {os.path.basename(path)}")
    words = load_words(path, N_FORMS_SCAN)
    print(f"扫描词形: {len(words)}")

    # 1) 抽词元
    lemmas, seen = [], set()
    for w in words:
        p = morph.parse(w)[0]
        key = (p.normal_form, str(p.tag.POS))
        if key in seen:
            continue
        seen.add(key)
        lemmas.append((p.normal_form, str(p.tag.POS), p))
        if len(lemmas) >= N_LEMMAS:
            break
    print(f"测试词元: {len(lemmas)}")

    # 2) 展开 + 3) 反查
    total = cover_ok = top1_ok = 0
    by_pos = collections.defaultdict(lambda: [0, 0, 0])
    failures = []

    for lemma, pos, p in lemmas:
        forms = p.lexeme
        for f in forms:
            w = f.word
            if not w or not is_cyrillic(w):
                continue
            want_g = gram(f)
            total += 1
            by_pos[pos][0] += 1
            parses = morph.parse(w)
            hit_any = False
            hit_top = False
            for i, q in enumerate(parses):
                if q.normal_form == lemma and gram(q) == want_g:
                    hit_any = True
                    if i == 0:
                        hit_top = True
                    break
            if hit_any:
                cover_ok += 1
                by_pos[pos][1] += 1
            if hit_top:
                top1_ok += 1
                by_pos[pos][2] += 1
            elif hit_any and len(failures) < 40:
                failures.append((lemma, pos, w, str(parses[0].normal_form),
                                 str(parses[0].tag), sorted(want_g)))

    print()
    print("=" * 62)
    print(f"生成词形总数 : {total}")
    print(f"coverage     : {cover_ok}/{total} = {cover_ok/total*100:.2f}%")
    print(f"top1（首选）  : {top1_ok}/{total} = {top1_ok/total*100:.2f}%")
    print("=" * 62)
    print()
    print(f"{'POS':10} {'forms':>7} {'cover%':>8} {'top1%':>8}")
    for pos, (n, c, t) in sorted(by_pos.items(), key=lambda kv: -kv[1][0]):
        print(f"{pos:10} {n:7} {c/n*100:7.2f}% {t/n*100:7.2f}%")

    print()
    print("--- 反查首选错误样本（前 40）---")
    print(f"{'lemma':15} {'生成形':15} {'首选解析':15} {'期望特征'}")
    for lemma, pos, w, got_lemma, got_tag, want in failures:
        print(f"{lemma:15} {w:15} {got_lemma:15} {','.join(want)[:40]}")

    # 4) 反向抽样：人工最常查的几类
    print()
    print("--- 重点词人工可核对清单 ---")
    for word in ["другу", "помочь", "Иванову", "Москве", "два", "обе", "мать",
                 "время", "идти", "хотеть"]:
        ps = morph.parse(word)
        top = ps[0]
        cases = ",".join(sorted(set(top.tag.grammemes) & KEY))
        print(f"{word:10} -> {top.normal_form:12} {str(top.tag.POS):6} {cases}")


if __name__ == "__main__":
    main()
