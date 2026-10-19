# -*- coding: utf-8 -*-
"""
阻止系统睡眠（会话期间有效，进程退出自动恢复）

原理：Windows 的 SetThreadExecutionState —— 这是应用层"我要保持唤醒"的标准做法，
      不修改任何电源计划设置，进程一退出就自动失效，可逆、干净。

策略：只申请 ES_SYSTEM_REQUIRED（阻止系统睡眠），不申请 ES_DISPLAY_REQUIRED，
      所以屏幕可以正常熄灭省电，但机器不会睡。

用法：
  python nosleep.py              # 一直保持，直到进程被杀
  python nosleep.py --duration 3600
"""
import argparse
import ctypes
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_AWAYMODE_REQUIRED = 0x00000040

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
PID_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nosleep.pid")


def hold():
    flags = ES_CONTINUOUS | ES_SYSTEM_REQUIRED
    r = k32.SetThreadExecutionState(ctypes.c_uint(flags))
    return r


def release():
    k32.SetThreadExecutionState(ctypes.c_uint(ES_CONTINUOUS))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--duration", type=int, default=0, help="0 = 一直保持")
    a = ap.parse_args()

    prev = hold()
    if not prev:
        print(f"SetThreadExecutionState 失败, err={ctypes.get_last_error()}")
        sys.exit(1)

    with open(PID_FILE, "w", encoding="utf-8") as fh:
        fh.write(str(os.getpid()))

    print(f"[nosleep] 已启用防睡眠 (pid={os.getpid()})")
    print("[nosleep] 屏幕可以熄灭，系统不会睡眠；进程退出即自动恢复。")
    t0 = time.time()
    try:
        while True:
            time.sleep(30)
            hold()                      # 保险起见周期性重申
            el = time.time() - t0
            if a.duration and el >= a.duration:
                print(f"[nosleep] 到达设定时长 {a.duration}s，退出。")
                break
            if int(el) % 1800 < 30:
                print(f"[nosleep] 已保持 {int(el/60)} 分钟")
    except KeyboardInterrupt:
        print("\n[nosleep] 收到中断")
    finally:
        release()
        try:
            os.remove(PID_FILE)
        except Exception:
            pass
        print("[nosleep] 已恢复系统默认睡眠策略")


if __name__ == "__main__":
    main()
