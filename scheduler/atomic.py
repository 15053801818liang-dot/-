"""跨平台原子 CAS (libatomic)"""

import ctypes
import ctypes.util
import sys
import platform

_cas32 = None
_cas64 = None

def _init_atomic():
    global _cas32, _cas64
    system = platform.system()

    if system == "Windows":
        kernel32 = ctypes.windll.kernel32
        _cas32 = kernel32.InterlockedCompareExchange
        _cas32.argtypes = [ctypes.POINTER(ctypes.c_int32), ctypes.c_int32, ctypes.c_int32]
        _cas32.restype = ctypes.c_int32
        _cas64 = kernel32.InterlockedCompareExchange64
        _cas64.argtypes = [ctypes.POINTER(ctypes.c_int64), ctypes.c_int64, ctypes.c_int64]
        _cas64.restype = ctypes.c_int64
        return

    lib_names = ['libatomic.so.1', 'libatomic.so', 'libatomic.dylib']
    lib = None
    for name in lib_names:
        try:
            lib = ctypes.CDLL(name)
            break
        except OSError:
            continue

    if lib is None:
        raise RuntimeError("libatomic not found")

    try:
        _cas32 = lib.__atomic_compare_exchange_4
        _cas32.argtypes = [
            ctypes.POINTER(ctypes.c_int32),
            ctypes.POINTER(ctypes.c_int32),
            ctypes.c_int32,
            ctypes.c_bool,
            ctypes.c_int,
            ctypes.c_int,
        ]
        _cas32.restype = ctypes.c_bool
    except AttributeError:
        raise RuntimeError("__atomic_compare_exchange_4 not found in libatomic")

    try:
        _cas64 = lib.__atomic_compare_exchange_8
        _cas64.argtypes = [
            ctypes.POINTER(ctypes.c_int64),
            ctypes.POINTER(ctypes.c_int64),
            ctypes.c_int64,
            ctypes.c_bool,
            ctypes.c_int,
            ctypes.c_int,
        ]
        _cas64.restype = ctypes.c_bool
    except AttributeError:
        pass

_init_atomic()

def cas32(addr_ptr, expected, new):
    """32-bit 原子 CAS"""
    if platform.system() == "Windows":
        old = _cas32(addr_ptr, new, expected)
        return old == expected
    expected_ptr = ctypes.pointer(ctypes.c_int32(expected))
    return _cas32(addr_ptr, expected_ptr, new, False, 0, 0)

def cas64(addr_ptr, expected, new):
    """64-bit 原子 CAS"""
    if platform.system() == "Windows":
        old = _cas64(addr_ptr, new, expected)
        return old == expected
    expected_ptr = ctypes.pointer(ctypes.c_int64(expected))
    return _cas64(addr_ptr, expected_ptr, new, False, 0, 0)
