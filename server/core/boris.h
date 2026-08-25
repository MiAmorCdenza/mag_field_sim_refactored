// 相对论 Boris 积分器:纯查表热路径(移植自 legacy physics_engine.cpp)。
//
// 新架构约定(REFACTOR_PLAN):
// - B / E / 阻力系数全部来自烘焙表(Table3D),每子步查表
// - 引力保留解析(-GM r̂/r²),也可由重力表替代
// - 本文件无任何 Python 依赖,全原生计划 = 每帧零 Python
#pragma once
#include <cmath>
#include <thread>
#include <vector>
#include "vec3.h"
#include "particles.h"
#include "table3d.h"

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

struct ForceTables {
    const Table3D* b = nullptr;     // 磁场(必需)
    const Table3D* e = nullptr;     // 电场(可选)
    const Table3D* drag = nullptr;  // 大气阻力系数(可选,标量通道)
};

struct IntegratorConfig {
    double dt = 0.01;               // 模型精度对应(legacy: 0.02/0.01/0.002/0.0005)
    double max_range = 90.0;
    bool enable_gravity = false;
    double gravity_mult = 1.0;
    int substep_cap = 20;
};

// 单粒子单步(每帧 steps_per_frame 次调用)
inline void boris_step(Particles& p, size_t i, const IntegratorConfig& cfg,
                       const ForceTables& tables) {
    if (p.status[i] != 0) return;  // 沉降/出界粒子静默(重生成由计划层决定)

    const double q_prime = (p.q[i] / p.m[i]) * 2988.5959;
    const double c = 299792.458 / 6371.0;

    Vec3 pos(p.x[i], p.y[i], p.z[i]);
    Vec3 vel(p.vx[i], p.vy[i], p.vz[i]);

    if (!(std::isfinite(pos.x) && std::isfinite(pos.y) && std::isfinite(pos.z) &&
          std::isfinite(vel.x) && std::isfinite(vel.y) && std::isfinite(vel.z))) {
        p.status[i] = 2;
        return;
    }

    double v2 = vel.norm2();
    if (v2 >= c * c) {
        v2 = c * c * 0.999999;
        vel = vel * (std::sqrt(v2) / vel.norm());
    }
    double gamma = 1.0 / std::sqrt(1.0 - v2 / (c * c));
    Vec3 u = vel * gamma;

    // 亚步长:回旋频率自适应(与 legacy 完全一致)
    Vec3 B;
    tables.b->sample(pos.x, pos.y, pos.z, B.x, B.y, B.z);
    double B_mag = B.norm();
    double wc = std::abs(q_prime * B_mag) / gamma;
    int n_sub = 1;
    if (wc * cfg.dt > 0.5) n_sub = (int)std::ceil(wc * cfg.dt / 0.5);
    if (n_sub > cfg.substep_cap) n_sub = cfg.substep_cap;

    double sub_dt = cfg.dt / n_sub;
    double sub_dt2 = sub_dt / 2.0;
    double GM = 1.5398e-6 * cfg.gravity_mult;

    for (int s = 0; s < n_sub; ++s) {
        if (s > 0) tables.b->sample(pos.x, pos.y, pos.z, B.x, B.y, B.z);

        Vec3 g(0, 0, 0);
        if (cfg.enable_gravity) {
            double rn = pos.norm();
            if (rn > 0.1) g = pos * (-GM / (rn * rn * rn));
        }

        Vec3 E(0, 0, 0);
        if (tables.e) tables.e->sample(pos.x, pos.y, pos.z, E.x, E.y, E.z);

        Vec3 impulse = (E * q_prime + g) * sub_dt2;
        Vec3 u_minus = u + impulse;
        double g_minus = std::sqrt(1.0 + u_minus.norm2() / (c * c));

        Vec3 t = B * (q_prime * sub_dt2 / g_minus);
        double t2 = t.norm2();
        Vec3 svec = t * (2.0 / (1.0 + t2));
        Vec3 u_prime = u_minus + u_minus.cross(t);
        u = u_minus + u_prime.cross(svec) + impulse;

        if (tables.drag) {
            double rn = pos.norm();
            if (rn < 1.15 && rn > 0.0) {
                double nu = tables.drag->sample_scalar(pos.x, pos.y, pos.z);
                double factor = 1.0 - nu * sub_dt;
                if (factor < 0.0) factor = 0.0;
                u = u * factor;
            }
        }

        gamma = std::sqrt(1.0 + u.norm2() / (c * c));
        vel = u / gamma;
        pos += vel * sub_dt;
    }

    double rn = pos.norm();
    if (!std::isfinite(rn)) {
        p.status[i] = 2;
        p.x[i] = 2000.0; p.y[i] = 0.0; p.z[i] = 0.0;
        p.vx[i] = p.vy[i] = p.vz[i] = 0.0;
    } else if (rn < 1.0) {
        p.status[i] = 1;
    } else if (rn > cfg.max_range + 2.0) {
        p.status[i] = 2;
    }

    p.x[i] = pos.x; p.y[i] = pos.y; p.z[i] = pos.z;
    p.vx[i] = vel.x; p.vy[i] = vel.y; p.vz[i] = vel.z;
}

// 多线程并行步进(与 legacy step() 同款分块策略)
inline void step_parallel(Particles& p, const IntegratorConfig& cfg,
                          const ForceTables& tables) {
    int n = (int)p.count;
    if (n == 0) return;
    int n_threads = (int)std::thread::hardware_concurrency();
    if (n_threads == 0) n_threads = 4;
    if (n_threads > n) n_threads = n;

    std::vector<std::thread> threads;
    int chunk = (n + n_threads - 1) / n_threads;
    for (int t = 0; t < n_threads; ++t) {
        int start = t * chunk;
        int end = std::min(start + chunk, n);
        if (start >= end) break;
        threads.emplace_back([&, start, end]() {
            for (int i = start; i < end; ++i) boris_step(p, (size_t)i, cfg, tables);
        });
    }
    for (auto& th : threads) th.join();
}
