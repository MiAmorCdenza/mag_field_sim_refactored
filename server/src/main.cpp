// mf_server:节点引擎驱动的实时仿真服务器。
//
// 头less 集成模式(本轮验收):
//   mf_server --root <repo> --graph graphs/integration_test_graph.json
//     --frames 120 --particles 20000
// 流程:嵌入 Python → 加载图 → 烘焙 B/E/drag → 安装 C++ 表 →
//       数值对拍(网格节点处 C++ 采样 vs Python 烘焙)→ 参数回路(set_param) →
//       2 万粒子帧循环 + 编码。
//
// WebSocket 服务在下一阶段接入(协议沿用旧版 init_config/bake_progress/二进制帧)。
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <sstream>
#include <string>

#include "bake_bridge.h"
#include "sim_pipeline.h"
#include "../core/table3d.h"

static std::string read_file(const std::string& path) {
    std::ifstream f(path, std::ios::binary);
    std::ostringstream ss;
    ss << f.rdbuf();
    return ss.str();
}

static int failures = 0;
#define CHECK(cond, msg)                                                      \
    do {                                                                      \
        if (!(cond)) {                                                        \
            std::printf("FAIL: %s\n", msg);                                   \
            ++failures;                                                       \
        } else {                                                              \
            std::printf("  ok: %s\n", msg);                                   \
        }                                                                     \
    } while (0)

