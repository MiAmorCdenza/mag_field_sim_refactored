// 粒子发射器:三种模式(定向盘面/全向球面/体积随机),移植自 legacy
// physics_engine.cpp 的 spawn_particle,数学与参数语义保持一致。
#pragma once
#include <cmath>
#include <random>
#include <utility>
#include <vector>
#include "vec3.h"
#include "particles.h"
#include "table3d.h"

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

// 单粒子注入(确定性初条件,零随机):位置/速度各两种表示。
// 由 particle_injection 节点声明 → 计划算子 → 发射器 mode 3。
struct InjectionConfig {
    bool enabled = false;
    // 位置:pos_mode 0 = (r, lat, lon)  1 = (x, y, z)   [Re / deg / Re,GSM]
    int pos_mode = 0;
    double r = 6.6, lat_deg = 0.0, lon_deg = 0.0;
    double x = 6.6, y = 0.0, z = 0.0;
    // 速度:vel_mode 0 = (v, pitch, phase) 相对局部 B;1 = (vx, vy, vz)
    int vel_mode = 0;
    double v_kms = 400.0, pitch_deg = 90.0, phase_deg = 0.0;
    double vx_kms = 0.0, vy_kms = 0.0, vz_kms = 400.0;
};

struct EmitterConfig {
    int mode = 0;              // 0=定向盘面 1=全向球面 2=体积随机 3=单粒子注入
    double lon_deg = 0.0;      // 发射方向经度(0/2 模式)
    double lat_deg = 0.0;      // 发射方向纬度(0/2 模式)
    double v_base = 400.0;     // km/s
    double v_random = 10.0;    // %
    double angle_random = 5.0; // %
    double dist_ratio = 1.0;   // 创生距离比例
    double spawn_radius_ratio = 0.5;
    double max_range = 90.0;
    int count = 0;             // 0 = 沿用全局粒子数;>0 = 图内覆盖
    std::vector<ParticleType> types;
    InjectionConfig injection;
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

    // 单粒子注入配置(particle_injection 节点接入后启用 mode 3)
    void set_injection(const InjectionConfig& inj) {
        cfg_.injection = inj;
        cfg_.injection.enabled = true;
        cfg_.mode = 3;
    }

    // 局部磁场表(俯仰角模式需要 B 方向构造正交基;空表 → z 轴退化)
    void set_field(const Table3D* b) { field_ = b; }

    void spawn(Particles& p, size_t idx, int32_t id) {
        double max_r = cfg_.max_range;
        Vec3 pos, base_dir;
        bool deterministic = false;   // 单粒子:跳过全部随机扰动
        double v_override = 0.0;      // 归一化速率(Re/s)
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
        } else if (cfg_.mode == 3 && cfg_.injection.enabled) {  // 单粒子注入
            const InjectionConfig& inj = cfg_.injection;
            if (inj.pos_mode == 1) {
                pos = Vec3(inj.x, inj.y, inj.z);
            } else {
                double lon = inj.lon_deg * M_PI / 180.0;
                double lat = inj.lat_deg * M_PI / 180.0;
                pos = Vec3(inj.r * std::cos(lat) * std::cos(lon),
                           inj.r * std::cos(lat) * std::sin(lon),
                           inj.r * std::sin(lat));
            }
            if (inj.vel_mode == 1) {          // (vx,vy,vz) 直接给定
                Vec3 vv(inj.vx_kms, inj.vy_kms, inj.vz_kms);
                double n = vv.norm();
                base_dir = (n > 1e-12) ? vv * (1.0 / n) : Vec3(0, 0, 1);
                v_override = ((n > 1e-12) ? n : 0.0) / 6371.0;
            } else {                          // (v, pitch, phase) 相对局部 B
                Vec3 B(0, 0, 0);
                if (field_) field_->sample(pos.x, pos.y, pos.z, B.x, B.y, B.z);
                double bm = B.norm();
                Vec3 bh = (bm > 1e-12) ? B * (1.0 / bm) : Vec3(0, 0, 1);
                Vec3 ref(0, 0, 1);
                if (std::abs(bh.dot(ref)) > 0.99) ref = Vec3(1, 0, 0);
                Vec3 e1 = bh.cross(ref);
                double n1 = e1.norm();
                e1 = (n1 > 1e-12) ? e1 * (1.0 / n1) : Vec3(1, 0, 0);
                Vec3 e2 = bh.cross(e1);
                double a = inj.pitch_deg * M_PI / 180.0;
                double ph = inj.phase_deg * M_PI / 180.0;
                base_dir = bh * std::cos(a) +
                           (e1 * std::cos(ph) + e2 * std::sin(ph)) * std::sin(a);
                v_override = inj.v_kms / 6371.0;
            }
            deterministic = true;
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

        // 速度(归一化单位:v_sw / 6371);单粒子走确定性分支(零随机)
        const ParticleType* pt;
        double final_v;
        Vec3 dir;
        if (deterministic) {
            // 物种取链首(确定性;不参与加权随机)
            pt = cfg_.types.empty() ? &fallback_ : &cfg_.types.front();
            final_v = v_override * pt->v_mult;
            dir = base_dir;
        } else {
            double v_sw = cfg_.v_base / 6371.0;
            std::normal_distribution<double> dist_v_mag(1.0, cfg_.v_random / 100.0);
            double mag_factor = dist_v_mag(gen_);
            if (mag_factor < 0.01) mag_factor = 0.01;
            pt = pick_type();
            final_v = v_sw * pt->v_mult * mag_factor;
            std::normal_distribution<double> dist_angle(0.0, cfg_.angle_random / 100.0);
            dir = base_dir + Vec3(dist_angle(gen_), dist_angle(gen_), dist_angle(gen_));
            double fn = dir.norm();
            if (fn > 1e-6) dir = dir / fn;
            else           dir = base_dir;
        }
        const double c_speed = 299792.458 / 6371.0;
        if (final_v >= c_speed) final_v = c_speed * 0.999999;

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
    const Table3D* field_ = nullptr;   // 俯仰角模式的正交基来源(可为空 → z 轴退化)
    static inline const ParticleType fallback_{1.0, 0.1, 1.0, 1.0, 0xffffff};
};
