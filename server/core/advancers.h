// 批次推进内核 seam(L1):统一接口 + 内置内核注册表 + 共享力模型辅助。
//
// 设计(REFACTOR_PLAN §5.7,用户决策 L1):
// - IBatchAdvancer = 内核 seam:SimPipeline 按执行计划的 kernel 字段选核,
//   换步进器 = 图上换节点,不改任何后端管线结构
// - Boris 内核 = boris.h 的 legacy 内核原样封装(默认图位级一致基准)
// - 经典核的磁力部分必须用 Boris 旋转(v×B 是正交力,线性踢会每步
//   涨能 ~(hω)²/4,200 步可爆 60×;旋转无条件稳定且精确保模):
//   leapfrog/verlet = Boris 旋转 + 经典踢/漂移排布(E/引力/阻力)
//   rk4 = 全经典 RK4(对纯回旋耗散,粗步长下能量损失大 —— 诚实特性,
//   文档注明;适合用户要"教科书 RK4"的对照场景)
// - 力模型与 legacy Boris 同源同标度(q_prime = (q/m)*2988.5959)
// - 未来 L2 DLL SDK:本文件的 AdvanceInput POD 布局即 ABI 边界,
//   只需 extern "C" 工厂 + 同一虚表约定,封装约百行
#pragma once
#include <cmath>
#include <string>
#include <vector>

#include "vec3.h"
#include "particles.h"
#include "table3d.h"
#include "boris.h"

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

// 内核输入(POD,未来 DLL ABI 边界)
struct AdvanceInput {
    const Table3D* b = nullptr;      // 磁场表(归一化单位)
    const Table3D* e = nullptr;      // 电场表(可选)
    const Table3D* drag = nullptr;   // 大气阻力系数(可选,标量通道)
    double dt = 0.01;                // 单子步时长(模型精度对应)
    double max_range = 90.0;
    bool enable_gravity = false;
    double gravity_mult = 1.0;
    int substep_cap = 20;
};

// 批次推进内核接口(每子步调用一次)
class IBatchAdvancer {
public:
    virtual ~IBatchAdvancer() = default;
    virtual const char* kernel() const = 0;
    virtual void step(Particles& p, const AdvanceInput& in) const = 0;
};

// ---- 共享辅助(经典核共用) ----

// 预检:状态/有限性/光速钳制。返回 false = 该粒子跳过本步(已置 status)
inline bool adv_prepare(Particles& p, size_t i, Vec3& pos, Vec3& vel) {
    if (p.status[i] != 0) return false;
    pos = Vec3(p.x[i], p.y[i], p.z[i]);
    vel = Vec3(p.vx[i], p.vy[i], p.vz[i]);
    if (!(std::isfinite(pos.x) && std::isfinite(pos.y) && std::isfinite(pos.z) &&
          std::isfinite(vel.x) && std::isfinite(vel.y) && std::isfinite(vel.z))) {
        p.status[i] = 2;
        return false;
    }
    const double c = 299792.458 / 6371.0;
    double v2 = vel.norm2();
    if (v2 >= c * c) {
        v2 = c * c * 0.999999;
        vel = vel * (std::sqrt(v2) / vel.norm());
    }
    return true;
}

// 磁场采样(空表 → 零场)
inline Vec3 adv_sample_b(const Vec3& pos, const AdvanceInput& in) {
    Vec3 B(0, 0, 0);
    if (in.b) in.b->sample(pos.x, pos.y, pos.z, B.x, B.y, B.z);
    return B;
}

// 非磁加速度(E + 解析引力;磁旋转单独处理,见 adv_rotate)
inline Vec3 adv_ext_accel(const Vec3& pos, double q_prime, const AdvanceInput& in) {
    Vec3 E(0, 0, 0);
    if (in.e) in.e->sample(pos.x, pos.y, pos.z, E.x, E.y, E.z);
    Vec3 a = E * q_prime;
    if (in.enable_gravity) {
        double rn = pos.norm();
        if (rn > 0.1) {
            double GM = 1.5398e-6 * in.gravity_mult;
            a += pos * (-GM / (rn * rn * rn));
        }
    }
    return a;
}

