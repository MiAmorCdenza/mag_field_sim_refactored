// 粒子状态编码:21 字节/粒子(与旧前端协议完全兼容)。
// [id:i32][x:f32][y:f32][z:f32][status:u8][color:u32]
// 坐标重映射(Three.js 约定):(x, y, z) → (x, z, -y)
#pragma once
#include <cstdint>
#include <cstring>
#include <vector>
#include "particles.h"

inline void encode_particles(const Particles& p, std::vector<uint8_t>& out) {
    out.resize(p.encoded_bytes());
    uint8_t* ptr = out.data();
    for (size_t i = 0; i < p.count; ++i) {
        int32_t id = p.id[i];
        float fx = std::isfinite(p.x[i]) ? (float)p.x[i] : 2000.0f;
        float fy = std::isfinite(p.z[i]) ? (float)p.z[i] : 0.0f;
        float fz = std::isfinite(p.y[i]) ? -(float)p.y[i] : 0.0f;
        uint8_t st = p.status[i];
        uint32_t col = (uint32_t)p.color[i];

        std::memcpy(ptr, &id, 4); ptr += 4;
        std::memcpy(ptr, &fx, 4); ptr += 4;
        std::memcpy(ptr, &fy, 4); ptr += 4;
        std::memcpy(ptr, &fz, 4); ptr += 4;
        *ptr++ = st;
        std::memcpy(ptr, &col, 4); ptr += 4;
    }
}

// 解码(测试/调试用)
inline void decode_particle(const std::vector<uint8_t>& buf, size_t idx,
                            int32_t& id, float& x, float& y, float& z,
                            uint8_t& st, uint32_t& col) {
    const uint8_t* p = buf.data() + idx * 21;
    std::memcpy(&id, p, 4);
    std::memcpy(&x, p + 4, 4);
    std::memcpy(&y, p + 8, 4);
    std::memcpy(&z, p + 12, 4);
    st = p[16];
    std::memcpy(&col, p + 17, 4);
}
