# -*- coding: utf-8 -*-
"""
系统托盘：右下角图标 + 菜单。

菜单项：
  Oleg's Russian Keyboard   （标题，不可点）
  ─────────────
  ⏸ 暂停 / ▶ 继续
  生词本…
  查词…
  打开日志文件夹
  ─────────────
  退出

托盘动作都在自己的线程里，改 UI 一律通过 app.q 交给 Tk 主线程。
"""
import os
import subprocess
import sys
import threading


def _make_image(size=64):
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # 深色圆角方块 + 白色的 "Я"
    d.rounded_rectangle([2, 2, size - 3, size - 3], radius=12,
                        fill=(31, 34, 38, 255))
    try:
        from PIL import ImageFont
        font = ImageFont.truetype("segoeuib.ttf", int(size * 0.82))
    except Exception:
        font = None
    text = "O"          # 作者 Oleg 的首字母
    if font is not None:
        box = d.textbbox((0, 0), text, font=font)
        w, h = box[2] - box[0], box[3] - box[1]
        d.text(((size - w) / 2 - box[0], (size - h) / 2 - box[1]),
               text, font=font, fill=(255, 255, 255, 255))
    else:
        d.text((size * 0.3, size * 0.15), text, fill=(255, 255, 255, 255))
    return img


_IMAGES = {}


def _images():
    """返回 (就绪图, 待命图)。待命图调暗，一眼看出没在工作。"""
    if not _IMAGES:
        from PIL import ImageEnhance
        active = _make_image()
        _IMAGES["active"] = active
        _IMAGES["idle"] = ImageEnhance.Brightness(active).enhance(0.45)
    return _IMAGES["active"], _IMAGES["idle"]


def set_active(app, active):
    """切换托盘图标状态（俄语布局=亮，其他=暗）。"""
    icon = getattr(app, "tray_icon", None)
    if icon is None:
        return
    try:
        act, idle = _images()
        icon.icon = act if active else idle
        ver = getattr(app, "version", "")
        icon.title = (f"Oleg's Russian Keyboard v{ver}"
                      + ("" if active else "（待命 · 非俄语布局）"))
    except Exception:
        pass


def start(app):
    """启动托盘。返回 icon 对象（或 None 表示失败）。"""
    try:
        import pystray
        from pystray import Menu, MenuItem
    except Exception as e:
        app.log(f"[tray] pystray 不可用: {e}")
        return None

    def ui(fn):
        """把动作丢回 Tk 主线程执行。"""
        app.q.put(("ui", fn))

    def on_toggle(icon=None, item=None):
        state = {"paused": None}

        def do():
            app.set_paused(not app.paused)
            state["paused"] = app.paused
        ui(do)

    def on_wordbook(icon=None, item=None):
        ui(app.open_wordbook)

    def on_lookup(icon=None, item=None):
        ui(app.open_lookup_window)

    def on_rules(icon=None, item=None):
        ui(app.open_rules)

    def on_show_pill(icon=None, item=None):
        ui(app.show_pill)

    def on_font_big(icon=None, item=None):
        ui(lambda: app.bump_font(+2))

    def on_font_small(icon=None, item=None):
        ui(lambda: app.bump_font(-2))

    def on_font_reset(icon=None, item=None):
        ui(lambda: app.bump_font(0))

    def on_feedback(icon=None, item=None):
        ui(lambda: app.show_feedback())

    def on_autostart(icon=None, item=None):
        ui(lambda: app.toggle_autostart())

    def on_review(icon=None, item=None):
        ui(lambda: app.open_review())

    def on_anki(icon=None, item=None):
        ui(lambda: app.export_anki())

    def on_theme_dark(icon=None, item=None):
        ui(lambda: app.apply_theme("dark"))

    def on_theme_light(icon=None, item=None):
        ui(lambda: app.apply_theme("light"))

    def on_theme_auto(icon=None, item=None):
        ui(lambda: app.apply_theme("auto"))

    def on_logs(icon=None, item=None):
        try:
            d = os.path.dirname(app.logpath)
            os.makedirs(d, exist_ok=True)
            subprocess.Popen(["explorer", d])
        except Exception:
            pass

    def on_quit(icon=None, item=None):
        try:
            icon.visible = False
            icon.stop()
        except Exception:
            pass
        ui(app.quit)

    ver = getattr(app, "version", "")
    menu = Menu(
        MenuItem(f"Oleg's Russian Keyboard v{ver}", None, enabled=False),
        Menu.SEPARATOR,
        MenuItem(lambda item: "▶ 继续" if app.paused else "⏸ 暂停",
                 on_toggle, default=True),
        MenuItem("生词本…", on_wordbook),
        MenuItem("查词…", on_lookup),
        MenuItem("编辑规则卡…", on_rules),
        MenuItem("候选字号", Menu(
            MenuItem("增大 +2", on_font_big),
            MenuItem("减小 -2", on_font_small),
            MenuItem("恢复默认", on_font_reset),
        )),
        MenuItem("复习生词本", on_review),
        MenuItem("报告问题（附日志）", on_feedback),
        MenuItem("开机自启（开/关）", on_autostart),
        MenuItem("导出 Anki", on_anki),
        MenuItem("主题", Menu(
            MenuItem("深色", on_theme_dark),
            MenuItem("浅色", on_theme_light),
            MenuItem("跟随系统", on_theme_auto),
        )),
        MenuItem("显示状态条", on_show_pill),
        Menu.SEPARATOR,
        MenuItem("打开日志文件夹", on_logs),
        MenuItem("退出", on_quit),
    )

    icon = pystray.Icon("olegs_russian", _make_image(),
                        f"Oleg's Russian Keyboard v{ver}", menu)
    t = threading.Thread(target=icon.run, name="tray", daemon=True)
    t.start()
    app.tray_icon = icon
    app.log("[tray] 托盘已启动")
    return icon
