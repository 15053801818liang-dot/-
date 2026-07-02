"""跨平台原子比较交换（CAS）封装，支持 Windows/Linux/macOS
Windows: InterlockedCompareExchange (kernel32)
Linux/macOS: __atomic_compare_exchange_4 (libatomic.so.1)
"""

import ctypes
import ctypes.util
import platform

_cas_func = None
_cas_style = None  # "windows" | "libatomic"


def _init_cas():
    global _cas_func, _cas_style
    system = platform.system()

    if system == "Windows":
        kernel32 = ctypes.windll.kernel32
        _cas_func = kernel32.InterlockedCompareExchange
        _cas_func.argtypes = [ctypes.POINTER(ctypes.c_long), ctypes.c_long, ctypes.c_long]
        _cas_func.restype = ctypes.c_long
        _cas_style = "windows"
        return

    # Linux / macOS: libatomic.so.1 导出 __atomic_compare_exchange_4
    # 签名: _Bool __atomic_compare_exchange_4(int *ptr, int *expected, int desired,
    #                                          int weak, int success_memorder, int failure_memorder)
    # 返回 True 表示 *ptr==*expected 且已写入 desired；返回 False 表示 *expected 被更新为 *ptr
    for libname in ("libatomic.so.1", "libatomic.so"):
        try:
            lib = ctypes.CDLL(libname)
            _cas_func = lib.__atomic_compare_exchange_4
            _cas_func.argtypes = [
                ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_int),
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
            ]
            _cas_func.restype = ctypes.c_bool
            _cas_style = "libatomic"
            return
        except (OSError, AttributeError):
            continue

    raise RuntimeError(
        "No atomic CAS library found. "
        "Install libatomic1 (apt install libatomic1) on Linux."
    )


_init_cas()


def cas_int(addr_ptr, expected: int, new_val: int) -> bool:
    """
    对 int32 指针执行原子比较交换。
    返回 True 如果 *addr_ptr == expected 且已写入 new_val。
    """
    if _cas_style == "windows":
        old = _cas_func(addr_ptr, new_val, expected)
        return old == expected
    else:
        # libatomic: __atomic_compare_exchange_4
        # weak=0 (strong), success_memorder=5 (seq_cst), failure_memorder=5
        expected_ptr = ctypes.pointer(ctypes.c_int(expected))
        return _cas_func(addr_ptr, expected_ptr, new_val, 0, 5, 5)
