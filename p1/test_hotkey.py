# -*- coding: utf-8 -*-
"""
热键与取词的测试。

这一组是 v0.9.1 的回归：Ctrl+L 曾经把热键自身的控制字符（\\x0c）
写进输入缓冲，查词窗口于是拿一个空字符去查，什么都不显示。
"""
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"D:\Tools\俄语输入法\p1")

import app as A


class FakeUser:
    """假装按着 Ctrl（可带 Shift），其余调用转给真的 user32。"""

    def __init__(self, ctrl_down=True, shift_down=False):
        self.ctrl_down = ctrl_down
        self.shift_down = shift_down

    def __getattr__(self, name):
        return getattr(A.user32, name)

    def GetAsyncKeyState(self, vk):
        if vk == 0x11 and self.ctrl_down:
            return 0x8000
        if vk == 0x10 and self.shift_down:
            return 0x8000
        return 0


def main():
    ok_all = True

    def check(name, got, want):
        nonlocal ok_all
        ok = got == want
        ok_all = ok_all and ok
        print(f"  {name:34} 得到={str(got)[:30]:32} {'PASS' if ok else 'FAIL'}")

    a = A.App(require_lang=None)
    a.root.update()
    A.user32 = FakeUser(True)
    A.foreground_lang = lambda: A.LANG_RU

    print("\n--- 控制字符不进缓冲 ---")
    check("current_word('\\x0c')", A.current_word("\x0c"), "")
    check("current_word('Думаю \\x0c')", A.current_word("Думаю \x0c"), "")
    check("previous_words('я не \\x0c')", A.previous_words("я не \x0c"),
          ["я", "не"])

    print("\n--- Ctrl+L 取词 ---")
    a.hook.buffer = "Думаю"
    got = a._maybe_intercept(0x4C)
    item = a.q.get_nowait() if not a.q.empty() else None
    check("拦截 Ctrl+L", got, True)
    check("查的是打出来的词", item, ("lookup", "Думаю"))

    a.hook.buffer = "Думаю "
    got = a._maybe_intercept(0x4C)
    item = a.q.get_nowait() if not a.q.empty() else None
    # previous_word 会把词转小写（预测那边要小写），查词不影响
    check("词后有空格也能取到", item, ("lookup", "думаю"))

    a.hook.buffer = "я не знаю "
    got = a._maybe_intercept(0x4C)
    item = a.q.get_nowait() if not a.q.empty() else None
    check("取最后一个词", item, ("lookup", "знаю"))

    print("\n--- Ctrl+D 同样 ---")
    a.hook.buffer = "суббота"
    got = a._maybe_intercept(0x44)
    item = a.q.get_nowait() if not a.q.empty() else None
    check("Ctrl+D 存词", item, ("save", "суббота"))

    print("\n--- 布局切换后的热键 ---")
    # 中文布局 + 刚打过俄语：仍然接管（用户就是切了布局继续用）
    A.user32 = FakeUser(True, False)
    A.foreground_lang = lambda: 0x0804
    a.hook.buffer = "Думаешь"
    a._last_text_at = time.time() - 5
    got = a._maybe_intercept(0x44)
    item = a.q.get_nowait() if not a.q.empty() else None
    check("中文布局但刚打过俄语", item, ("save", "Думаешь"))

    # 中文布局 + 很久没打俄语：不能抢浏览器的 Ctrl+D
    a._last_text_at = time.time() - 600
    check("很久没打俄语时不接管", a._maybe_intercept(0x44), False)

    print("\n--- Ctrl+Shift+D 打开生词本 ---")
    A.user32 = FakeUser(True, True)
    a._last_text_at = time.time() - 5
    got = a._maybe_intercept(0x44)
    item = a.q.get_nowait() if not a.q.empty() else None
    check("拦截 Ctrl+Shift+D", got, True)
    check("投递 wordbook 动作", item, ("wordbook", None))

    a.root.destroy()
    print("\n" + ("全部通过" if ok_all else "有失败项"))
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
