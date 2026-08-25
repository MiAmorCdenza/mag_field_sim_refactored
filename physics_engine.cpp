#include <nlohmann/json.hpp>

#include <vector>
#include <cmath>
#include <random>
#include <thread>
#include <algorithm>
#include <iostream>
#include <cstdint>
#include <cstring>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif



struct Vec3 {
    double x, y, z;
    Vec3() : x(0), y(0), z(0) {}
    Vec3(double x, double y, double z) : x(x), y(y), z(z) {}
    Vec3 operator+(const Vec3& o) const { return Vec3(x+o.x, y+o.y, z+o.z); }
    Vec3 operator-(const Vec3& o) const { return Vec3(x-o.x, y-o.y, z-o.z); }
    Vec3 operator*(double s) const { return Vec3(x*s, y*s, z*s); }
    Vec3 operator/(double s) const { return Vec3(x/s, y/s, z/s); }
    Vec3& operator+=(const Vec3& o) { x+=o.x; y+=o.y; z+=o.z; return *this; }
    double dot(const Vec3& o) const { return x*o.x + y*o.y + z*o.z; }
    Vec3 cross(const Vec3& o) const { return Vec3(y*o.z - z*o.y, z*o.x - x*o.z, x*o.y - y*o.x); }
    double norm() const { return std::sqrt(x*x + y*y + z*z); }
};

class MagneticGrid {
public:
    std::vector<double> x_coords, y_coords, z_coords;
    int nx, ny, nz, nynz;
    std::vector<double> Bx_grid, By_grid, Bz_grid;
    // Raw pointers for fast hot-path access (set after set_grid)
    const double* __restrict px;
    const double* __restrict py;
    const double* __restrict pz;
    const double* __restrict pBx;
    const double* __restrict pBy;
    const double* __restrict pBz;

    MagneticGrid() : nx(0), ny(0), nz(0), nynz(0), px(nullptr), py(nullptr), pz(nullptr),
                     pBx(nullptr), pBy(nullptr), pBz(nullptr) {}

    bool is_valid() const {
        return nx > 0 && ny > 0 && nz > 0 && Bx_grid.size() == (size_t)(nx * ny * nz);
    }

    void set_grid(const std::vector<double>& xs, const std::vector<double>& ys, const std::vector<double>& zs,
                  const std::vector<double>& bx,
                  const std::vector<double>& by,
                  const std::vector<double>& bz) {
        x_coords = xs; nx = (int)xs.size();
        y_coords = ys; ny = (int)ys.size();
        z_coords = zs; nz = (int)zs.size();
        nynz = ny * nz;
        Bx_grid = bx; By_grid = by; Bz_grid = bz;
        px = x_coords.data(); py = y_coords.data(); pz = z_coords.data();
        pBx = Bx_grid.data(); pBy = By_grid.data(); pBz = Bz_grid.data();
    }

    inline int find_idx(const double* __restrict arr, int n, double val) const {
        // Inline binary search — faster than std::upper_bound in hot path
        int lo = 0, hi = n - 1;
        while (lo < hi) {
            int mid = (lo + hi + 1) >> 1;
            if (arr[mid] <= val) lo = mid;
            else                 hi = mid - 1;
        }
        if (lo >= n - 1) lo = n - 2;
        return lo;
    }

    Vec3 interpolate(double x, double y, double z) const {
        if (!px) return Vec3(0,0,0);

        // Clamp to bounds
        if (x < px[0])   x = px[0];
        if (x > px[nx-1]) x = px[nx-1];
        if (y < py[0])   y = py[0];
        if (y > py[ny-1]) y = py[ny-1];
        if (z < pz[0])   z = pz[0];
        if (z > pz[nz-1]) z = pz[nz-1];

        int i = find_idx(px, nx, x);
        int j = find_idx(py, ny, y);
        int k = find_idx(pz, nz, z);

        double tx = (x - px[i]) / (px[i+1] - px[i]);
        double ty = (y - py[j]) / (py[j+1] - py[j]);
        double tz = (z - pz[k]) / (pz[k+1] - pz[k]);
        double c00x = 1.0 - tx, c10x = tx;
        double c00y = 1.0 - ty, c10y = ty;
        double c00z = 1.0 - tz, c10z = tz;

        // Precompute base index for the 8 cell corners
        int i0 = i * nynz + j * nz + k;
        int i1 = i0 + nynz;  // i+1
        int j1 = nz;         // j+1 offset in flat index
        int k1 = 1;          // k+1 offset

        auto interp_comp = [&](const double* __restrict p) {
            double v000 = p[i0];
            double v100 = p[i1];
            double v010 = p[i0 + j1];
            double v110 = p[i1 + j1];
            double v001 = p[i0 + k1];
            double v101 = p[i1 + k1];
            double v011 = p[i0 + j1 + k1];
            double v111 = p[i1 + j1 + k1];

            double v00 = v000 * c00x + v100 * c10x;
            double v01 = v001 * c00x + v101 * c10x;
            double v10 = v010 * c00x + v110 * c10x;
            double v11 = v011 * c00x + v111 * c10x;

            double v0 = v00 * c00y + v10 * c10y;
            double v1 = v01 * c00y + v11 * c10y;

            return v0 * c00z + v1 * c10z;
        };

        return Vec3(interp_comp(pBx), interp_comp(pBy), interp_comp(pBz));
    }

