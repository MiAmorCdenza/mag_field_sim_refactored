// 磁场线追踪器:Tsyganenko TRACE_08 的 C++ 移植(采样器 = 烘焙表)。
//
// 算法(Geopack-2008 TRACE_08/STEP_08,官方双精度版):
// - Runge-Kutta-Merson 积分,嵌入截断误差 ERRCUR = Σ|R1−4.5R3+4R4−0.5R5|
// - 自适应步长:误差超限减半重试;误差 <4% 时步长 ×1.5(≤DSMAX)
// - 近地收窄(R<3 且向内):DS = FC·(R−R0+0.2),FC=0.2(极近 0.05)
// - 外边界三面判据:球 R=RLIM / 圆柱 ρ=CYL / 平面 X=XMAX
// - 内边界:由外向内穿越 R0 → 线性插值足点至精确 R=R0
// - 环检测:径向方向反转计数 >4 → 终止(取代旧防折返 hack)
// - 元数据:每条线带终止原因(可查证调试)
#pragma once
#include <cmath>
#include <vector>
#include "vec3.h"
#include "table3d.h"

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

struct TraceConfig {
    double dsmax = 0.2;        // 最大步长(输出点间距)
    double err = 1e-4;         // 允许步进误差(Merson,双精度下可更小)
    double rlim = 90.0;        // 外边界球
    double r0 = 1.0;           // 内边界(地球/电离层)
    double cyl_radius = 40.0;  // 外边界圆柱(绕 X 轴)
    double xmax = 20.0;        // 外边界平面
    int max_points = 2000;     // 单方向点数上限
    // 场表域(点阵范围,缺省全开):越出即终止 —— Table3D::sample 越界
    // 钳制得到的常数场会把迹线拉成长直伪线(纯偶极视图外侧"乱"的根因)
    double txmin = -1e30, txmax = 1e30, tymin = -1e30, tymax = 1e30,
           tzmin = -1e30, tzmax = 1e30;
};

enum class TermReason : uint8_t {
    HitEarth = 0,    // 足点插值到 R0
    LeftDomain = 1,  // 外边界三面之一
    Loops = 2,       // 径向反转 >4(闭合/绕圈)
    MaxPoints = 3,   // 点数上限
    Stagnant = 4,    // 场强近零
};

struct FieldLine {
    std::vector<Vec3> pts;
    TermReason reason = TermReason::MaxPoints;
    double length = 0.0;
};

