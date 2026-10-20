# 词表来源与许可

`../ru-words.txt` 是补全用的词频表（每行一个词，按词频降序排列，行号即排名）。

## 组成

| 来源 | 占比 | 许可 |
|---|---|---|
| **OpenSubtitles 2018** 字幕词频（口语） | 前 120,000 词 | **CC-BY-SA-4.0** |
| **Leeds 语料** 词表（书面语补充） | 补充 40,000 词 | CC BY 2.5 |

字幕词频表取自 [hermitdave/FrequencyWords](https://github.com/hermitdave/FrequencyWords)
（`content/2018/ru/ru_full.txt`，内容 CC-BY-SA-4.0，代码 MIT）。
原始语料来自 [OPUS OpenSubtitles2018](https://opus.nlpl.eu/OpenSubtitles-v2018.php)。

Leeds 部分来自 `russian-words/100000-russian-words.txt`（由 hingston 清理，CC BY 2.5）。

## 为什么混两种

字幕语料能反映**日常口语**的词频：`зав` 的第一候选是 `завтра`、`здр` 是 `здравствуйте`。
但它缺少书面/专业词，所以用 Leeds 词表补覆盖。

字幕也有 OCR 噪声（`декючр`、`ааа` 这类），构建时用 pymorphy3 的形态学词典过滤掉了
（丢弃约 2 万条）。重复字母连续出现 3 次以上的也一并丢掉。

## 重新生成

```bash
# 1. 下载字幕词频表到 %TEMP%\ru_full.txt
curl -o %TEMP%\ru_full.txt https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/ru/ru_full.txt

# 2. 构建
python data/build_wordlist.py
```

脚本会自动打印各前缀的首选词，方便回归检查。

## 用 `ru-words.txt` 的后果

- 文件 2.71 MB（旧表 1.7 MB），打包后的 exe 大约 +1 MB
- 加载 160,000 词约 175 ms，只在启动时一次
- 补全 0.04–0.15 ms，无感