    // Backward-compatible uniform grid setter
    void set_grid_uniform(double xmin, double xmax, int nx_,
                          double ymin, double ymax, int ny_,
                          double zmin, double zmax, int nz_,
                          const std::vector<double>& bx,
                          const std::vector<double>& by,
                          const std::vector<double>& bz) {
        x_coords.clear(); y_coords.clear(); z_coords.clear();
        nx = nx_; ny = ny_; nz = nz_; nynz = ny * nz;
        double dx = (nx > 1) ? (xmax - xmin) / (nx - 1) : 1.0;
        double dy = (ny > 1) ? (ymax - ymin) / (ny - 1) : 1.0;
        double dz = (nz > 1) ? (zmax - zmin) / (nz - 1) : 1.0;
        for (int i = 0; i < nx; ++i) x_coords.push_back(xmin + i * dx);
        for (int i = 0; i < ny; ++i) y_coords.push_back(ymin + i * dy);
        for (int i = 0; i < nz; ++i) z_coords.push_back(zmin + i * dz);
        Bx_grid = bx; By_grid = by; Bz_grid = bz;
        px = x_coords.data(); py = y_coords.data(); pz = z_coords.data();
        pBx = Bx_grid.data(); pBy = By_grid.data(); pBz = Bz_grid.data();
    }
};

class MagneticField {
public:
    double total_tilt;
    double seasonal_tilt;
    double day_of_year;
    Vec3 m;
    double solar_wind_compression;
    double max_range;
    double dipole_moment;
    double b_multiplier;

    MagneticGrid ext_grid;

    MagneticField(double dipole_moment = 1.0) : dipole_moment(dipole_moment) {
        day_of_year = 172.0; 
        solar_wind_compression = 1.0;
        max_range = 90.0;
        b_multiplier = 1.0;
        update_tilt();
    }

    void update_tilt() {
        double tilt_rot_max = 23.44 * M_PI / 180.0;
        double tilt_mag_offset = 11.0 * M_PI / 180.0;
        seasonal_tilt = tilt_rot_max * std::cos(2.0 * M_PI * (day_of_year - 172.0) / 365.25);
        total_tilt = seasonal_tilt + tilt_mag_offset;
        m = Vec3(-std::sin(total_tilt), 0.0, -std::cos(total_tilt)) * dipole_moment;
    }

    Vec3 get_field(const Vec3& r_vec) const {
        double r = r_vec.norm();
        if (r < 0.1) return Vec3(0, 0, 0);

        if (ext_grid.is_valid()) {
            // Grid is in nT; convert to dipole units (1.0 ≈ 31200 nT at surface)
            // so that q_prime = (q/m)*2988.5959 yields the correct gyrofrequency.
            double scale_factor = dipole_moment / 31200.0;
            return ext_grid.interpolate(r_vec.x, r_vec.y, r_vec.z) * scale_factor * b_multiplier;
        }

        // Fallback: pure dipole + image dipole + simplified tail sheet
        Vec3 r_hat = r_vec / r;
        Vec3 B_earth = (r_hat * (3.0 * m.dot(r_hat)) - m) * (1.0 / (r * r * r));

        double R_mp = 10.0 / std::pow(solar_wind_compression, 1.0/3.0);
        double D = 2.0 * R_mp;
        Vec3 r_image(D, 0.0, 0.0);
        Vec3 r_img_vec = r_vec - r_image;
        double r_img = r_img_vec.norm();

        Vec3 B_image(0, 0, 0);
        if (r_img > 0.1) {
            Vec3 r_img_hat = r_img_vec / r_img;
            double comp_cbrt = std::pow(solar_wind_compression, 1.0/3.0);
            Vec3 m_image = Vec3(-m.x, m.y, m.z) * comp_cbrt;
            B_image = (r_img_hat * (3.0 * m_image.dot(r_img_hat)) - m_image) * (1.0 / (r_img * r_img * r_img));
        }

        Vec3 B_tail(0, 0, 0);
        if (r_vec.x < 0) {
            double z = r_vec.z;
            double tail_strength = 0.8 * solar_wind_compression; 
            double z_decay = std::exp(-z * z / 6.0);              
            double Bx = -tail_strength * z_decay;                 
            B_tail = Vec3(Bx, 0.0, 0.0);
        }

        return (B_earth + B_image + B_tail) * b_multiplier;
    }
};

