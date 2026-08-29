// 头less 基准与正确性测试:无 WS/无 Python,纯原生热路径。
//
// 验证:
// 1) 能量守恒:纯磁场中单粒子 |v| 守恒(Boris 数值性质)
// 2) 性能:2 万粒子 × 5 步/帧 × 300 帧(与旧引擎同负载),报告 ms/步
// 3) 稳定性:全部位置有限,状态机正常(沉降/出界)
// 4) 编码:21 字节/粒子,往返解码一致
//
// 编译(MSVC): cl /EHsc /O2 /std:c++17 /I..\core headless_main.cpp
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <random>
#include <vector>

#include "vec3.h"
#include "table3d.h"
#include "particles.h"
#include "emitters.h"
#include "boris.h"
#include "advancers.h"
#include "encoder.h"
#include "plan.h"

// 拉伸轴(近地 0.1,外部幂律) —— 与引擎 Lattice 同构
static std::vector<double> stretched(double vmin, double vmax, int n_total,
                                     double inner_half = 3.0, double inner_dx = 0.1) {
    std::vector<double> inner;
    for (double v = std::max(vmin, -inner_half);
         v <= std::min(vmax, inner_half) + inner_dx * 0.5; v += inner_dx)
        inner.push_back(v);
    int n_outer = n_total - (int)inner.size();
    if (n_outer <= 0) return inner;
    std::vector<double> out;
    double span_left = inner.front() - vmin, span_right = vmax - inner.back();
    int n_left = std::max(1, (int)(n_outer * span_left / (span_left + span_right)));
    int n_right = std::max(1, n_outer - n_left);
    for (int i = n_left - 1; i >= 0; --i) {
        double t = (n_left <= 1) ? 0.0 : (double)i / (n_left - 1);
        out.push_back(inner.front() - span_left * std::pow(t, 1.8));
    }
    for (double v : inner) out.push_back(v);
    for (int i = 0; i < n_right; ++i) {
        double t = (n_right <= 1) ? 1.0 : (double)i / (n_right - 1);
        out.push_back(inner.back() + span_right * std::pow(t, 1.8));
    }
    // 去重(端点可能与内部区重复;重复轴值会导致插值除零)
    out.erase(std::unique(out.begin(), out.end(),
                          [](double a, double b) { return std::abs(a - b) < 1e-12; }),
              out.end());
    return out;
}

