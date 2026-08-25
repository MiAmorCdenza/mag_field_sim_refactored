// 粒子缓冲(SoA,缓存友好)+ 粒子类型。
#pragma once
#include <cstdint>
#include <vector>

struct ParticleType {
    double q = 1.0;        // 电荷(归一化单位)
    double mass = 1.0;     // 质量(归一化单位)
    double v_mult = 1.0;   // 速度倍率
    double weight = 1.0;   // 生成权重
    int32_t color = 0xffffff;
};

struct Particles {
    std::vector<int32_t> id;
    std::vector<double> x, y, z;    // 位置(Re,GSM 类坐标)
    std::vector<double> vx, vy, vz; // 速度(归一化单位)
    std::vector<double> q, m;
    std::vector<int32_t> color;
    std::vector<uint8_t> status;    // 0=存活 1=沉降 2=出界/异常
    size_t count = 0;

    void resize(size_t n) {
        id.resize(n); x.resize(n); y.resize(n); z.resize(n);
        vx.resize(n); vy.resize(n); vz.resize(n);
        q.resize(n); m.resize(n); color.resize(n); status.resize(n);
        count = n;
    }

    // 每粒子编码字节数 = 4(id)+12(xyz f32)+1(status)+4(color)
    size_t encoded_bytes() const { return count * 21; }
};