struct ParticleType {
    double q;
    double mass;
    int color;
    double v_multiplier;
    double weight;
};

struct Particle {
    int id;
    double q;
    double mass;
    Vec3 pos;
    Vec3 vel;
    int status; 
    int color;
};

class SimulationEngine {
public:
    MagneticField b_field;
    std::vector<Particle> particles;
    double dt;
    bool needs_field_update;
    int next_id;
    int model_precision;
    int field_precision;
    double spawn_radius_ratio;
    std::vector<ParticleType> active_particle_types;
    double emitter_v_base;
    int emitter_mode;
    double emitter_lon;
    double emitter_lat;
    double emitter_v_random;
    double emitter_angle_random;
    double emitter_distance_ratio;
    bool enable_gravity;
    double gravity_multiplier;
    bool enable_electric_field;
    double electric_field_multiplier;
    bool enable_atmosphere;
    double atmosphere_multiplier;
    int atmos_model;
    int efield_model;

    SimulationEngine() : dt(0.01), needs_field_update(true), next_id(0), model_precision(1), field_precision(1), spawn_radius_ratio(0.5), enable_gravity(false), gravity_multiplier(1.0), enable_electric_field(false), electric_field_multiplier(1.0), enable_atmosphere(false), atmosphere_multiplier(1.0), atmos_model(0), efield_model(0) {
        emitter_v_base = 400.0;
        emitter_mode = 0;
        emitter_lon = 0.0;
        emitter_lat = 0.0;
        emitter_v_random = 10.0;
        emitter_angle_random = 5.0;
        emitter_distance_ratio = 1.0;
        
        active_particle_types.push_back({1.0, 0.1, 0xff3333, 1.0, 1.0});
        active_particle_types.push_back({-1.0, 0.1, 0x3333ff, 1.0, 1.0});
        
        set_particle_count(100);
    }

    void set_particle_count(int count) {
        int current = (int)particles.size();
        if (count > current) {
            particles.reserve(count);
            for (int i = current; i < count; ++i) {
                particles.push_back(spawn_particle(next_id++));
            }
        } else if (count < current) {
            particles.resize(count);
        }
    }