int main(int argc, char** argv) {
    std::string root = ".";
    std::string graph_path;
    int frames = 120, count = 20000;
    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        if (a == "--root" && i + 1 < argc) root = argv[++i];
        else if (a == "--graph" && i + 1 < argc) graph_path = argv[++i];
        else if (a == "--frames" && i + 1 < argc) frames = std::atoi(argv[++i]);
        else if (a == "--particles" && i + 1 < argc) count = std::atoi(argv[++i]);
    }
    if (graph_path.empty()) {
        std::printf("用法: mf_server --root <repo> --graph <json> [--frames N] [--particles N]\n");
        return 2;
    }

    std::printf("=== 1) 嵌入 Python 引擎 ===\n");
    BakeBridge bridge;
    std::string err;
    if (!bridge.init(root, err)) {
        std::printf("FAIL: 引擎初始化: %s\n", err.c_str());
        return 1;
    }
    CHECK(true, "Python 解释器与引擎加载");

    std::printf("=== 2) 图加载 ===\n");
    if (!bridge.load_graph(read_file(graph_path), err)) {
        std::printf("FAIL: 图加载: %s\n", err.c_str());
        return 1;
    }
    CHECK(true, "图 JSON 加载成功");

    std::printf("=== 3) 烘焙 B/E/drag ===\n");
    auto b = bridge.bake("B", err);
    CHECK(b.has_value(), ("B 烘焙: " + err).c_str());
    auto e = bridge.bake("E", err);
    CHECK(e.has_value(), ("E 烘焙: " + err).c_str());
    auto d = bridge.bake("drag", err);
    CHECK(d.has_value(), ("drag 烘焙: " + err).c_str());
    if (!b) return 1;
    std::printf("  B: %zu 格点 | E: %zu | drag: %zu\n", b->c0.size(),
                e ? e->c0.size() : 0, d ? d->c0.size() : 0);

    std::printf("=== 4) C++ 表 vs Python 烘焙 数值对拍 ===\n");
    {
        Table3D t;
        t.set_grid(b->xs, b->ys, b->zs, b->c0, b->c1, b->c2);
        auto axis_zero = [](const std::vector<double>& ax) {
            for (size_t i = 0; i < ax.size(); ++i)
                if (ax[i] == 0.0) return (int)i;
            return -1;
        };
        int ix = axis_zero(b->xs), iy = axis_zero(b->ys), iz = axis_zero(b->zs);
        CHECK(ix >= 0 && iy >= 0 && iz >= 0, "点阵轴包含原点");
        int ny = (int)b->ys.size(), nz = (int)b->zs.size();
        size_t flat = (size_t)ix * ny * nz + (size_t)iy * nz + iz;
        double sx, sy, sz;
        t.sample(0.0, 0.0, 0.0, sx, sy, sz);
        double d0 = std::abs(sx - b->c0[flat]) + std::abs(sy - b->c1[flat]) +
                    std::abs(sz - b->c2[flat]);
        CHECK(d0 < 1e-12, "网格节点处采样与烘焙数组一致");
    }

    std::printf("=== 5) 参数回路(kp 2.0 → 3.0) ===\n");
    {
        uint64_t v1 = bridge.graph_version();
        double flat_bx_before = 0.0;
        {
            int ny = (int)b->ys.size(), nz = (int)b->zs.size();
            for (size_t i = 0; i < b->xs.size(); ++i)
                if (b->xs[i] == 0.0) { flat_bx_before = b->c0[i * ny * nz]; break; }
        }
        CHECK(bridge.set_param("kp", "kp", 3.0, err), "set_param 成功");
        uint64_t v2 = bridge.graph_version();
        CHECK(v2 > v1, "图版本号 +1");
        auto b2 = bridge.bake("B", err);
        CHECK(b2.has_value(), "重新烘焙成功");
        if (b2) {
            int ny = (int)b2->ys.size(), nz = (int)b2->zs.size();
            double flat_bx_after = 0.0;
            for (size_t i = 0; i < b2->xs.size(); ++i)
                if (b2->xs[i] == 0.0) { flat_bx_after = b2->c0[i * ny * nz]; break; }
            CHECK(flat_bx_after != flat_bx_before, "烘焙表随参数更新");
        }
    }

    std::printf("=== 6) 2 万粒子帧循环 ===\n");
    {
        PipelineConfig cfg;
        cfg.particle_count = count;
        cfg.steps_per_frame = 5;
        cfg.emitter.mode = 0;
        cfg.emitter.v_base = 400.0;
        cfg.emitter.max_range = 15.0;
        cfg.emitter.types = {{1.0, 0.1, 1.0, 1.0, 0xff3333},
                             {-1.0, 0.1, 1.0, 1.0, 0x3333ff}};
        cfg.integrator.dt = 0.01;
        cfg.integrator.max_range = 15.0;

        SimPipeline pipe(cfg);
        CHECK(pipe.install_baked(*b, err), ("安装 B: " + err).c_str());
        if (e) pipe.install_baked(*e, err);
        if (d) pipe.install_baked(*d, err);

        auto t0 = std::chrono::steady_clock::now();
        for (int f = 0; f < frames; ++f) pipe.step_frame();
        auto t1 = std::chrono::steady_clock::now();
        double ms = std::chrono::duration<double, std::milli>(t1 - t0).count();
        std::printf("  %d 帧 × 5 步 总耗时 %.1f ms,平均 %.3f ms/步\n",
                    frames, ms, ms / (frames * 5));

        size_t bad = 0, alive = 0, hit = 0, out = 0;
        for (size_t i = 0; i < pipe.particles.count; ++i) {
            if (!std::isfinite(pipe.particles.x[i]) ||
                !std::isfinite(pipe.particles.y[i]) ||
                !std::isfinite(pipe.particles.z[i])) ++bad;
            if (pipe.particles.status[i] == 0) ++alive;
            else if (pipe.particles.status[i] == 1) ++hit;
            else ++out;
        }
        std::printf("  状态: 存活 %zu / 沉降 %zu / 出界 %zu / 非有限 %zu\n",
                    alive, hit, out, bad);
        CHECK(bad == 0, "全部位置有限(带真实烘焙场)");
        CHECK(alive + hit + out == pipe.particles.count, "状态机覆盖全部粒子");

        std::vector<uint8_t> buf;
        pipe.encode(buf);
        CHECK(buf.size() == (size_t)count * 21, "编码 = 21 字节/粒子");
    }

    std::printf(failures ? "\n[%d 项失败]\n" : "\n端到端集成全部通过 ✅\n", failures);
    return failures ? 1 : 0;
}
