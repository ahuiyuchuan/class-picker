"""同一数据目录的 Windows 进程间互斥，覆盖事务之外的备份与文件替换。

@author ahui
只约束同一 Windows 会话中使用本锁的程序；其他旧版本或外部 SQLite 工具不受约束。
线程内可重入，以兼容写入后读取快照及恢复前生成保护备份。每次外层操作结束释放句柄。
"""

import ctypes
import hashlib
import os
import threading
from ctypes import wintypes


class DataLock:
    """与 with RLock 用法兼容；Windows 上额外按规范化数据库路径串行化操作。"""

    def __init__(self, path):
        """path 为数据库 Path；不读取名单，互斥量名称仅包含目录标识的 SHA-256。"""
        self._thread_lock = threading.RLock()
        self._depth = 0
        self._handle = None
        normalized = os.path.normcase(str(path.resolve()))
        self._name = (
            "Local\\ClassroomPicker-"
            + hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        )
        self._kernel = None
        if os.name == "nt":
            self._kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            self._kernel.CreateMutexW.argtypes = [
                ctypes.c_void_p,
                wintypes.BOOL,
                wintypes.LPCWSTR,
            ]
            self._kernel.CreateMutexW.restype = wintypes.HANDLE
            self._kernel.WaitForSingleObject.argtypes = [
                wintypes.HANDLE,
                wintypes.DWORD,
            ]
            self._kernel.WaitForSingleObject.restype = wintypes.DWORD
            for name in ("ReleaseMutex", "CloseHandle"):
                getattr(self._kernel, name).argtypes = [wintypes.HANDLE]
                getattr(self._kernel, name).restype = wintypes.BOOL

    def __enter__(self):
        """最多等待其他进程 5 秒；超时未执行写入，调用者可提示稍后重试。"""
        self._thread_lock.acquire()
        try:
            if self._depth == 0 and self._kernel:
                handle = self._kernel.CreateMutexW(None, False, self._name)
                if not handle:
                    raise ctypes.WinError(ctypes.get_last_error())
                result = self._kernel.WaitForSingleObject(handle, 5000)
                # WAIT_ABANDONED 表示前任进程意外退出；此时已拥有锁，SQLite 负责日志恢复。
                if result not in (0, 0x80):
                    error = ctypes.get_last_error()
                    self._kernel.CloseHandle(handle)
                    if result == 0x102:
                        raise ValueError("另一窗口正在处理数据，请稍后重试")
                    raise ctypes.WinError(error)
                self._handle = handle
            self._depth += 1
            return self
        except BaseException:
            self._thread_lock.release()
            raise

    def __exit__(self, exc_type, exc_value, traceback):
        """最后一层退出时释放系统互斥与句柄；异常原样传播，不吞掉事务失败。"""
        try:
            self._depth -= 1
            if self._depth == 0 and self._handle:
                try:
                    self._kernel.ReleaseMutex(self._handle)
                finally:
                    self._kernel.CloseHandle(self._handle)
                    self._handle = None
        finally:
            self._thread_lock.release()