    Particle spawn_particle(int id, Particle* p = nullptr) {
        double max_r = b_field.max_range;
        static thread_local std::mt19937 gen(std::random_device{}());
        Vec3 pos, base_dir;

        if (emitter_mode == 1) {
            std::uniform_real_distribution<double> dist_z(-1.0, 1.0);
            double z = dist_z(gen);
            std::uniform_real_distribution<double> dist_theta(0.0, 2.0 * M_PI);
            double theta = dist_theta(gen);
            double r_xy = std::sqrt(1.0 - z * z);
            
            double r = max_r * emitter_distance_ratio;
            pos = Vec3(r * r_xy * std::cos(theta), r * r_xy * std::sin(theta), r * z);
            base_dir = pos * (-1.0 / std::max(r, 0.001));
        } else if (emitter_mode == 2) {
            double lon = emitter_lon * M_PI / 180.0;
            double lat = emitter_lat * M_PI / 180.0;
            Vec3 W(std::cos(lat) * std::cos(lon), std::cos(lat) * std::sin(lon), std::sin(lat));
            
            double r_vol = max_r * spawn_radius_ratio;
            std::uniform_real_distribution<double> dist_u(0.0, 1.0);
            double u = dist_u(gen);
            double r_random = r_vol * std::cbrt(u);
            
            std::uniform_real_distribution<double> dist_z(-1.0, 1.0);
            double z = dist_z(gen);
            std::uniform_real_distribution<double> dist_theta(0.0, 2.0 * M_PI);
            double theta = dist_theta(gen);
            double r_xy = std::sqrt(1.0 - z * z);
            
            Vec3 offset(r_random * r_xy * std::cos(theta), r_random * r_xy * std::sin(theta), r_random * z);
            
            pos = W * (max_r * emitter_distance_ratio) + offset;
            base_dir = W * -1.0;
        } else {
            double lon = emitter_lon * M_PI / 180.0;
            double lat = emitter_lat * M_PI / 180.0;
            
            Vec3 W(std::cos(lat) * std::cos(lon), std::cos(lat) * std::sin(lon), std::sin(lat));
            
            Vec3 up(0, 0, 1);
            if (std::abs(W.z) > 0.99) up = Vec3(1, 0, 0);
            Vec3 U = W.cross(up); 
            U = U / U.norm();
            Vec3 V = W.cross(U);  
            V = V / V.norm();

            double r_disk_max = max_r * spawn_radius_ratio;
            std::uniform_real_distribution<double> dist_r(0.0, 1.0);
            double r_d = r_disk_max * std::sqrt(dist_r(gen));
            
            std::uniform_real_distribution<double> dist_theta(0.0, 2.0 * M_PI);
            double angle_d = dist_theta(gen);

            double disk_u = r_d * std::cos(angle_d);
            double disk_v = r_d * std::sin(angle_d);
            double dist_w = max_r * emitter_distance_ratio;

            pos = W * dist_w + U * disk_u + V * disk_v;
            base_dir = W * -1.0;
        }

        double v_sw_internal = emitter_v_base / 6371.0;
        std::normal_distribution<double> dist_v_mag(1.0, emitter_v_random / 100.0);
        double mag_factor = dist_v_mag(gen);
        if (mag_factor < 0.01) mag_factor = 0.01;

        ParticleType ptype;
        if (!active_particle_types.empty()) {
            std::vector<double> weights;
            for (const auto& t : active_particle_types) {
                weights.push_back(t.weight);
            }
            std::discrete_distribution<int> dist_type(weights.begin(), weights.end());
            ptype = active_particle_types[dist_type(gen)];
        } else {
            ptype = {1.0, 0.1, 0xffffff, 1.0, 1.0};
        }

        double final_v_mag = v_sw_internal * ptype.v_multiplier * mag_factor;
        const double c_speed = 299792.458 / 6371.0;
        if (final_v_mag >= c_speed) {
            final_v_mag = c_speed * 0.999999;
        }

        std::normal_distribution<double> dist_angle(0.0, emitter_angle_random / 100.0);
        Vec3 dir_offset(dist_angle(gen), dist_angle(gen), dist_angle(gen));
        Vec3 final_dir = base_dir + dir_offset;
        double fnorm = final_dir.norm();
        if (fnorm > 1e-6) final_dir = final_dir / fnorm;
        else final_dir = base_dir;

        Vec3 vel = final_dir * final_v_mag;

        if (pos.norm() < 1.05) {
            if (pos.norm() > 1e-6) pos = pos / pos.norm() * 1.05;
            else pos = Vec3(1.05, 0, 0);
        }

        if (p == nullptr) {
            return {id, ptype.q, ptype.mass, pos, vel, 0, ptype.color};
        } else {
            p->q = ptype.q;
            p->mass = ptype.mass;
            p->pos = pos;
            p->vel = vel;
            p->status = 0;
            p->color = ptype.color;
            return *p;
        }
    }

    double get_max_range() const { return b_field.max_range; }
    void set_max_range(double r) {
        if (std::abs(r - b_field.max_range) > 0.01) {
            b_field.max_range = r;
            needs_field_update = true;
        }
    }
    double get_compression() const { return b_field.solar_wind_compression; }
    
    void set_day_of_year(double day) {
        if (std::abs(day - b_field.day_of_year) > 0.1) {
            b_field.day_of_year = day;
            b_field.update_tilt();
            needs_field_update = true;
        }
    }

    void set_model_precision(int prec) {
        model_precision = prec;
        if (prec == 0) dt = 0.02;
        else if (prec == 1) dt = 0.01;
        else if (prec == 2) dt = 0.002;
        else if (prec == 3) dt = 0.0005;
    }

    void set_field_precision(int prec) {
        if (field_precision != prec) {
            field_precision = prec;
            needs_field_update = true;
        }
    }

    void set_b_multiplier(double val) {
        b_field.b_multiplier = val;
        needs_field_update = true;
    }

    void set_spawn_radius_ratio(double ratio) {
        spawn_radius_ratio = ratio;
    }

    void set_emitter_params(int mode, double lon, double lat, double v_base, double v_random, double angle_random, double dist_ratio) {
        emitter_mode = mode;
        emitter_lon = lon;
        emitter_lat = lat;
        emitter_v_base = v_base;
        emitter_v_random = v_random;
        emitter_angle_random = angle_random;
        emitter_distance_ratio = dist_ratio;
    }

    void set_magnetic_grid(const std::vector<double>& xs,
                           const std::vector<double>& ys,
                           const std::vector<double>& zs,
                           const std::vector<double>& bx,
                           const std::vector<double>& by,
                           const std::vector<double>& bz) {
        b_field.ext_grid.set_grid(xs, ys, zs, bx, by, bz);
        needs_field_update = true;
    }

