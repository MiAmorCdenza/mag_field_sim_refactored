// DLL 加载耗时基准:LoadLibrary/FreeLibrary 循环。
// 编译: cl /EHsc /O2 /std:c++17 /utf-8 dll_bench.cpp
#include <chrono>
#include <cstdio>
#include <windows.h>

int main() {
    const char* dll = "bench_dll.dll";
    // 预热
    HMODULE h = LoadLibraryA(dll);
    if (h) FreeLibrary(h);

    const int N = 200;
    auto t0 = std::chrono::steady_clock::now();
    for (int i = 0; i < N; ++i) {
        h = LoadLibraryA(dll);
        if (!h) {
            std::printf("FAIL: LoadLibrary err=%lu\n", GetLastError());
            return 1;
        }
        FreeLibrary(h);
    }
    auto t1 = std::chrono::steady_clock::now();
    double ms = std::chrono::duration<double, std::milli>(t1 - t0).count();
    std::printf("LoadLibrary+FreeLibrary ×%d: 总 %.1f ms,平均 %.3f ms/次\n",
                N, ms, ms / N);
    return 0;
}
