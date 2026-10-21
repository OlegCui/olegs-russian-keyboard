# 数据文件说明

这些文件是**构建产物**，不要手改；改脚本再重新生成。

| 文件 | 内容 | 大小 | 生成脚本 |
|---|---|---|---|
| `ru-words.txt` | 160,000 个词形，按词频排序（补全用） | 2.7 MB | 外部语料 + 去重脚本 |
| `ru-lemmas.tsv` | 83,278 个原形 + 真实频次（覆盖率计算、纠错门槛用） | 1.6 MB | `build_lemmas.py` |
| `ru-bigram.tsv` | 24,759 个前词 → 后续词（下一个词预测） | 0.5 MB | `build_ngram.py` |
| `ru-trigram.tsv` | 25,766 个前两词 → 后续词 | 0.3 MB | `build_ngram.py` |
| `ru-examples.tsv` | 13,781 个原形的例句 | 1.2 MB | `build_examples.py` |
| `ru-cards.tsv` | 50 张深度卡（释义/结构/搭配/辨析/错误） | 20 KB | `seed_cards.py` |

## 什么时候需要更新

**每年一次就够。**

词表已经覆盖 99.9% 的实际说话内容（83,278 原形；6,000 原形 = 93.6%，
10,000 = 96.2%）。语料源（OpenSubtitles、Leipzig、维基）本身也是每年更新
一两次，追得太勤没有收益。

真正值得跟进的不是"更多词"，而是：

1. 例句覆盖率（现在 13,781/83,278，前排词要优先）
2. 词表清洗（字幕语料混进转写噪声，如 `секонд` 排 139,839）
3. 深度卡数量（需要 API key 批量生成，见 `seed_cards.py`）

## 年度更新步骤

```powershell
# 1. 拉新语料（路径见各脚本头部注释），放进 data/raw/
# 2. 重建
python data/build_lemmas.py      # 原形频次
python data/build_ngram.py       # 二元组 / 三元组
python data/build_examples.py    # 例句
# 3. 记下新数字，更新 README 里的覆盖率表
python -c "print(open('data/ru-lemmas.tsv',encoding='utf-8').read().count(chr(10)))"
# 4. 重新打包并核对启动日志：
#    [配置] 例句库: N 个原形
#    [配置] 预测模型: 二元组 N / 三元组 N
```

## 许可

代码是 MIT，**数据文件不是**，各自跟随来源：

- `ru-words.txt`：OpenSubtitles（CC BY-SA 4.0）+ Leeds 词表（CC BY 2.5）
- 语料频次：Leipzig Corpora（CC BY 4.0）、OpenSubtitles 字幕（Apache-2.0）
- 词典与形态：pymorphy3 及其 OpenCorpora 词典
- 例句：从上述语料里挑的句子，随语料许可

再分发数据文件时请保留上述署名。