// 单方向追踪(TRACE_08 移植):dir=+1 反平行于 B(北→南约定),dir=-1 平行
inline TermReason trace_one(const Table3D& table, const Vec3& start, double dir,
                            const TraceConfig& cfg, FieldLine& out) {
    out.pts.clear();
    out.reason = TermReason::MaxPoints;
    out.length = 0.0;

    // 采样器:B/|B| 单位方向(与粒子看到的场严格一致)
    auto rhand = [&](const Vec3& p) -> Vec3 {
        Vec3 b;
        table.sample(p.x, p.y, p.z, b.x, b.y, b.z);
        double bm = b.norm();
        if (bm < 1e-12) return Vec3(0, 0, 0);
        return b * (1.0 / bm);
    };

    double ds = 0.5 * dir;
    Vec3 x = start;
    Vec3 xr = start;  // 上一采样位置(足点插值用)

    // 径向分量符号 → 初始步进方向(仅用于初始化 RR,同 TRACE_08)
    Vec3 r0v = rhand(x);
    if (r0v.abs_sum() < 1e-12) {
        out.reason = TermReason::Stagnant;
        return out.reason;
    }
    double ad = 0.01;
    if (x.dot(r0v) < 0.0) ad = -0.01;
    double rr = x.norm() + ad;
    int nrev = 0;
    double prev_dr = 0.0;

    for (int l = 0; l < cfg.max_points; ++l) {
        out.pts.push_back(x);
        double r = x.norm();
        double ryz = x.y * x.y + x.z * x.z;

        // 外边界三面判据
        if (r > cfg.rlim || ryz > cfg.cyl_radius * cfg.cyl_radius ||
            x.x > cfg.xmax) {
            out.reason = TermReason::LeftDomain;
            break;
        }
        // 场表域判据:越过点阵边界 → 终止(钳制场伪线不得出现)
        if (x.x < cfg.txmin || x.x > cfg.txmax || x.y < cfg.tymin ||
            x.y > cfg.tymax || x.z < cfg.tzmin || x.z > cfg.tzmax) {
            out.reason = TermReason::LeftDomain;
            break;
        }
        // 内边界:由外向内穿越 → 足点线性插值到精确 R0
        if (r < cfg.r0 && rr > r) {
            double f = (cfg.r0 - r) / (rr - r);
            x = x - (x - xr) * f;
            out.pts.back() = x;
            out.reason = TermReason::HitEarth;
            break;
        }
        // 近地收窄(仅当向内运动且 R<3)
        if (r < rr && r < 3.0) {
            double fc = 0.2;
            if (r - cfg.r0 < 0.05) fc = 0.05;
            double al = fc * (r - cfg.r0 + 0.2);
            ds = dir * al;
        }
        xr = x;
        double drp = r - rr;
        rr = r;

        // ---- STEP_08:RK-Merson 自适应步(内部重试) ----
        Vec3 nx;
        bool stepped = false;
        double ds_try = ds;
        for (int attempt = 0; attempt < 50 && !stepped; ++attempt) {
            double s3 = -ds_try / 3.0;
            auto rh = [&](const Vec3& p) {
                return rhand(p) * s3;  // RHAND 约定:方向 × (-DS/3)
            };
            Vec3 R1 = rh(x);
            Vec3 R2 = rh(x + R1);
            Vec3 R3 = rh(x + (R1 + R2) * 0.5);
            Vec3 R4 = rh(x + (R1 + R3 * 3.0) * 0.375);
            Vec3 R5 = rh(x + (R1 - R3 * 3.0 + R4 * 4.0) * 1.5);
            double errcur = (R1 - R3 * 4.5 + R4 * 4.0 - R5 * 0.5).abs_sum();
            if (errcur > cfg.err) {           // 误差超限:减半重试
                ds_try *= 0.5;
                continue;
            }
            if (std::abs(ds_try) > cfg.dsmax) {  // 步长超上限:钳制重试
                ds_try = std::copysign(cfg.dsmax, ds_try);
                continue;
            }
            nx = x + (R1 + R4 * 4.0 + R5) * 0.5;
            // 误差过小 → 下一步步长 ×1.5
            if (errcur < cfg.err * 0.04 && ds_try < cfg.dsmax / 1.5)
                ds = ds_try * 1.5;
            else
                ds = ds_try;
            stepped = true;
        }
        if (!stepped) {
            out.reason = TermReason::Stagnant;
            break;
        }
        out.length += (nx - x).norm();
        x = nx;

        // 环检测:径向方向反转计数(>4 判定绕圈/闭合)
        double dr = x.norm() - rr;
        if (prev_dr * dr < 0.0) ++nrev;
        prev_dr = dr;
        if (nrev > 4) {
            out.reason = TermReason::Loops;
            break;
        }
    }
    if (out.reason == TermReason::MaxPoints && (int)out.pts.size() >= cfg.max_points)
        out.reason = TermReason::MaxPoints;
    return out.reason;
}

// 双向追踪并拼接(标准场线:种子点两侧)
inline void trace_line(const Table3D& table, const Vec3& seed,
                       const TraceConfig& cfg, FieldLine& out) {
    FieldLine fwd, bwd;
    trace_one(table, seed, -1.0, cfg, fwd);  // 平行于 B
    trace_one(table, seed, +1.0, cfg, bwd);  // 反平行于 B
    out.pts.clear();
    for (int i = (int)bwd.pts.size() - 1; i >= 1; --i) out.pts.push_back(bwd.pts[i]);
    for (const auto& p : fwd.pts) out.pts.push_back(p);
    out.length = fwd.length + bwd.length;
    // 终止原因:任一方向先触发(足点 > 出界 > 环)
    out.reason = (bwd.reason == TermReason::HitEarth || fwd.reason == TermReason::HitEarth)
                     ? TermReason::HitEarth
                 : (bwd.reason == TermReason::Loops || fwd.reason == TermReason::Loops)
                     ? TermReason::Loops
                     : TermReason::LeftDomain;
}