    void clear_particle_types() {
        active_particle_types.clear();
    }

    void add_particle_type(double q, double mass, int color, double v_multiplier, double weight) {
        active_particle_types.push_back({q, mass, color, v_multiplier, weight});
    }

    void respawn_all() {
        for (auto& p : particles) {
            spawn_particle(p.id, &p);
        }
    }

    void set_solar_activity(double kp_index) {
        double new_comp = 1.0 + (kp_index / 9.0);
        if (std::abs(new_comp - b_field.solar_wind_compression) > 0.01) {
            b_field.solar_wind_compression = new_comp;
            needs_field_update = true;
        }
    }

    void set_compression(double comp) {
        if (std::abs(comp - b_field.solar_wind_compression) > 0.01) {
            b_field.solar_wind_compression = comp;
            needs_field_update = true;
        }
    }

    void boris_step(Particle& particle) {
        if (particle.status != 0) {
            spawn_particle(particle.id, &particle);
            return;
        }

        if (std::isnan(particle.pos.x) || std::isnan(particle.pos.y) || std::isnan(particle.pos.z) ||
            std::isnan(particle.vel.x) || std::isnan(particle.vel.y) || std::isnan(particle.vel.z)) {
            particle.status = 2;
            return;
        }

        double q_prime = (particle.q / particle.mass) * 2988.5959; 
        const double c = 299792.458 / 6371.0; 
        
        double v_mag2 = particle.vel.dot(particle.vel);
        if (v_mag2 >= c * c) {
            v_mag2 = c * c * 0.999999;
            particle.vel = particle.vel * (std::sqrt(v_mag2) / particle.vel.norm());
        }
        
        double gamma = 1.0 / std::sqrt(1.0 - v_mag2 / (c * c));
        Vec3 u = particle.vel * gamma; 
        
        Vec3 B = b_field.get_field(particle.pos);
        double B_mag = B.norm();
        
        double wc = std::abs(q_prime * B_mag) / gamma;
        
        int num_substeps = 1;
        if (wc * dt > 0.5) {
            num_substeps = (int)std::ceil(wc * dt / 0.5);
        }
        if (num_substeps > 20) num_substeps = 20;

        double sub_dt = dt / num_substeps;
        double sub_dt2 = sub_dt / 2.0;
        double GM = 1.5398e-6 * gravity_multiplier;

        for (int i = 0; i < num_substeps; ++i) {
            if (i > 0) B = b_field.get_field(particle.pos); 

            Vec3 g(0,0,0);
            if (enable_gravity) {
                double r_norm = particle.pos.norm();
                if (r_norm > 0.1) {
                    g = particle.pos * (-GM / (r_norm * r_norm * r_norm));
                }
            }

            Vec3 E(0,0,0);
            if (enable_electric_field) {
                if (efield_model == 0) {
                    Vec3 E_conv(0, 5.0e-6 * electric_field_multiplier, 0);
                    Vec3 Omega(0, 0, 7.27e-5);
                    Vec3 v_corot = Omega.cross(particle.pos);
                    Vec3 E_corot = v_corot.cross(B) * -1.0;
                    E = E_conv + E_corot;
                } else if (efield_model == 1) {
                    double r_norm = particle.pos.norm();
                    Vec3 Omega(0, 0, 7.27e-5);
                    Vec3 v_corot = Omega.cross(particle.pos);
                    Vec3 E_corot = v_corot.cross(B) * -1.0;
                    
                    double shielding = 1.0;
                    if (r_norm < 4.0 && r_norm > 0.1) {
                        shielding = std::pow(r_norm / 4.0, 2.0);
                    }
                    Vec3 E_conv(0, 5.0e-6 * electric_field_multiplier * shielding, 0);
                    E = E_conv + E_corot;
                }
            }

            Vec3 force_impulse = (E * q_prime + g) * sub_dt2;
            Vec3 u_minus = u + force_impulse;
            double gamma_minus = std::sqrt(1.0 + u_minus.dot(u_minus) / (c * c));
            
            Vec3 t = B * (q_prime * sub_dt2 / gamma_minus);
            double t_mag2 = t.dot(t);
            Vec3 s = t * (2.0 / (1.0 + t_mag2));

            Vec3 u_prime = u_minus + u_minus.cross(t);
            Vec3 u_plus = u_minus + u_prime.cross(s);

            u = u_plus + force_impulse;
            
            if (enable_atmosphere) {
                double r_norm = particle.pos.norm();
                if (r_norm < 1.15 && r_norm > 0.0) {
                    double nu = 0.0;
                    if (atmos_model == 0) {
                        nu = 100.0 * atmosphere_multiplier * std::exp(-(r_norm - 1.0) / 0.01);
                    } else if (atmos_model == 1) {
                        double h = (r_norm - 1.0) * 6371.0;
                        if (h < 100.0) {
                            nu = 1000.0 * std::exp(-h / 8.0);
                        } else if (h < 500.0) {
                            nu = 10.0 * std::exp(-(h - 100.0) / 40.0);
                        } else {
                            nu = 0.5 * std::exp(-(h - 500.0) / 100.0);
                        }
                        nu *= atmosphere_multiplier;
                    }
                    double factor = 1.0 - nu * sub_dt;
                    if (factor < 0.0) factor = 0.0; 
                    u = u * factor;
                }
            }

            gamma = std::sqrt(1.0 + u.dot(u) / (c * c));
            particle.vel = u / gamma;
            particle.pos += particle.vel * sub_dt;
        }

        double r_norm = particle.pos.norm();
        if (std::isnan(r_norm) || !std::isfinite(r_norm)) {
            particle.status = 2;
            particle.pos = Vec3(2000.0, 0, 0); 
            particle.vel = Vec3(0, 0, 0);
        } else if (r_norm < 1.0) {
            particle.status = 1;
        } else if (r_norm > b_field.max_range + 2.0) {
            particle.status = 2;
        }
    }

