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
# ru-words.txt = OpenSubtitles 词频表（口语）+ Leeds 补充，见 data/build_wordlist.py
WORDS_FILE = _first_existing(
    os.path.join(BUNDLE, "..", "data", "ru-words.txt"),
    os.path.join(BUNDLE, "ru-words.txt"),               # PyInstaller 打进来的原始文件名
    os.path.join(BUNDLE, "..", "data", "russian-words",
                 "100000-russian-words.txt"),           # 旧表，保底
    os.path.join(BUNDLE, "100000-russian-words.txt"),
)

# 下一个词预测用的 bigram（data/build_bigram.py 生成）
NGRAM_FILE = _first_existing(
    os.path.join(BUNDLE, "..", "data", "ru-bigram.tsv"),
    os.path.join(BUNDLE, "ru-bigram.tsv"),
)

TRIGRAM_FILE = _first_existing(
    os.path.join(BUNDLE, "..", "data", "ru-trigram.tsv"),
    os.path.join(BUNDLE, "ru-trigram.tsv"),
)

EXAMPLES_FILE = _first_existing(
    os.path.join(BUNDLE, "..", "data", "ru-examples.tsv"),
    os.path.join(BUNDLE, "ru-examples.tsv"),
)

# 例句的中文翻译（data/build_example_zh.py 生成，可能不存在）
EXAMPLES_ZH_FILE = _first_existing(
    os.path.join(BUNDLE, "..", "data", "ru-examples-zh.tsv"),
    os.path.join(BUNDLE, "ru-examples-zh.tsv"),
)

CARDS_FILE = _first_existing(
    os.path.join(BUNDLE, "..", "data", "ru-cards.tsv"),
    os.path.join(BUNDLE, "ru-cards.tsv"),
)

SETTINGS_FILE = user_path("settings.json")
RULES_USER = user_path("rules.json")        # 用户可改的规则卡（优先于内置）
FREQ_FILE = user_path("user_freq.json")
WORDBOOK_FILE = user_path("wordbook.json")
WORDBOOK_MD = user_path("生词本.md")
LOG_FILE = user_path("app.log")


SRC = {
    "frozen": FROZEN,
        "bundle": BUNDLE,
        "user": USER,
        "rules": RULES_FILE,
        "rules_user": RULES_USER,
        "words": WORDS_FILE,
        "bigram": NGRAM_FILE,
        "trigram": TRIGRAM_FILE,
        "examples": EXAMPLES_FILE,
        "cards": CARDS_FILE,
}


def describe():
    return SRC


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for k, v in describe().items():
        print(f"  {k:8} = {v}")
    print(f"  rules 存在 = {os.path.exists(RULES_FILE)}")
    print(f"  words 存在 = {os.path.exists(WORDS_FILE)}")
