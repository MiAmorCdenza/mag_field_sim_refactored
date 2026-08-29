"""用 dbghelp 把崩溃偏移解析为符号(需要 /DEBUG 构建的 .pdb)。

用法: python tests/stackresolve.py <exe路径> <pdb路径> <偏移1> [偏移2 ...]
"""
import ctypes
import sys
from ctypes import wintypes

exe = sys.argv[1]
pdb_dir = sys.argv[2]
offsets = [int(x, 0) for x in sys.argv[3:]]

dbghelp = ctypes.WinDLL("dbghelp.dll")
kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)

SYMOPT_UNDNAME = 0x00000002
SYMOPT_DEFERRED_LOADS = 0x00000004


class SYMBOL_INFO(ctypes.Structure):
    _fields_ = [("SizeOfStruct", wintypes.ULONG),
                ("TypeIndex", wintypes.ULONG),
                ("Reserved", ctypes.c_uint64 * 2),
                ("Index", wintypes.ULONG),
                ("Size", wintypes.ULONG),
                ("ModBase", ctypes.c_uint64),
                ("Flags", wintypes.ULONG),
                ("Value", ctypes.c_uint64),
                ("Address", ctypes.c_uint64),
                ("Register", wintypes.ULONG),
                ("Scope", wintypes.ULONG),
                ("Tag", wintypes.ULONG),
                ("NameLen", wintypes.ULONG),
                ("MaxNameLen", wintypes.ULONG),
                ("Name", ctypes.c_char * 2048)]


h = ctypes.c_void_p(ctypes.cast(ctypes.pointer(ctypes.c_int(0)),
                                ctypes.c_void_p).value or 0)
# 用 GetCurrentProcess() 作为假句柄
h = kernel32.GetCurrentProcess()

dbghelp.SymSetOptions(SYMOPT_UNDNAME | SYMOPT_DEFERRED_LOADS)
ok = dbghelp.SymInitialize(h, None, False)
if not ok:
    print("SymInitialize 失败:", ctypes.get_last_error())
    sys.exit(1)

base = dbghelp.SymLoadModuleEx(h, None, exe.encode(), None, 0x10000000, 0,
                                None, 0)
if base == 0:
    print("SymLoadModuleEx 失败:", ctypes.get_last_error())
    sys.exit(1)
print(f"模块基址: 0x{base:X}")

dbghelp.SymSetSearchPath(h, pdb_dir.encode(), False)

for off in offsets:
    addr = base + off
    info = SYMBOL_INFO()
    info.SizeOfStruct = ctypes.sizeof(SYMBOL_INFO)
    info.MaxNameLen = 2047
    disp = ctypes.c_uint64(0)
    sym_ok = dbghelp.SymFromAddr(h, ctypes.c_uint64(addr),
                                 ctypes.byref(disp), ctypes.byref(info))
    if sym_ok:
        print(f"0x{off:06X}: {info.Name.decode(errors='replace')}+0x{disp.value:X}")
    else:
        # 找最近的符号(向前回溯)
        near = SYMBOL_INFO()
        near.SizeOfStruct = ctypes.sizeof(SYMBOL_INFO)
        near.MaxNameLen = 2047
        disp2 = ctypes.c_uint64(0)
        ok2 = dbghelp.SymFromAddr(h, ctypes.c_uint64(addr), ctypes.byref(disp2),
                                  ctypes.byref(near))
        print(f"0x{off:06X}: <无符号> err={ctypes.get_last_error()}")

dbghelp.SymCleanup(h)