// 全加速度(非磁 + v×B;RK4 用)
inline Vec3 adv_accel(const Vec3& pos, const Vec3& vel, double q_prime,
                      const AdvanceInput& in) {
    Vec3 B = adv_sample_b(pos, in);
    return adv_ext_accel(pos, q_prime, in) + vel.cross(B) * q_prime;
}

// Boris 式磁场旋转(非相对论近似):t = B·(qm·dt/2),s = 2t/(1+t²),
// v' = v + (v + v×t)×s。精确保模、任意旋转角无条件稳定。
inline Vec3 adv_rotate(const Vec3& v, const Vec3& B, double q_prime, double dt) {
    Vec3 t = B * (q_prime * dt * 0.5);
    double t2 = t.norm2();
    Vec3 s = t * (2.0 / (1.0 + t2));
    return v + (v + v.cross(t)).cross(s);
}

// 大气阻力阻尼因子(与 legacy 同阈值同形式)
inline double adv_drag_factor(const Vec3& pos, const AdvanceInput& in, double dt) {
    if (!in.drag) return 1.0;
    double rn = pos.norm();
    if (rn < 1.15 && rn > 0.0) {
        double nu = in.drag->sample_scalar(pos.x, pos.y, pos.z);
        double factor = 1.0 - nu * dt;
        return factor < 0.0 ? 0.0 : factor;
    }
    return 1.0;
}

// 写回 + 状态机(与 boris_step 的收尾语义一致)
inline void adv_finish(Particles& p, size_t i, const Vec3& pos, const Vec3& vel,
                       double max_range) {
    double rn = pos.norm();
    if (!std::isfinite(rn)) {
        p.status[i] = 2;
        p.x[i] = 2000.0; p.y[i] = 0.0; p.z[i] = 0.0;
        p.vx[i] = p.vy[i] = p.vz[i] = 0.0;
        return;
    }
    p.x[i] = pos.x; p.y[i] = pos.y; p.z[i] = pos.z;
    p.vx[i] = vel.x; p.vy[i] = vel.y; p.vz[i] = vel.z;
    if (rn < 1.0) p.status[i] = 1;
    else if (rn > max_range + 2.0) p.status[i] = 2;
}

// ---- 内置内核 ----

// Boris:legacy 相对论内核原样封装(位级一致基准)
class BorisAdvancer final : public IBatchAdvancer {
public:
    const char* kernel() const override { return "boris"; }
    void step(Particles& p, const AdvanceInput& in) const override {
        ForceTables ft{in.b, in.e, in.drag};
        IntegratorConfig cfg;
        cfg.dt = in.dt;
        cfg.max_range = in.max_range;
        cfg.enable_gravity = in.enable_gravity;
        cfg.gravity_mult = in.gravity_mult;
        cfg.substep_cap = in.substep_cap;
        step_parallel(p, cfg, ft);
    }
};

// 蛙跳(Boris 旋转 + 踢-漂-踢):
//   v_{1/2} = v + ½h·a_ext(x);v_{1/2} = rotate(v_{1/2}, B, h);
//   x' = x + v_{1/2}·h;v' = v_{1/2} + ½h·a_ext(x'),阻尼
class LeapfrogAdvancer final : public IBatchAdvancer {
public:
    const char* kernel() const override { return "leapfrog"; }
    void step(Particles& p, const AdvanceInput& in) const override {
        particles_parallel_for(p.count, [&](size_t, size_t start, size_t end) {
            for (size_t i = start; i < end; ++i) {
                Vec3 pos, vel;
                if (!adv_prepare(p, i, pos, vel)) continue;
                const double qp = (p.q[i] / p.m[i]) * 2988.5959;
                const double h = in.dt;
                Vec3 vh = vel + adv_ext_accel(pos, qp, in) * (h * 0.5);
                vh = adv_rotate(vh, adv_sample_b(pos, in), qp, h);
                Vec3 pos2 = pos + vh * h;
                vh = (vh + adv_ext_accel(pos2, qp, in) * (h * 0.5)) *
                     adv_drag_factor(pos2, in, in.dt);
                adv_finish(p, i, pos2, vh, in.max_range);
            }
        });
    }
};

