# -*- coding: utf-8 -*-
"""
下一个词预测的测试（安全版：不向任何窗口注入按键）。

覆盖：
  1. previous_word()：词/句结束后能不能正确取出"上一个词"
  2. Bigram：加载与查询
  3. 完整链路：打完一个词 + 空格 → 候选条显示预测 → 数字键选词 → 注入
"""
import os
import sys
import tempfile
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "D:/Tools/俄语输入法/p1")

import app as app_mod
from ngram import Bigram, Trigram, Predictor

FAKE = {
    "я": [("не", 900), ("знаю", 700), ("хочу", 600)],
    "не": [("знаю", 800), ("могу", 700)],
    "как": [("дела", 900), ("ты", 700)],
}


def make_bigram_file():
    path = os.path.join(tempfile.gettempdir(), "_bigram_test.tsv")
    with open(path, "w", encoding="utf-8") as fh:
        for head, rows in FAKE.items():
            fh.write(head + "\t" + " ".join(f"{w}:{c}" for w, c in rows) + "\n")
    return path


def main():
    ok_all = True

    def check(name, got, want):
        nonlocal ok_all
        ok = got == want
        ok_all = ok_all and ok
        print(f"  {name:34} 得到={got!r:26} 期望={want!r:26} "
              f"{'PASS' if ok else 'FAIL'}")

    print("\n--- previous_word（词结束才取上一个词）---")
    check("'я не '", app_mod.previous_word("я не "), "не")
    check("'я не'（还在打字）", app_mod.previous_word("я не"), "")
    check("'как дела? '", app_mod.previous_word("как дела? "), "дела")
    check("'привет, '", app_mod.previous_word("привет, "), "привет")
    check("'  '（只有空白）", app_mod.previous_word("  "), "")

    print("\n--- Bigram 查询 ---")
    bg = Bigram(make_bigram_file())
    check("加载条数", len(bg), 3)
    check("predict('я')", bg.predict("я"), ["не", "знаю", "хочу"])
    check("predict('нет такого')", bg.predict("нет такого"), [])

    print("\n--- 三元组：看前两个词 ---")
    tri_path = os.path.join(tempfile.gettempdir(), "_trigram_test.tsv")
    with open(tri_path, "w", encoding="utf-8") as fh:
        fh.write("я не\tзнаю:900 могу:700\n")
        fh.write("как ты\tдумаешь:800\n")
    tri = Trigram(tri_path)
    check("三元组条数", len(tri), 2)
    check("predict('я не')", tri.predict("я не"), ["знаю", "могу"])

    pred = Predictor(make_bigram_file(), tri_path)
    got, src = pred.predict(["я", "не"])
    check("三元组命中（来源）", src, "trigram")
    check("三元组命中（候选）", got[:2], ["знаю", "могу"])

    got2, src2 = pred.predict(["в", "не"])      # "в не" 不在三元组里
    check("没命中退回二元组（来源）", src2, "bigram")
    check("退回后用的是最后一个词", got2[:2], ["знаю", "могу"])

    got3, src3 = pred.predict(["я"])
    check("只有一个词时走二元组", src3, "bigram")
    check("predict(['я'])", got3, ["не", "знаю", "хочу"])

    print("\n--- 完整链路：预测 → 选词 → 注入 ---")
    injected = []
    app_mod.input_sim.replace_tail = lambda n, t: (
        injected.append(("back", n, t)), True)[1]
    app_mod.input_sim.send_text = lambda t: (injected.append(("text", t)), True)[1]

    app = app_mod.App(require_lang=None, verbose=False)
    app.eng._pred = Predictor(make_bigram_file(), tri_path)  # 用测试模型
    app.next_word = True
    app.start()
    app.root.after(40, app.pump)

    def pump(n=20):
        for _ in range(n):
            app.root.update()
            time.sleep(0.02)

    app.hook.buffer = "я не "
    app._update("я не ")
    pump()
    mode_ok = app._mode == "predict"
    forms = [i["form"] for i in app.bar.items]
    check("模式", app._mode, "predict")
    check("候选", forms, ["знаю", "могу"])
    ok_all = ok_all and mode_ok and bool(forms)

    # 预测模式下数字键必须放行（否则想打 "10" 会插进一个词）
    check("预测模式按 1 不拦截", app._maybe_intercept(0x31), False)

    injected.clear()
    check("预测模式按 Tab 拦截", app._maybe_intercept(0x09), True)
    pump()
    check("Tab 选词（词 + 自动空格）", injected,
          [("back", 0, "знаю"), ("text", " ")])

    # 补全模式下数字仍然直选
    app.hook.buffer = "прив"
    app._update("прив")
    pump()
    check("补全模式按 1 仍直选", app._maybe_intercept(0x31), True)

    # 刚选完立刻不该又弹预测
    app._update("я не знаю ")
    pump()
    check("选完后 0.35 秒内不再弹", app.bar.visible, False)

    app.hook.stop()
    app.root.destroy()
    print("\n" + ("全部通过" if ok_all else "有失败项"))
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
