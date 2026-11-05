"""Windows workbook writer coordination.

Used by both tracker servers and the scheduled scan launcher. The mutex is
process-wide across Windows sessions; it never locks the workbook for reading.
"""
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import hashlib
import os
from pathlib import Path


def mutex_name(workbook):
    canonical = str(Path(workbook).resolve()).lower()
    return 'Global\\JobSearchHQ-Workbook-' + hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:24]


@contextmanager
def workbook_lock(workbook):
    if os.name != 'nt':
        raise RuntimeError('The workbook writer lock is configured for Windows only.')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.ReleaseMutex.argtypes = [wintypes.HANDLE]
    kernel.ReleaseMutex.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.CreateMutexW(None, False, mutex_name(workbook))
    if not handle:
        raise PermissionError('Cannot acquire the spreadsheet writer lock.')
    owned = False
    try:
        status = kernel.WaitForSingleObject(handle, 0)
        if status not in (0, 0x80):  # Acquired, or recovered from a terminated owner.
            raise PermissionError('The scan or another tracker save owns the spreadsheet.')
        owned = True
        yield
    finally:
        if owned:
            kernel.ReleaseMutex(handle)
        kernel.CloseHandle(handle)
