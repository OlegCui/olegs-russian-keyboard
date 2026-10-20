# -*- coding: utf-8 -*-
"""
桌宠：右下角的卡通布偶猫。

替代底部居中的状态条。能干的事：
- 鼠标左键点一下 → 打开菜单（和状态条右击同一套）
- 按住拖动 → 换位置，位置会记住
- 有消息时头上冒气泡（"已加入生词本：суббота"），几秒后自动消失
- 闲置时轻轻上下浮动，偶尔眨眼

实现要点
--------
- 窗口用 ``-transparentcolor`` 抠掉背景，剩下鲸鱼和气泡，看起来是贴纸
- 加 ``WS_EX_NOACTIVATE``：点它不会抢走正在打字窗口的焦点
- 只在有动画帧时重绘，其余时间靠 after 定时器，几乎不占 CPU
"""
import ctypes
import os

import tkinter as tk

user32 = ctypes.WinDLL("user32", use_last_error=True)
GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080

KEY = "#010203"          # 抠图用的色键（正常画面里不会出现的颜色）
W, H = 250, 210          # 窗口大小：上面留给气泡，下面放猫
BODY = 92                # 鲸鱼尺寸


FUR = (248, 240, 229, 255)       # 奶油色身体
FUR2 = (255, 252, 247, 255)      # 胸口更亮
POINT = (154, 130, 112, 255)     # 重点色（面罩 / 耳朵 / 腿 / 尾巴）
POINT_D = (124, 102, 86, 255)
EYE = (96, 168, 226, 255)        # 布偶猫的蓝眼睛
EYE_D = (30, 74, 116, 255)
PINK = (234, 158, 158, 255)


class _RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


def work_area():
    """桌面可用区（不含任务栏）。SPI_GETWORKAREA = 0x0030。"""
    r = _RECT()
    try:
        if user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0):
            return r.left, r.top, r.right, r.bottom
    except Exception:
        pass
    try:
        return (0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))
    except Exception:
        return 0, 0, 1920, 1080


