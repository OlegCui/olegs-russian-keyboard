# -*- coding: utf-8 -*-
"""
开机自启：写 HKCU 的 Run 键。

为什么用注册表而不是启动文件夹
------------------------------
注册表 Run 键只影响当前用户（不需要管理员）、改名/移动后容易修正，
启动文件夹还会在资源管理器里留一个快捷方式，用户容易误删。
"""
import os
import sys

APP_NAME = "OlegsRussianKeyboard"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _command():
    """启动命令：打包后是 exe 自己，开发时是 pythonw + app.py。"""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    here = os.path.dirname(os.path.abspath(__file__))
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    exe = pyw if os.path.exists(pyw) else sys.executable
    return f'"{exe}" "{os.path.join(here, "app.py")}"'


def is_enabled():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            try:
                winreg.QueryValueEx(k, APP_NAME)
                return True
            except FileNotFoundError:
                return False
    except Exception:
        return False


def enable():
    try:
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, _command())
        return True
    except Exception:
        return False


def disable():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY,
                            0, winreg.KEY_SET_VALUE) as k:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except FileNotFoundError:
                pass
        return True
    except Exception:
        return False


def set_enabled(on):
    return enable() if on else disable()
