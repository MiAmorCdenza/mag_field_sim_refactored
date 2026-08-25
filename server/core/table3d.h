// 非均匀张量积网格的三线性查表(移植自 legacy physics_engine.cpp 的 MagneticGrid)。
// B/E 为矢量表(bx/by/bz 三通道),阻力等标量场复用 bx 通道(sample_scalar)。
#pragma once
#include <vector>
#include <cmath>

class Table3D {
public:
    std::vector<double> xs, ys, zs;
    std::vector<double> bx, by, bz;
    int nx = 0, ny = 0, nz = 0;

    void set_grid(const std::vector<double>& xs_, const std::vector<double>& ys_,
                  const std::vector<double>& zs_,
                  const std::vector<double>& bx_, const std::vector<double>& by_,
                  const std::vector<double>& bz_) {
        xs = xs_; ys = ys_; zs = zs_;
        nx = (int)xs.size(); ny = (int)ys.size(); nz = (int)zs.size();
        bx = bx_; by = by_; bz = bz_;
    }

    bool has_data() const {
        return nx > 0 && ny > 0 && nz > 0 &&
               bx.size() == (size_t)nx * ny * nz && by.size() == bx.size();
    }

    // 二分定位(热路径内联)
    static inline int find_idx(const double* a, int n, double v) {
        int lo = 0, hi = n - 1;
        while (lo < hi) {
            int mid = (lo + hi + 1) >> 1;
            if (a[mid] <= v) lo = mid;
            else             hi = mid - 1;
        }
        if (lo >= n - 1) lo = n - 2;
        return lo;
    }

    // 三线性插值(越界钳制)
    void sample(double x, double y, double z, double& ox, double& oy, double& oz) const {
        if (!has_data()) { ox = oy = oz = 0.0; return; }
        const double* px = xs.data();
        const double* py = ys.data();
        const double* pz = zs.data();
        if (x < px[0]) x = px[0];
        if (x > px[nx - 1]) x = px[nx - 1];
        if (y < py[0]) y = py[0];
        if (y > py[ny - 1]) y = py[ny - 1];
        if (z < pz[0]) z = pz[0];
        if (z > pz[nz - 1]) z = pz[nz - 1];

        int i = find_idx(px, nx, x);
        int j = find_idx(py, ny, y);
        int k = find_idx(pz, nz, z);

        double tx = (x - px[i]) / (px[i + 1] - px[i]);
        double ty = (y - py[j]) / (py[j + 1] - py[j]);
        double tz = (z - pz[k]) / (pz[k + 1] - pz[k]);
        double c00x = 1.0 - tx, c10x = tx;
        double c00y = 1.0 - ty, c10y = ty;
        double c00z = 1.0 - tz, c10z = tz;

        int nynz = ny * nz;
        int i0 = i * nynz + j * nz + k;
        int i1 = i0 + nynz;
        int j1 = nz;
        int k1 = 1;

        auto interp = [&](const std::vector<double>& c) {
            const double* p = c.data();
            double v000 = p[i0], v100 = p[i1];
            double v010 = p[i0 + j1], v110 = p[i1 + j1];
            double v001 = p[i0 + k1], v101 = p[i1 + k1];
            double v011 = p[i0 + j1 + k1], v111 = p[i1 + j1 + k1];
            double v00 = v000 * c00x + v100 * c10x;
            double v01 = v001 * c00x + v101 * c10x;
            double v10 = v010 * c00x + v110 * c10x;
            double v11 = v011 * c00x + v111 * c10x;
            double v0 = v00 * c00y + v10 * c10y;
            double v1 = v01 * c00y + v11 * c10y;
            return v0 * c00z + v1 * c10z;
        };
        ox = interp(bx);
        oy = interp(by);
        oz = interp(bz);
    }

    // 标量通道(阻力系数等)
    double sample_scalar(double x, double y, double z) const {
        double a, b, c;
        sample(x, y, z, a, b, c);
        return a;
    }
};