    void step() {
        int n = particles.size();
        int num_threads = std::thread::hardware_concurrency();
        if (num_threads == 0) num_threads = 4;
        
        std::vector<std::thread> threads;
        int chunk_size = (n + num_threads - 1) / num_threads;

        for (int t = 0; t < num_threads; ++t) {
            int start = t * chunk_size;
            int end = std::min(start + chunk_size, n);
            if (start >= end) break;

            threads.emplace_back([this, start, end]() {
                for (int i = start; i < end; ++i) {
                    this->boris_step(particles[i]);
                }
            });
        }

        for (auto& th : threads) {
            th.join();
        }
    }

    nlohmann::json get_state() {
        nlohmann::json state = nlohmann::json::array();
        for (const auto& p : particles) {
            nlohmann::json p_dict = nlohmann::json::object();
            p_dict["i"] = p.id;
            p_dict["p"] = {std::isfinite(p.pos.x) ? p.pos.x : 2000.0, std::isfinite(p.pos.z) ? p.pos.z : 0.0, std::isfinite(p.pos.y) ? -p.pos.y : 0.0};
            p_dict["s"] = p.status;
            p_dict["c"] = p.color;
            state.push_back(p_dict);
        }
        return state;
    }

    void get_state_binary(std::vector<uint8_t>& buffer) {
        size_t total = particles.size() * 21;
        buffer.resize(total);
        uint8_t* ptr = buffer.data();
        for (const auto& p : particles) {
            float px = std::isfinite(p.pos.x) ? (float)p.pos.x : 2000.0f;
            float py = std::isfinite(p.pos.z) ? (float)p.pos.z : 0.0f;
            float pz = std::isfinite(p.pos.y) ? -(float)p.pos.y : 0.0f;

            int32_t id = p.id;
            uint8_t status = (uint8_t)p.status;
            uint32_t color = (uint32_t)p.color;

            memcpy(ptr, &id, 4); ptr += 4;
            memcpy(ptr, &px, 4); ptr += 4;
            memcpy(ptr, &py, 4); ptr += 4;
            memcpy(ptr, &pz, 4); ptr += 4;
            *ptr++ = status;
            memcpy(ptr, &color, 4); ptr += 4;
        }
    }

