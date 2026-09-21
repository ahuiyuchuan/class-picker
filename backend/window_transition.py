"""GUI 线程内批量切换窗口尺寸，防止中间还原状态被逐帧绘制。

@author ahui
保留 WinForms 管理的还原矩形，不直接写原生 placement 绕开其尺寸缓存。
只临时关闭本窗口重绘和 DWM 过渡，finally 必须恢复，不能修改系统动画设置。
"""

import ctypes
from contextlib import contextmanager
from ctypes import wintypes


@contextmanager
def batch_window_transition(form):
    """合并布局并冻结重绘，结束后按最终尺寸绘制一次；异常原样向调用者传播。

    Args:
        form: 当前 GUI 线程中的已显示 WinForms 窗口，内部控件由 Dock 自动布局。
    """
    handle = form.Handle.ToInt64()
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.SendMessageW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        ctypes.c_size_t,
        ctypes.c_ssize_t,
    ]
    user32.SendMessageW.restype = ctypes.c_ssize_t
    user32.RedrawWindow.argtypes = [
        wintypes.HWND,
        ctypes.c_void_p,
        wintypes.HANDLE,
        wintypes.UINT,
    ]
    user32.RedrawWindow.restype = wintypes.BOOL
    dwm = ctypes.WinDLL("dwmapi")
    signature = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    dwm.DwmGetWindowAttribute.argtypes = signature
    dwm.DwmGetWindowAttribute.restype = ctypes.c_long
    dwm.DwmSetWindowAttribute.argtypes = signature
    dwm.DwmSetWindowAttribute.restype = ctypes.c_long
    previous = wintypes.BOOL()
    disabled = wintypes.BOOL(True)
    supported = (
        dwm.DwmGetWindowAttribute(
            handle, 3, ctypes.byref(previous), ctypes.sizeof(previous)
        )
        == 0
    )
    form.SuspendLayout()
    try:
        user32.SendMessageW(handle, 0x000B, 0, 0)  # WM_SETREDRAW(false)
        if supported:
            dwm.DwmSetWindowAttribute(
                handle, 3, ctypes.byref(disabled), ctypes.sizeof(disabled)
            )
        yield
    finally:
        try:
            # Dock 布局延迟到最终尺寸；WebView 不跟随每次 Normal/Maximized 中间态缩放。
            form.ResumeLayout(True)
        finally:
            user32.SendMessageW(handle, 0x000B, 1, 0)
            user32.RedrawWindow(
                handle, None, None, 0x0585
            )  # invalidate/frame/allchildren/update
            if supported:
                dwm.DwmSetWindowAttribute(
                    handle, 3, ctypes.byref(previous), ctypes.sizeof(previous)
                )