def _make_cat(size=BODY, blink=False):
    """原创卡通布偶猫。

    布偶猫的三个识别特征都画了：重点色面罩、中间 V 形白条、蓝眼睛。
    没有复刻任何受版权保护的角色设计。
    """
    from PIL import Image, ImageDraw

    S = size * 3
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, r = S * 0.5, S / 2.0

    # 影子
    d.ellipse([cx - r * 0.44, r * 1.68, cx + r * 0.44, r * 1.86],
              fill=(0, 0, 0, 55))
    # 尾巴（蓬松，重点色）
    d.ellipse([cx + r * 0.26, r * 1.00, cx + r * 0.88, r * 1.64], fill=POINT)
    d.ellipse([cx + r * 0.40, r * 0.86, cx + r * 0.78, r * 1.26], fill=POINT)
    # 身体
    d.ellipse([cx - r * 0.46, r * 0.74, cx + r * 0.46, r * 1.62], fill=FUR2)
    # 前腿 + 爪尖
    d.ellipse([cx - r * 0.38, r * 1.24, cx - r * 0.12, r * 1.70], fill=POINT)
    d.ellipse([cx + r * 0.12, r * 1.24, cx + r * 0.38, r * 1.70], fill=POINT)
    d.ellipse([cx - r * 0.38, r * 1.54, cx - r * 0.12, r * 1.70], fill=FUR2)
    d.ellipse([cx + r * 0.12, r * 1.54, cx + r * 0.38, r * 1.70], fill=FUR2)
    # 耳朵
    d.polygon([(cx - r * 0.52, r * 0.34), (cx - r * 0.46, r * -0.08),
               (cx - r * 0.14, r * 0.22)], fill=POINT)
    d.polygon([(cx + r * 0.52, r * 0.34), (cx + r * 0.46, r * -0.08),
               (cx + r * 0.14, r * 0.22)], fill=POINT)
    d.polygon([(cx - r * 0.44, r * 0.28), (cx - r * 0.42, r * 0.04),
               (cx - r * 0.24, r * 0.18)], fill=PINK)
    d.polygon([(cx + r * 0.44, r * 0.28), (cx + r * 0.42, r * 0.04),
               (cx + r * 0.24, r * 0.18)], fill=PINK)
    # 头
    d.ellipse([cx - r * 0.50, r * 0.08, cx + r * 0.50, r * 0.94], fill=FUR)
    # 重点色面罩
    d.ellipse([cx - r * 0.47, r * 0.10, cx + r * 0.47, r * 0.68], fill=POINT)
    # 中间 V 形白条
    d.polygon([(cx - r * 0.13, r * 0.10), (cx + r * 0.13, r * 0.10),
               (cx + r * 0.05, r * 0.60), (cx, r * 0.70),
               (cx - r * 0.05, r * 0.60)], fill=FUR)
    # 下半张脸回到奶油色
    d.ellipse([cx - r * 0.44, r * 0.54, cx + r * 0.44, r * 1.10], fill=FUR)
    d.polygon([(cx - r * 0.13, r * 0.54), (cx + r * 0.13, r * 0.54),
               (cx, r * 0.72)], fill=FUR)

    # 眼睛
    for sx in (-1, 1):
        x = cx + sx * r * 0.25
        d.ellipse([x - r * 0.135, r * 0.38, x + r * 0.135, r * 0.62], fill=EYE)
        if blink:
            d.chord([x - r * 0.135, r * 0.38, x + r * 0.135, r * 0.62],
                    start=180, end=360, fill=FUR)
            d.arc([x - r * 0.135, r * 0.42, x + r * 0.135, r * 0.60],
                  start=195, end=345, fill=EYE_D, width=max(2, S // 70))
        else:
            d.ellipse([x - r * 0.05, r * 0.44, x + r * 0.05, r * 0.56], fill=EYE_D)
            d.ellipse([x - r * 0.03, r * 0.415, x + r * 0.01, r * 0.455],
                      fill=(255, 255, 255, 255))

    # 鼻子 / 嘴 / 胡须
    d.polygon([(cx - r * 0.055, r * 0.72), (cx + r * 0.055, r * 0.72),
               (cx, r * 0.79)], fill=PINK)
    d.arc([cx - r * 0.10, r * 0.76, cx - r * 0.004, r * 0.85],
          start=0, end=110, fill=POINT_D, width=max(2, S // 65))
    d.arc([cx + r * 0.004, r * 0.76, cx + r * 0.10, r * 0.85],
          start=70, end=180, fill=POINT_D, width=max(2, S // 65))
    for sx in (-1, 1):
        for dy in (-0.03, 0.0, 0.03):
            d.line([(cx + sx * r * 0.10, r * (0.76 + dy)),
                    (cx + sx * r * 0.50, r * (0.72 + dy * 1.8))],
                   fill=(214, 204, 194, 200), width=max(1, S // 120))

    return img.resize((size, size), getattr(Image, "LANCZOS", Image.BICUBIC))


def _load_custom(path, size=BODY):
    """用户自己的图。等比缩放到 size。"""
    try:
        from PIL import Image
        if not path or not os.path.exists(path):
            return None
        img = Image.open(path).convert("RGBA")
        w, h = img.size
        k = size / float(max(w, h))
        return img.resize((max(1, int(w * k)), max(1, int(h * k))),
                          getattr(Image, "LANCZOS", Image.BICUBIC))
    except Exception:
        return None


class DesktopPet:
    def __init__(self, root, app=None, pos=None, on_menu=None,
                 image_path=None):
        from PIL import ImageTk

        self.root = root
        self.app = app
        self.on_menu = on_menu
        self._ImageTk = ImageTk
        self._hide_job = None
        self._bob_job = None
        self._blink_job = None
        self._bubble = ""
        self._drag = None
        self.bob = 0

        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        try:
            self.win.attributes("-transparentcolor", KEY)
        except Exception:
            pass
        self.win.configure(bg=KEY)
        self.canvas = tk.Canvas(self.win, width=W, height=H, bg=KEY,
                                highlightthickness=0, bd=0)
        self.canvas.pack()

        custom = _load_custom(image_path, BODY)
        if custom is not None:
            self._img = ImageTk.PhotoImage(custom)
            self._img_blink = self._img          # 自定义图不做眨眼
        else:
            self._img = ImageTk.PhotoImage(_make_cat())
            self._img_blink = ImageTk.PhotoImage(_make_cat(blink=True))
        self._cat_y = H - BODY // 2 - 8
        self.whale = self.canvas.create_image(W // 2, self._cat_y,
                                              image=self._img)
        self.bubble_id = self.canvas.create_text(
            W // 2, 30, text="", fill="#ffffff", width=W - 20,
            font=("Microsoft YaHei UI", -11), justify="center")
        self.bubble_bg = self.canvas.create_rectangle(
            0, 0, 0, 0, fill="#252525", outline="#3d3d3d", width=1)

        self._place(pos)
        self._bind()
        self._no_activate()
        self._schedule_bob()
        self._schedule_blink()

    # ---------- 位置 ----------
    def _place(self, pos=None):
        # 用「工作区」而不是整屏，否则窗口会压在任务栏的日期时间上
        l, t, r, b = work_area()
        x, y = pos if pos else (r - W - 16, b - H - 2)
        x = max(l, min(int(x), r - W))
        y = max(t, min(int(y), b - H))
        self._bounds = (l, t, r, b)
        self.win.geometry(f"{W}x{H}+{x}+{y}")

    def position(self):
        return self.win.winfo_x(), self.win.winfo_y()

    def _no_activate(self):
        try:
            child = self.win.winfo_id()
            h = user32.GetAncestor(child, 2) or child
            ex = user32.GetWindowLongW(h, GWL_EXSTYLE)
            user32.SetWindowLongW(h, GWL_EXSTYLE,
                                  ex | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
        except Exception:
            pass

    # ---------- 交互 ----------
    def _bind(self):
        for w in (self.canvas, self.win):
            w.bind("<Button-1>", self._down)
            w.bind("<B1-Motion>", self._drag_move)
            w.bind("<ButtonRelease-1>", self._up)
            w.bind("<Button-3>", self._menu)
            w.bind("<Double-Button-1>", self._menu)

    def _down(self, e):
        self._drag = (e.x_root - self.win.winfo_x(),
                      e.y_root - self.win.winfo_y(), False)

    def _drag_move(self, e):
        if not self._drag:
            return
        dx, dy, moved = self._drag
        nx, ny = e.x_root - dx, e.y_root - dy
        l, t, r, b = work_area()
        nx = max(l, min(int(nx), r - W))
        ny = max(t, min(int(ny), b - H))
        if abs(nx - self.win.winfo_x()) > 2 or abs(ny - self.win.winfo_y()) > 2:
            self._drag = (dx, dy, True)
        self.win.geometry(f"+{nx}+{ny}")

    def _up(self, e):
        if not self._drag:
            return
        moved = self._drag[2]
        self._drag = None
        if moved:
            self._save_pos()
        else:
            self._menu(e)

    def _menu(self, e=None):
        if self.on_menu:
            try:
                self.on_menu()
            except Exception:
                pass

    def _save_pos(self):
        if self.app is not None and hasattr(self.app, "_save_setting"):
            try:
                x, y = self.position()
                self.app._save_setting("pet_position", [x, y])
            except Exception:
                pass

    # ---------- 气泡 ----------
    def say(self, text, ok=True, autohide=3000):
        self._bubble = text or ""
        self._render_bubble(text)
        if self._hide_job:
            try:
                self.root.after_cancel(self._hide_job)
            except Exception:
                pass
            self._hide_job = None
        if text and autohide:
            self._hide_job = self.root.after(autohide, self._clear_bubble)

    def _render_bubble(self, text):
        c = self.canvas
        if not text:
            self._clear_bubble()
            return
        # 太长就截断，别把窗口撑爆
        shown = text if len(text) <= 42 else text[:40] + "…"
        c.itemconfigure(self.bubble_id, text=shown)
        bbox = c.bbox(self.bubble_id) or (0, 0, 0, 0)
        pad = 9
        cat_top = self._cat_y - BODY // 2
        h = bbox[3] - bbox[1]
        bottom = cat_top - 6                     # 气泡底边贴猫头顶
        top = max(4, bottom - h - pad * 2)
        x0 = max(4, W // 2 - (bbox[2] - bbox[0]) // 2 - pad)
        x1 = min(W - 4, x0 + (bbox[2] - bbox[0]) + pad * 2)
        c.coords(self.bubble_bg, x0, top, x1, bottom)
        # 文本在气泡里居中
        c.coords(self.bubble_id, (x0 + x1) // 2, (top + bottom) // 2)
        c.tag_raise(self.bubble_bg)
        c.tag_raise(self.bubble_id)

    def _clear_bubble(self):
        self._bubble = ""
        self.canvas.itemconfigure(self.bubble_id, text="")
        self.canvas.coords(self.bubble_bg, 0, 0, 0, 0)

    # ---------- 动画 ----------
    def _schedule_bob(self):
        def tick():
            self.bob = 0 if self.bob else -3
            base = self._cat_y
            self.canvas.coords(self.whale, W // 2, base + self.bob)
            self._bob_job = self.root.after(900, tick)
        self._bob_job = self.root.after(900, tick)

    def _schedule_blink(self):
        def tick():
            try:
                self.canvas.itemconfigure(self.whale, image=self._img_blink)
                self.root.after(140, lambda: self.canvas.itemconfigure(
                    self.whale, image=self._img))
            except Exception:
                pass
            self._blink_job = self.root.after(5200, tick)
        self._blink_job = self.root.after(5200, tick)

    # ---------- 生命周期 ----------
    def set_theme(self, name):
        """气泡跟着主题走。"""
        try:
            import app as app_mod
            t = app_mod.THEMES[app_mod.resolve_theme(name)]
            self.canvas.itemconfigure(self.bubble_bg, fill=t["bg"],
                                      outline=t["border"])
            self.canvas.itemconfigure(self.bubble_id, fill=t["text"])
        except Exception:
            pass

    def hide(self):
        try:
            self.win.withdraw()
        except Exception:
            pass

    def show(self):
        try:
            self.win.deiconify()
        except Exception:
            pass

    def destroy(self):
        for job in (self._bob_job, self._blink_job, self._hide_job):
            if job:
                try:
                    self.root.after_cancel(job)
                except Exception:
                    pass
        try:
            self.win.destroy()
        except Exception:
            pass