    nlohmann::json compute_field_lines() {
        nlohmann::json lines = nlohmann::json::array();
        std::vector<double> L_shells;
        int num_angles;
        double step;
        
        if (field_precision == 0) {
            L_shells = {2.0, 4.0, 6.0};
            num_angles = 4;
            step = 0.1;
        } else if (field_precision == 1) {
            L_shells = {1.5, 2.5, 4.0, 6.0, 8.0};
            num_angles = 8;
            step = 0.05;
        } else if (field_precision == 2) {
            L_shells = {1.2, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0};
            num_angles = 16;
            step = 0.02;
        } else {
            L_shells = {1.2, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0};
            num_angles = 32;
            step = 0.01;
        }

        double total_tilt = b_field.total_tilt;
        Vec3 z_m(std::sin(total_tilt), 0.0, std::cos(total_tilt));
        Vec3 y_m(0.0, 1.0, 0.0);
        Vec3 x_m = y_m.cross(z_m);

        double max_s = b_field.max_range * 4.0;

        auto trace = [&](Vec3 start_pos, int dir) {
            std::vector<Vec3> line;
            line.push_back(start_pos);
            Vec3 pos = start_pos;
            double s = 0;
            while (s < max_s) {
                Vec3 B = b_field.get_field(pos);
                double B_mag = B.norm();
                if (B_mag < 1e-9) break;
                Vec3 B_dir = B / B_mag;
                Vec3 dpos = B_dir * (step * dir);
                pos += dpos;
                s += step;
                line.push_back(pos);

                double r = pos.norm();
                if (r < 1.0 || r > b_field.max_range) break;

                // 防折返截断
                if (pos.x < -2.0 && B_dir.x > 0.0) break;
            }
            return line;
        };

        for (double L : L_shells) {
            for (int i = 0; i < num_angles; ++i) {
                double angle = i * 2.0 * M_PI / num_angles;
                Vec3 start_pos = x_m * (L * std::cos(angle)) + y_m * (L * std::sin(angle));
                if (start_pos.norm() > b_field.max_range) continue;

                std::vector<Vec3> line_fwd = trace(start_pos, 1);
                std::vector<Vec3> line_bwd = trace(start_pos, -1);

                nlohmann::json full_line = nlohmann::json::array();
                for (int j = line_bwd.size() - 1; j >= 1; --j) {
                    full_line.push_back({line_bwd[j].x, line_bwd[j].y, line_bwd[j].z});
                }
                for (size_t j = 0; j < line_fwd.size(); ++j) {
                    full_line.push_back({line_fwd[j].x, line_fwd[j].y, line_fwd[j].z});
                }
                if (full_line.size() > 1) {
                    lines.push_back(full_line);
                }
            }
        }

        // ===============================================================
        // IMF / Solar Wind Field Lines
        // Seed points placed in the solar wind / magnetosheath region.
        // These trace the Parker spiral (45° angle) far from the Earth.
        // ===============================================================
        if (field_precision >= 1) {
            double imf_step = (field_precision <= 1) ? 0.1 : 0.05;
            double max_range_2 = b_field.max_range * 2.0;

            auto trace_imf = [&](Vec3 start_pos, int dir) {
                std::vector<Vec3> line;
                line.push_back(start_pos);
                Vec3 pos = start_pos;
                double s = 0;
                while (s < max_range_2) {
                    Vec3 B = b_field.get_field(pos);
                    double B_mag = B.norm();
                    if (B_mag < 1e-9) break;
                    Vec3 B_dir = B / B_mag;
                    Vec3 dpos = B_dir * (imf_step * dir);
                    pos += dpos;
                    s += imf_step;
                    line.push_back(pos);

                    double r = pos.norm();
                    if (r < 1.0 || r > b_field.max_range + 5.0) break;
                }
                return line;
            };

            // Sunward seeds: X=+18Re, Y/Z grid spanning ±25Re (solar wind / magnetosheath)
            int n_imf = (field_precision <= 1) ? 5 : 9;
            double yz_range = (field_precision <= 1) ? 20.0 : 25.0;
            for (int iy = 0; iy < n_imf; ++iy) {
                double y_seed = -yz_range + 2.0 * yz_range * iy / (n_imf - 1);
                for (int iz = 0; iz < n_imf; ++iz) {
                    double z_seed = -yz_range + 2.0 * yz_range * iz / (n_imf - 1);
                    // Skip seeds too close to the axis (they'd hit the magnetopause)
                    double dist_yz = std::sqrt(y_seed * y_seed + z_seed * z_seed);
                    if (dist_yz < 5.0) continue;

                    Vec3 seed(18.0, y_seed, z_seed);
                    if (seed.norm() > b_field.max_range) continue;

                    std::vector<Vec3> line_fwd = trace_imf(seed, 1);
                    std::vector<Vec3> line_bwd = trace_imf(seed, -1);

                    nlohmann::json full_line = nlohmann::json::array();
                    for (int j = line_bwd.size() - 1; j >= 1; --j) {
                        full_line.push_back({line_bwd[j].x, line_bwd[j].y, line_bwd[j].z});
                    }
                    for (size_t j = 0; j < line_fwd.size(); ++j) {
                        full_line.push_back({line_fwd[j].x, line_fwd[j].y, line_fwd[j].z});
                    }
                    if (full_line.size() > 2) {
                        lines.push_back(full_line);
                    }
                }
            }

            // Far-tail flank seeds: X=-30Re, |Y|=20Re, Z span ±15Re
            if (field_precision >= 2) {
                int n_flank = 7;
                for (int iy_sign = 0; iy_sign < 2; ++iy_sign) {
                    double y_seed = (iy_sign == 0) ? 20.0 : -20.0;
                    for (int iz = 0; iz < n_flank; ++iz) {
                        double z_seed = -15.0 + 30.0 * iz / (n_flank - 1);
                        Vec3 seed(-30.0, y_seed, z_seed);
                        if (seed.norm() > b_field.max_range) continue;

                        std::vector<Vec3> line_fwd = trace_imf(seed, 1);
                        std::vector<Vec3> line_bwd = trace_imf(seed, -1);

                        nlohmann::json full_line = nlohmann::json::array();
                        for (int j = line_bwd.size() - 1; j >= 1; --j) {
                            full_line.push_back({line_bwd[j].x, line_bwd[j].y, line_bwd[j].z});
                        }
                        for (size_t j = 0; j < line_fwd.size(); ++j) {
                            full_line.push_back({line_fwd[j].x, line_fwd[j].y, line_fwd[j].z});
                        }
                        if (full_line.size() > 2) {
                            lines.push_back(full_line);
                        }
                    }
                }
            }
        }

        return lines;
    }