// 经典 4 阶 Runge-Kutta(全加速度 a = (q/m)(E+v×B)+g;4 次场采样/子步)。
// 对纯回旋耗散 —— 教科书特性,粗步长需自行调小 dt(见文件头说明)。
class Rk4Advancer final : public IBatchAdvancer {
public:
    const char* kernel() const override { return "rk4"; }
    void step(Particles& p, const AdvanceInput& in) const override {
        particles_parallel_for(p.count, [&](size_t, size_t start, size_t end) {
            for (size_t i = start; i < end; ++i) {
                Vec3 pos, vel;
                if (!adv_prepare(p, i, pos, vel)) continue;
                const double qp = (p.q[i] / p.m[i]) * 2988.5959;
                const double h = in.dt;
                Vec3 k1v = adv_accel(pos, vel, qp, in);
                Vec3 k1x = vel;
                Vec3 k2v = adv_accel(pos + k1x * (h * 0.5), vel + k1v * (h * 0.5), qp, in);
                Vec3 k2x = vel + k1v * (h * 0.5);
                Vec3 k3v = adv_accel(pos + k2x * (h * 0.5), vel + k2v * (h * 0.5), qp, in);
                Vec3 k3x = vel + k2v * (h * 0.5);
                Vec3 k4v = adv_accel(pos + k3x * h, vel + k3v * h, qp, in);
                Vec3 k4x = vel + k3v * h;
                Vec3 pos2 = pos + (k1x + k2x * 2.0 + k3x * 2.0 + k4x) * (h / 6.0);
                Vec3 vel2 = (vel + (k1v + k2v * 2.0 + k3v * 2.0 + k4v) * (h / 6.0)) *
                            adv_drag_factor(pos2, in, in.dt);
                adv_finish(p, i, pos2, vel2, in.max_range);
            }
        });
    }
};

// 速度 Verlet(Boris 旋转 + 位置先行):
//   x' = x + v·h + ½h²·a_ext(x);v* = rotate(v, B, h);
//   v' = v* + ½h·(a_ext(x) + a_ext(x')),阻尼
class VerletAdvancer final : public IBatchAdvancer {
public:
    const char* kernel() const override { return "verlet"; }
    void step(Particles& p, const AdvanceInput& in) const override {
        particles_parallel_for(p.count, [&](size_t, size_t start, size_t end) {
            for (size_t i = start; i < end; ++i) {
                Vec3 pos, vel;
                if (!adv_prepare(p, i, pos, vel)) continue;
                const double qp = (p.q[i] / p.m[i]) * 2988.5959;
                const double h = in.dt;
                Vec3 a0 = adv_ext_accel(pos, qp, in);
                Vec3 pos2 = pos + vel * h + a0 * (0.5 * h * h);
                Vec3 vrot = adv_rotate(vel, adv_sample_b(pos, in), qp, h);
                Vec3 vel2 = (vrot + (a0 + adv_ext_accel(pos2, qp, in)) * (h * 0.5)) *
                            adv_drag_factor(pos2, in, in.dt);
                adv_finish(p, i, pos2, vel2, in.max_range);
            }
        });
    }
};

// ---- 内核注册表(进程内单例;DLL SDK 阶段替换为可扩展容器) ----

inline const BorisAdvancer& advancer_boris() { static const BorisAdvancer a; return a; }
inline const LeapfrogAdvancer& advancer_leapfrog() { static const LeapfrogAdvancer a; return a; }
inline const Rk4Advancer& advancer_rk4() { static const Rk4Advancer a; return a; }
inline const VerletAdvancer& advancer_verlet() { static const VerletAdvancer a; return a; }

inline const std::vector<const IBatchAdvancer*>& all_advancers() {
    static const std::vector<const IBatchAdvancer*> v = {
        &advancer_boris(), &advancer_leapfrog(), &advancer_rk4(), &advancer_verlet(),
    };
    return v;
}

inline const IBatchAdvancer* find_advancer(const std::string& kernel) {
    for (const auto* a : all_advancers())
        if (kernel == a->kernel()) return a;
    return nullptr;
}
