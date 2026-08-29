// 粒子发射器:三种模式(定向盘面/全向球面/体积随机),移植自 legacy
// physics_engine.cpp 的 spawn_particle,数学与参数语义保持一致。
#pragma once
#include <cmath>
#include <random>
#include <utility>
#include <vector>
#include "vec3.h"
#include "particles.h"

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

struct EmitterConfig {
    int mode = 0;              // 0=定向盘面 1=全向球面 2=体积随机
    double lon_deg = 0.0;      // 发射方向经度(0/2 模式)
    double lat_deg = 0.0;      // 发射方向纬度(0/2 模式)
    double v_base = 400.0;     // km/s
    double v_random = 10.0;    // %
    double angle_random = 5.0; // %
    double dist_ratio = 1.0;   // 创生距离比例
    double spawn_radius_ratio = 0.5;
    double max_range = 90.0;
    std::vector<ParticleType> types;
};

class Emitter {
public:
    explicit Emitter(const EmitterConfig& cfg) : cfg_(cfg), gen_(std::random_device{}()) {}

    // 显式移动:MSVC 14.51 对含 mt19937(5000B 状态)类的隐式 move-assign
    // 生成过错误代码(启动即 0xC0000005,与 SimPipeline 隐式移动同款坑);
    // 显式逐成员移动绕开代码生成 bug。声明移动 → 拷贝被隐式删除。
    Emitter(Emitter&& o) noexcept
        : cfg_(std::move(o.cfg_)), gen_(o.gen_) {}
    Emitter& operator=(Emitter&& o) noexcept {
        if (this != &o) {
            cfg_ = std::move(o.cfg_);
            gen_ = o.gen_;
        }
        return *this;
    }

    // 粒子类型列表(物种声明节点聚合后应用)
    void set_types(const std::vector<ParticleType>& types) { cfg_.types = types; }

    void spawn(Particles& p, size_t idx, int32_t id) {
        double max_r = cfg_.max_range;
        Vec3 pos, base_dir;
        std::uniform_real_distribution<double> dist_u(0.0, 1.0);
        std::uniform_real_distribution<double> dist_z(-1.0, 1.0);
        std::uniform_real_distribution<double> dist_theta(0.0, 2.0 * M_PI);

        if (cfg_.mode == 1) {  // 全向球面
            double zz = dist_z(gen_);
            double theta = dist_theta(gen_);
            double r_xy = std::sqrt(1.0 - zz * zz);
            double r = max_r * cfg_.dist_ratio;
            pos = Vec3(r * r_xy * std::cos(theta), r * r_xy * std::sin(theta), r * zz);
            base_dir = pos * (-1.0 / std::max(r, 0.001));
        } else if (cfg_.mode == 2) {  // 体积随机
            double lon = cfg_.lon_deg * M_PI / 180.0;
            double lat = cfg_.lat_deg * M_PI / 180.0;
            Vec3 W(std::cos(lat) * std::cos(lon), std::cos(lat) * std::sin(lon), std::sin(lat));
            double u = dist_u(gen_);
            double r_random = max_r * cfg_.spawn_radius_ratio * std::cbrt(u);
            double zz = dist_z(gen_);
            double theta = dist_theta(gen_);
            double r_xy = std::sqrt(1.0 - zz * zz);
            Vec3 offset(r_random * r_xy * std::cos(theta), r_random * r_xy * std::sin(theta),
                        r_random * zz);
            pos = W * (max_r * cfg_.dist_ratio) + offset;
            base_dir = W * -1.0;
        } else {  // 定向盘面
            double lon = cfg_.lon_deg * M_PI / 180.0;
            double lat = cfg_.lat_deg * M_PI / 180.0;
            Vec3 W(std::cos(lat) * std::cos(lon), std::cos(lat) * std::sin(lon), std::sin(lat));
            Vec3 up(0, 0, 1);
            if (std::abs(W.z) > 0.99) up = Vec3(1, 0, 0);
            Vec3 U = W.cross(up);
            U = U / U.norm();
            Vec3 V = W.cross(U);
            V = V / V.norm();

            double r_disk_max = max_r * cfg_.spawn_radius_ratio;
            std::uniform_real_distribution<double> dist_r(0.0, 1.0);
            double r_d = r_disk_max * std::sqrt(dist_r(gen_));
            double angle_d = dist_theta(gen_);
            double disk_u = r_d * std::cos(angle_d);
            double disk_v = r_d * std::sin(angle_d);
            double dist_w = max_r * cfg_.dist_ratio;
            pos = W * dist_w + U * disk_u + V * disk_v;
            base_dir = W * -1.0;
        }

        // 速度(归一化单位:v_sw / 6371)
        double v_sw = cfg_.v_base / 6371.0;
        std::normal_distribution<double> dist_v_mag(1.0, cfg_.v_random / 100.0);
        double mag_factor = dist_v_mag(gen_);
        if (mag_factor < 0.01) mag_factor = 0.01;

        const ParticleType* pt = pick_type();
        double final_v = v_sw * pt->v_mult * mag_factor;
        const double c_speed = 299792.458 / 6371.0;
        if (final_v >= c_speed) final_v = c_speed * 0.999999;

        std::normal_distribution<double> dist_angle(0.0, cfg_.angle_random / 100.0);
        Vec3 dir = base_dir + Vec3(dist_angle(gen_), dist_angle(gen_), dist_angle(gen_));
        double fn = dir.norm();
        if (fn > 1e-6) dir = dir / fn;
        else           dir = base_dir;

        double rn = pos.norm();
        if (rn < 1.05) {
            if (rn > 1e-6) pos = pos / rn * 1.05;
            else           pos = Vec3(1.05, 0, 0);
        }

        p.id[idx] = id;
        p.x[idx] = pos.x; p.y[idx] = pos.y; p.z[idx] = pos.z;
        p.vx[idx] = dir.x * final_v;
        p.vy[idx] = dir.y * final_v;
        p.vz[idx] = dir.z * final_v;
        p.q[idx] = pt->q;
        p.m[idx] = pt->mass;
        p.color[idx] = pt->color;
        p.status[idx] = 0;
    }

private:
    const ParticleType* pick_type() {
        if (cfg_.types.empty()) return &fallback_;
        double total = 0.0;
        for (const auto& t : cfg_.types) total += t.weight;
        std::uniform_real_distribution<double> dist_w(0.0, total);
        double r = dist_w(gen_);
        double acc = 0.0;
        for (const auto& t : cfg_.types) {
            acc += t.weight;
            if (r <= acc) return &t;
        }
        return &cfg_.types.back();
    }

    EmitterConfig cfg_;
    std::mt19937 gen_;
    static inline const ParticleType fallback_{1.0, 0.1, 1.0, 1.0, 0xffffff};
};