// 种子策略:三类拓扑(闭合 / 开放 / 太阳风),全参数化
struct SeedSet {
    std::vector<Vec3> closed;
    std::vector<Vec3> open;
    std::vector<Vec3> solarwind;
};

struct SeedConfig {
    // 闭合:磁赤道面 L 壳环
    std::vector<double> l_shells = {2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0};
    int angles_per_shell = 8;
    // 开放:极盖磁纬(度)网格,球面 r=1.02
    std::vector<double> polar_lats = {60.0, 65.0, 70.0, 75.0, 80.0, 85.0};
    int polar_lons = 8;
    // 太阳风:上游平面 X=xplane,YZ 网格
    double sw_x = 18.0;
    double sw_half = 25.0;
    double sw_step = 5.0;
    // 域自适应(缺省全开):生成时过滤,保证种子都在场表域内。
    // 域外种子(如 x=18 的太阳风平面 vs ±10 的 tiny 点阵)整条迹线
    // 都从钳制场开始 → 纯伪线(绿色大扇子的来源)
    double dom_xmin = -1e30, dom_xmax = 1e30,
           dom_ymin = -1e30, dom_ymax = 1e30,
           dom_zmin = -1e30, dom_zmax = 1e30;
    double dom_margin = 0.5;  // 距域边界的种子保留余量(Re)
};

inline SeedSet build_seeds(const SeedConfig& cfg) {
    SeedSet s;
    auto in_dom = [&](const Vec3& p) {
        return p.x >= cfg.dom_xmin + cfg.dom_margin &&
               p.x <= cfg.dom_xmax - cfg.dom_margin &&
               p.y >= cfg.dom_ymin + cfg.dom_margin &&
               p.y <= cfg.dom_ymax - cfg.dom_margin &&
               p.z >= cfg.dom_zmin + cfg.dom_margin &&
               p.z <= cfg.dom_zmax - cfg.dom_margin;
    };
    // 闭合:磁赤道面(z=0)L 环
    for (double L : cfg.l_shells) {
        for (int i = 0; i < cfg.angles_per_shell; ++i) {
            double th = 2.0 * M_PI * i / cfg.angles_per_shell;
            Vec3 p(L * std::cos(th), L * std::sin(th), 0.0);
            if (in_dom(p)) s.closed.push_back(p);
        }
    }
    // 开放:极盖球面网格(南北半球)
    for (double lat : cfg.polar_lats) {
        double th = (90.0 - lat) * M_PI / 180.0;  // 余纬
        for (int i = 0; i < cfg.polar_lons; ++i) {
            double phi = 2.0 * M_PI * i / cfg.polar_lons;
            double rxy = 1.02 * std::sin(th);
            double z = 1.02 * std::cos(th);
            Vec3 a(rxy * std::cos(phi), rxy * std::sin(phi), z);
            Vec3 b(rxy * std::cos(phi), rxy * std::sin(phi), -z);
            if (in_dom(a)) s.open.push_back(a);
            if (in_dom(b)) s.open.push_back(b);
        }
    }
    // 太阳风:上游 YZ 平面
    for (double y = -cfg.sw_half; y <= cfg.sw_half + 1e-9; y += cfg.sw_step) {
        for (double z = -cfg.sw_half; z <= cfg.sw_half + 1e-9; z += cfg.sw_step) {
            Vec3 p(cfg.sw_x, y, z);
            if (in_dom(p)) s.solarwind.push_back(p);
        }
    }
    return s;
}