// 倾斜偶极子合成表(归一化单位,与引擎 fallback 同标度)
static void fill_dipole(Table3D& t, double ps) {
    double mx = -std::sin(ps), mz = -std::cos(ps);
    t.bx.assign(t.nx * t.ny * t.nz, 0.0);
    t.by.assign(t.nx * t.ny * t.nz, 0.0);
    t.bz.assign(t.nx * t.ny * t.nz, 0.0);
    int idx = 0;
    for (int i = 0; i < t.nx; ++i)
        for (int j = 0; j < t.ny; ++j)
            for (int k = 0; k < t.nz; ++k, ++idx) {
                double x = t.xs[i], y = t.ys[j], z = t.zs[k];
                double r2 = x * x + y * y + z * z;
                if (r2 < 0.01) continue;
                double r = std::sqrt(r2), r3 = r2 * r, r5 = r3 * r2;
                double md = mx * x + mz * z;
                t.bx[idx] = 3.0 * md * x / r5 - mx / r3;
                t.by[idx] = 3.0 * md * y / r5;
                t.bz[idx] = 3.0 * md * z / r5 - mz / r3;
            }
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

int main() {
    const double PS = 0.5;
    std::printf("=== 1) 合成偶极表 ===\n");
    Table3D b_table;
    b_table.set_grid(stretched(-15.0, 10.0, 70), stretched(-12.0, 12.0, 64),
                     stretched(-12.0, 12.0, 64),
                     std::vector<double>(70 * 64 * 64), {}, {});
    fill_dipole(b_table, PS);
    CHECK(b_table.has_data(), "表构建完成");

    std::printf("=== 2) 能量守恒(纯磁场, E=0, 引力/大气关) ===\n");
    {
        Particles one;
        one.resize(1);
        one.id[0] = 0;
        one.x[0] = 3.0; one.y[0] = 0.0; one.z[0] = 0.0;
        one.vx[0] = 0.0; one.vy[0] = 0.02; one.vz[0] = 0.01;
        one.q[0] = 1.0; one.m[0] = 1.0; one.color[0] = 0xffffff; one.status[0] = 0;
        IntegratorConfig cfg;
        cfg.dt = 0.01; cfg.max_range = 90.0;
        ForceTables ft{&b_table, nullptr, nullptr};
        double v0 = std::sqrt(one.vx[0] * one.vx[0] + one.vy[0] * one.vy[0] +
                              one.vz[0] * one.vz[0]);
        for (int s = 0; s < 2000; ++s) boris_step(one, 0, cfg, ft);
        double v1 = std::sqrt(one.vx[0] * one.vx[0] + one.vy[0] * one.vy[0] +
                              one.vz[0] * one.vz[0]);
        CHECK(std::abs(v1 - v0) / v0 < 1e-9, "2000 步后 |v| 相对漂移 < 1e-9");
        CHECK(one.status[0] == 0, "粒子仍存活(磁镜捕获)");
    }

    std::printf("=== 3) 2 万粒子性能(300 帧 × 5 步) ===\n");
    {
        EmitterConfig ec;
        ec.mode = 0;
        ec.v_base = 400.0;
        ec.types = {{1.0, 0.1, 1.0, 1.0, 0xff3333},
                    {-1.0, 0.1, 1.0, 1.0, 0x3333ff},
                    {1.0, 1.0, 1.0, 1.0, 0xff8800}};
        ec.max_range = 15.0;

        Particles p;
        p.resize(20000);
        Emitter em(ec);
        for (size_t i = 0; i < p.count; ++i) em.spawn(p, i, (int32_t)i);

        IntegratorConfig cfg;
        cfg.dt = 0.01; cfg.max_range = 15.0;
        ForceTables ft{&b_table, nullptr, nullptr};

        auto t0 = std::chrono::steady_clock::now();
        for (int frame = 0; frame < 300; ++frame)
            for (int s = 0; s < 5; ++s) step_parallel(p, cfg, ft);
        auto t1 = std::chrono::steady_clock::now();
        double ms = std::chrono::duration<double, std::milli>(t1 - t0).count();
        double ms_per_step = ms / (300 * 5);
        std::printf("  300 帧×5 步 总耗时 %.1f ms,平均 %.3f ms/步\n", ms, ms_per_step);
        CHECK(ms_per_step < 5.0, "2 万粒子单步 < 5ms(旧引擎同量级预算)");

        size_t alive = 0, hit = 0, out = 0, bad = 0;
        for (size_t i = 0; i < p.count; ++i) {
            if (p.status[i] == 0) ++alive;
            else if (p.status[i] == 1) ++hit;
            else ++out;
            if (!std::isfinite(p.x[i]) || !std::isfinite(p.y[i]) ||
                !std::isfinite(p.z[i])) ++bad;
        }
        std::printf("  状态: 存活 %zu / 沉降 %zu / 出界 %zu / 非有限 %zu\n",
                    alive, hit, out, bad);
        CHECK(bad == 0, "全部位置有限");
        CHECK(alive + hit + out == p.count, "状态机覆盖全部粒子");
    }

    std::printf("=== 4) 编码协议(21 字节/粒子) ===\n");
    {
        Particles p;
        p.resize(3);
        for (size_t i = 0; i < 3; ++i) {
            p.id[i] = (int32_t)(100 + i);
            p.x[i] = 1.0 + i; p.y[i] = -2.0; p.z[i] = 3.0;
            p.vx[i] = 0.1; p.vy[i] = 0.2; p.vz[i] = 0.3;
            p.q[i] = 1; p.m[i] = 1; p.color[i] = 0x00ff00 + (int)i; p.status[i] = (uint8_t)i;
        }
        std::vector<uint8_t> buf;
        encode_particles(p, buf);
        CHECK(buf.size() == 3 * 21, "编码大小 = 21×N");
        int32_t id; float x, y, z; uint8_t st; uint32_t col;
        decode_particle(buf, 1, id, x, y, z, st, col);
        CHECK(id == 101 && x == 2.0f && z == 2.0f && st == 1, "解码往返一致(含坐标重映射)");
    }

    std::printf("=== 5) 推进内核注册表与经典核 ===\n");
    {
        CHECK(find_advancer("boris") != nullptr, "boris 内核已注册");
        CHECK(find_advancer("leapfrog") != nullptr, "leapfrog 内核已注册");
        CHECK(find_advancer("rk4") != nullptr, "rk4 内核已注册");
        CHECK(find_advancer("verlet") != nullptr, "verlet 内核已注册");
        CHECK(find_advancer("no_such") == nullptr, "未知内核返回 nullptr");
        CHECK(all_advancers().size() == 4, "内核注册表共 4 项");

        // Boris 内核与 legacy boris_step 位级一致(默认图验收基准)
        {
            Particles a, b;
            a.resize(1);
            b.resize(1);
            a.id[0] = b.id[0] = 0;
            a.x[0] = b.x[0] = 3.0; a.y[0] = b.y[0] = 0.0; a.z[0] = b.z[0] = 0.0;
            a.vx[0] = b.vx[0] = 0.0; a.vy[0] = b.vy[0] = 0.02; a.vz[0] = b.vz[0] = 0.01;
            a.q[0] = b.q[0] = 1.0; a.m[0] = b.m[0] = 1.0;
            a.status[0] = b.status[0] = 0;
            AdvanceInput in;
            in.b = &b_table;
            in.dt = 0.01;
            in.max_range = 90.0;
            IntegratorConfig cfg;
            cfg.dt = 0.01;
            cfg.max_range = 90.0;
            ForceTables ft{&b_table, nullptr, nullptr};
            for (int s = 0; s < 100; ++s) {
                find_advancer("boris")->step(a, in);
                boris_step(b, 0, cfg, ft);
            }
            CHECK(a.x[0] == b.x[0] && a.y[0] == b.y[0] && a.z[0] == b.z[0] &&
                      a.vx[0] == b.vx[0] && a.vy[0] == b.vy[0] && a.vz[0] == b.vz[0],
                  "Boris 内核与 legacy boris_step 位级一致");
        }

        // 经典核冒烟:纯偶极场 200 子步,全部有限。
        // leapfrog/verlet:磁部分 Boris 旋转精确保模 → |v| 漂移 ~0(容差 1%)
        // rk4:全经典 RK4 对纯回旋耗散(教科书特性)→ 容差 10%
        struct KernelCase { const char* name; double tol; };
        const std::vector<KernelCase> cases = {
            {"leapfrog", 0.01}, {"rk4", 0.10}, {"verlet", 0.01},
        };
        for (const auto& kc : cases) {
            const char* k = kc.name;
            Particles p;
            p.resize(1);
            p.id[0] = 0;
            p.x[0] = 3.0; p.y[0] = 0.0; p.z[0] = 0.0;
            p.vx[0] = 0.0; p.vy[0] = 0.02; p.vz[0] = 0.01;
            p.q[0] = 1.0; p.m[0] = 1.0; p.color[0] = 0xffffff; p.status[0] = 0;
            AdvanceInput in;
            in.b = &b_table;
            in.dt = 0.002;
            in.max_range = 90.0;
            const auto* adv = find_advancer(k);
            double v0 = std::sqrt(p.vx[0] * p.vx[0] + p.vy[0] * p.vy[0] +
                                  p.vz[0] * p.vz[0]);
            for (int s = 0; s < 200; ++s) adv->step(p, in);
            double v1 = std::sqrt(p.vx[0] * p.vx[0] + p.vy[0] * p.vy[0] +
                                  p.vz[0] * p.vz[0]);
            bool finite = std::isfinite(p.x[0]) && std::isfinite(p.y[0]) &&
                          std::isfinite(p.z[0]) && std::isfinite(p.vx[0]) &&
                          std::isfinite(p.vy[0]) && std::isfinite(p.vz[0]);
            bool drift_ok = std::abs(v1 - v0) / v0 < kc.tol;
            char msg[160];
            std::snprintf(msg, sizeof(msg),
                          "%s 内核 200 步:有限=%d 速度漂移 %.3f%% (容差 %.0f%%)",
                          k, (int)finite, (v1 - v0) / v0 * 100.0, kc.tol * 100.0);
            CHECK(finite && drift_ok, msg);
        }
    }

    std::printf("=== 6) 原生算子注册 ===\n");
    CHECK(native_builtins().size() == 6, "6 个内置原生算子已注册");

    std::printf(failures ? "\n[%d 项失败]\n" : "\n全部通过 ✅\n", failures);
    return failures ? 1 : 0;
}
