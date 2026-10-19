# Oleg's Russian Keyboard

给**中国俄语学习者**用的 Windows 俄语输入辅助工具。

它不是输入法，而是在你已有的俄语键盘布局（ЙЦУКЕН）之上加一层：

- **高频词补全** —— 打 `прив` 就提示 `привет`
- **拼写更正** —— 打 `привт` 提示 `привет`
- **变格提示** —— 打完 `другу` 告诉你这是「与格」，并列出全部词形
- **个人词频记忆** —— 你选过的词下次排前面
- **生词本** —— 一键收藏，导出 Markdown
- **形式词典** —— 查任意词的完整词形表

> 现状：**alpha**。主要在 Word 里实测通过；Chrome、微信等程序里候选条位置可能退化（见「已知限制」）。

---

## 为什么做这个

俄语在 Windows 上不是输入法，是**键盘布局**——装了俄语键盘就能打字，但没有任何"联想"。

而对中文母语者，真正的难点不是敲字母，是**变格**：知道 `друг`，但写句子时要变成 `другу`（与格）、`другом`（工具格）。系统输入法不会帮你，查词典也慢。

所以这个工具的优先级是：

```
词形提示  >>  拼写纠错  >  补全
```

不预测下一个词（那需要大规模对话语料），只解决"这个词该长什么样"。

---

## 安装

### 方式一：下载 exe（推荐）

1. 到 [Releases](../../releases) 下载 `OlegsRussianKeyboard.exe`
2. 双击运行，右下角托盘出现图标即可
3. 系统里需要**已安装俄语键盘**（设置 → 时间和语言 → 语言 → 添加俄语）

不需要安装 Python，不需要管理员权限。

> ### ⚠️ 第一次运行会被 Windows 拦截
>
> exe 没有购买代码签名，Windows SmartScreen 会提示
> **「Windows 已保护你的电脑」**。
>
> 处理方式：点 **更多信息** → **仍要运行**。
>
> （代码签名证书约 ¥1000/年，alpha 阶段先不买。如果你不放心，可以按下面的方式从源码运行。）

### 方式二：从源码运行

```powershell
pip install pymorphy3 pymorphy3-dicts-ru pywin32 uiautomation psutil pystray pillow
python p1/app.py
```

---

## 使用

### 打字时

切到俄语布局，正常打字。停顿约 0.3 秒后，光标下方会弹出候选条。

| 按键 | 作用 |
|---|---|
| `1` – `6` | 直接选第几个候选 |
| `←` `→` | 移动高亮 |
| `Enter` | 确认当前高亮 |
| `Tab` | 在「补全」和「变格」两种视图间切换 |
| `Ctrl+D` | 把当前词加入生词本 |
| `Ctrl+L` | 查这个词的完整词形表 |
| `Esc` | 关掉候选条 |

> 注意：候选条显示期间，`Enter` / 数字键 / 方向键会被程序接管。想换行请等它自动消失（约 1.5 秒）或按 `Esc`。

### 托盘菜单

- **暂停 / 继续**：暂时关掉候选条（默认双击图标）
- **生词本…**：查看收藏的词，右侧显示词形表
- **查词…**：打开形式词典
- **打开日志文件夹**
- **退出**

### 数据在哪

```
%APPDATA%\OlegsRussianKeyboard\
    app.log          运行日志
    settings.json    界面与排除程序设置
    rules.json       规则卡（存在时优先于内置版本）
    user_freq.json   个人词频记忆
    wordbook.json    生词本
    生词本.md        生词本导出（可直接粘到笔记）
```

**全部本地，不联网，不上传任何输入内容。**

### 自定义规则卡

托盘菜单 → **编辑规则卡…** 会自动把内置规则复制到 `%APPDATA%\OlegsRussianKeyboard\rules.json` 并打开记事本。

改完**重启助手**生效。格式：

```json
{
  "cards": [
    {
      "id": "unique-id",
      "title": "看到的中文提示",
      "pattern": "正则表达式",
      "why": "为什么错",
      "fix": "怎么改"
    }
  ]
}
```

`pattern` 是正则，会对整句做匹配。这条机制意味着**改规则不用重新打包 exe**。

### 配置

同目录下的 `settings.json`：

```json
{
  "font_size": null,
  "exclude_apps": ["game.exe", "some_app.exe"]
}
```

- `font_size`：候选条字号（像素）。`null` = 自动跟随正文光标大小
- `exclude_apps`：这些程序里不弹候选条（密码管理器已默认排除）

---

## 已知限制

- **只在 Word 里充分测试过**。其他程序的光标位置探测会退化到"鼠标位置"或"控件矩形"
- **Chromium 系程序**（Chrome / Edge / 微信）常常拿不到光标坐标，需要开启 accessibility 或只能退化
- **密码框**：已用 UIA 检测 `IsPassword` 排除，但这依赖程序正确暴露该属性
- **不是系统输入法**：候选条是独立窗口，无法像微软拼音那样嵌在应用内部（那是 TSF 的工作，见 Roadmap）
- 只支持 Windows 10/11 x64

---

## 从源码构建

```cmd
build.cmd
```

产物：`dist\OlegsRussianKeyboard.exe`（约 28 MB，单文件）

依赖：Python 3.12 + `requirements.txt`，打包用 PyInstaller。

---

## Roadmap

- [ ] 更多程序的光标定位适配
- [ ] 规则卡提示可展开（`чтобы`、`помочь тебя` 这类搭配错误）
- [ ] 真正的 TSF 输入法（系统级，可与应用内嵌）
- [ ] 俄语母语者审校释义与规则

---

## 第三方数据

- 词形分析：[pymorphy3](https://github.com/no-plagiarism/pymorphy3)（MIT）
- 词频表：`data/russian-words/100000-russian-words.txt`
  来自 [University of Leeds Corpus](http://corpus.leeds.ac.uk/frqc/internet-ru.num)，
  由 [hingston](https://github.com/hingston/russian) 整理，
  **CC BY 2.5** —— 允许商用，需署名（授权原文见 `data/russian-words/LICENSE.md`）

---

## License

MIT
