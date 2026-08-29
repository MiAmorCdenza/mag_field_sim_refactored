// 最小基准 DLL:带导出函数 + DllMain + 静态初始化器。
#include <windows.h>

static int g_init = 0;

// 静态初始化器(模拟真实插件的一小段初始化)
static const int s_static = []() -> int { return 42; }();

extern "C" __declspec(dllexport) int bench_probe(int x) {
    return x + s_static + g_init;
}

BOOL WINAPI DllMain(HINSTANCE, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) g_init = 1;
    return TRUE;
}
