# -*- coding: utf-8 -*-
"""
路径层：区分「只读资源」和「可写数据」。

开发模式（直接跑 .py）：
    只读 = p1/ 和 ../data/
    可写 = p1/（方便调试，文件就在眼前）

打包后（PyInstaller）：
    只读 = sys._MEIPASS（每次启动解压，只读）
    可写 = %APPDATA%\\OlegsRussianKeyboard（用户数据：记忆、生词本、日志、设置）

这样打包前后行为一致，用户数据也不会因为升级 exe 而丢。
"""
import os
import sys

APP_NAME = "OlegsRussianKeyboard"
FROZEN = bool(getattr(sys, "frozen", False))

if FROZEN:
    BUNDLE = getattr(sys, "_MEIPASS",
                     os.path.dirname(os.path.abspath(sys.executable)))
    USER = os.path.join(os.environ.get("APPDATA")
                        or os.path.expanduser("~"), APP_NAME)
else:
    BUNDLE = os.path.dirname(os.path.abspath(__file__))
    USER = BUNDLE

try:
    os.makedirs(USER, exist_ok=True)
except Exception:
    pass


def user_path(name):
    return os.path.join(USER, name)


def _first_existing(*cands):
    for c in cands:
        if c and os.path.exists(c):
            return c
    return cands[-1]


# 规则卡：开发时在 p0/，打包后在根目录
RULES_FILE = _first_existing(
    os.path.join(BUNDLE, "..", "p0", "rules.json"),
    os.path.join(BUNDLE, "rules.json"),
)

# 词表：开发时在 ../data/，打包后在根目录
WORDS_FILE = _first_existing(
    os.path.join(BUNDLE, "..", "data", "russian-words",
                 "100000-russian-words.txt"),
    os.path.join(BUNDLE, "russian-words.txt"),
)

SETTINGS_FILE = user_path("settings.json")
FREQ_FILE = user_path("user_freq.json")
WORDBOOK_FILE = user_path("wordbook.json")
WORDBOOK_MD = user_path("生词本.md")
LOG_FILE = user_path("app.log")


def describe():
    return {
        "frozen": FROZEN,
        "bundle": BUNDLE,
        "user": USER,
        "rules": RULES_FILE,
        "words": WORDS_FILE,
    }


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for k, v in describe().items():
        print(f"  {k:8} = {v}")
    print(f"  rules 存在 = {os.path.exists(RULES_FILE)}")
    print(f"  words 存在 = {os.path.exists(WORDS_FILE)}")