    Vec3 compute_efield_at_point(const Vec3& pos) const {
        Vec3 E(0, 0, 0);
        if (!enable_electric_field) return E;

        Vec3 B = b_field.get_field(pos);

        if (efield_model == 0) {
            Vec3 E_conv(0, 5.0e-6 * electric_field_multiplier, 0);
            Vec3 Omega(0, 0, 7.27e-5);
            Vec3 v_corot = Omega.cross(pos);
            Vec3 E_corot = v_corot.cross(B) * -1.0;
            E = E_conv + E_corot;
        } else if (efield_model == 1) {
            double r_norm = pos.norm();
            Vec3 Omega(0, 0, 7.27e-5);
            Vec3 v_corot = Omega.cross(pos);
            Vec3 E_corot = v_corot.cross(B) * -1.0;
            
            double shielding = 1.0;
            if (r_norm < 4.0 && r_norm > 0.1) {
                shielding = std::pow(r_norm / 4.0, 2.0);
            }
            Vec3 E_conv(0, 5.0e-6 * electric_field_multiplier * shielding, 0);
            E = E_conv + E_corot;
        }
        return E;
    }

    nlohmann::json compute_efield_lines() {
        nlohmann::json lines = nlohmann::json::array();
        if (!enable_electric_field) return lines;

        // E-field lines in the equatorial plane (magnetic equatorial plane, Z=0 in dipole frame)
        double total_tilt = b_field.total_tilt;
        Vec3 z_m(std::sin(total_tilt), 0.0, std::cos(total_tilt));
        Vec3 y_m(0.0, 1.0, 0.0);
        Vec3 x_m = y_m.cross(z_m);

        double step = 0.15;
        double max_s = b_field.max_range * 3.0;
        int num_seeds_radial = 12;
        int num_seeds_angular = 16;

        auto trace_e = [&](Vec3 start_pos, int dir) {
            std::vector<Vec3> line;
            line.push_back(start_pos);
            Vec3 pos = start_pos;
            double s = 0;
            while (s < max_s) {
                Vec3 E = compute_efield_at_point(pos);
                double E_mag = E.norm();
                if (E_mag < 1e-12) break;
                Vec3 E_dir = E / E_mag;
                // Project to equatorial plane
                Vec3 dpos = E_dir * (step * dir);
                pos += dpos;
                s += step;
                line.push_back(pos);

                double r = pos.norm();
                if (r < 1.0 || r > b_field.max_range) break;
                if (pos.z > 5.0 || pos.z < -5.0) break;
            }
            return line;
        };

        for (int ir = 0; ir < num_seeds_radial; ++ir) {
            double R = 2.0 + ir * (b_field.max_range - 2.0) / (num_seeds_radial - 1);
            for (int ia = 0; ia < num_seeds_angular; ++ia) {
                double angle = ia * 2.0 * M_PI / num_seeds_angular;
                Vec3 start_pos = x_m * (R * std::cos(angle)) + y_m * (R * std::sin(angle));
                if (start_pos.norm() > b_field.max_range) continue;

                std::vector<Vec3> line_fwd = trace_e(start_pos, 1);
                std::vector<Vec3> line_bwd = trace_e(start_pos, -1);

                nlohmann::json full_line = nlohmann::json::array();
                for (int j = line_bwd.size() - 1; j >= 1; --j) {
                    full_line.push_back({line_bwd[j].x, line_bwd[j].y, line_bwd[j].z});
                }
                for (size_t j = 0; j < line_fwd.size(); ++j) {
                    full_line.push_back({line_fwd[j].x, line_fwd[j].y, line_fwd[j].z});
                }
                if (full_line.size() > 2) {
                    lines.push_back(full_line);
                }
            }
        }
        return lines;
    }
};
