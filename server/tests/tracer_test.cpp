// TRACE_08 移植验收:纯偶极场解析解逐点对照。
//
// 偶极场线解析性质(轴沿 Z,磁矩 m=(0,0,-1)):
//   1) r = L·sin²θ(θ 为余纬,L = 赤道穿越距离)
//   2) 场线保持在种子方位角的子午面内:φ = atan2(y,x) 守恒
//   3) 两端足点精确落在 r = R0
// 编译: cl /EHsc /O2 /std:c++17 /utf-8 /I ..\core tracer_test.cpp
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <vector>

#include "../core/vec3.h"
#include "../core/table3d.h"
#include "../core/tracer.h"

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
    out.erase(std::unique(out.begin(), out.end(),
                          [](double a, double b) { return std::abs(a - b) < 1e-12; }),
              out.end());
    return out;
}

// 无倾角偶极表:m=(0,0,-1) 归一化单位
static void fill_dipole(Table3D& t) {
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
                double md = -z;  // m·r
                t.bx[idx] = 3.0 * md * x / r5;
                t.by[idx] = 3.0 * md * y / r5;
                t.bz[idx] = 3.0 * md * z / r5 + 1.0 / r3;
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
    Table3D table;
    table.set_grid(stretched(-15.0, 10.0, 70), stretched(-12.0, 12.0, 64),
                   stretched(-12.0, 12.0, 64),
                   std::vector<double>(70 * 64 * 64), {}, {});
    fill_dipole(table);

    TraceConfig cfg;
    cfg.dsmax = 0.2;
    cfg.err = 1e-4;
    cfg.rlim = 15.0;

    std::printf("=== 1) 单条场线:L=3,种子 (3,0,0) ===\n");
    {
        FieldLine line;
        trace_line(table, Vec3(3.0, 0.0, 0.0), cfg, line);
        CHECK(line.reason == TermReason::HitEarth, "两端终止于地球(足点插值)");
        CHECK(line.pts.size() > 20 && line.pts.size() < 1000, "点数合理");
        // 足点为线性插值估计(沿弦近似,误差 ~ 曲率·ds²,Fortran 原版同此)
        CHECK(std::abs(line.pts.front().norm() - 1.0) < 1e-3, "起点端足点 r≈1.0");
        CHECK(std::abs(line.pts.back().norm() - 1.0) < 1e-3, "终点端足点 r≈1.0");

        double max_dr = 0.0, max_dphi = 0.0;
        for (const auto& p : line.pts) {
            double r = p.norm();
            if (r < 0.01) continue;
            double th = std::acos(p.z / r);          // 余纬
            double r_theory = 3.0 * std::sin(th) * std::sin(th);
            max_dr = std::max(max_dr, std::abs(r - r_theory));
            double phi = std::atan2(p.y, p.x);
            max_dphi = std::max(max_dphi, std::abs(phi));
        }
        CHECK(max_dr < 0.05, "r = L·sin²θ 解析关系(max|Δr| < 0.05)");
        CHECK(max_dphi < 0.02, "子午面守恒(φ≈0)");
        std::printf("     max|Δr|=%.4f  max|Δφ|=%.4f  点数=%zu\n",
                    max_dr, max_dphi, line.pts.size());
    }

    std::printf("=== 2) 方位角守恒:种子 (0,4,0) → φ≈90° ===\n");
    {
        FieldLine line;
        trace_line(table, Vec3(0.0, 4.0, 0.0), cfg, line);
        CHECK(line.reason == TermReason::HitEarth, "终止于地球");
        double max_err = 0.0;
        for (const auto& p : line.pts) {
            double phi = std::atan2(p.y, p.x);
            double err = std::abs(std::abs(phi) - M_PI / 2.0);
            max_err = std::max(max_err, err);
        }
        CHECK(max_err < 0.02, "子午面守恒(φ≈90°)");
        std::printf("     max|Δφ|=%.4f\n", max_err);
    }

    std::printf("=== 3) 全种子集性能 ===\n");
    {
        SeedConfig sc;
        SeedSet seeds = build_seeds(sc);
        size_t total = seeds.closed.size() + seeds.open.size() + seeds.solarwind.size();
        std::printf("     种子: 闭合 %zu + 开放 %zu + 太阳风 %zu = %zu\n",
                    seeds.closed.size(), seeds.open.size(),
                    seeds.solarwind.size(), total);
        auto t0 = std::chrono::steady_clock::now();
        size_t traced = 0, hit_earth = 0, left = 0, loops = 0, other = 0;
        auto run = [&](const std::vector<Vec3>& v) {
            for (const auto& s : v) {
                FieldLine line;
                trace_line(table, s, cfg, line);
                ++traced;
                if (line.reason == TermReason::HitEarth) ++hit_earth;
                else if (line.reason == TermReason::LeftDomain) ++left;
                else if (line.reason == TermReason::Loops) ++loops;
                else ++other;
            }
        };
        run(seeds.closed);
        run(seeds.open);
        run(seeds.solarwind);
        auto t1 = std::chrono::steady_clock::now();
        double ms = std::chrono::duration<double, std::milli>(t1 - t0).count();
        std::printf("     结果: 闭合线 %zu(其中足点 %zu / 出界 %zu / 环 %zu / 其他 %zu)\n",
                    traced, hit_earth, left, loops, other);
        std::printf("     耗时: %.1f ms\n", ms);
        CHECK(traced == total, "全部种子完成追踪");
        CHECK(hit_earth > 0 && left > 0, "闭合线有足点、太阳风线有出界");
        CHECK(ms < 2000.0, "全种子集 < 2 秒(预算内)");
    }

    std::printf(failures ? "\n[%d 项失败]\n" : "\n追踪器验收全部通过 ✅\n", failures);
    return failures ? 1 : 0;
}
