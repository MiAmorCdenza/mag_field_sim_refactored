#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <vector>
#include <cmath>
#include <random>
#include <thread>
#include <algorithm>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

namespace py = pybind11;

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
    double x_min, x_max, y_min, y_max, z_min, z_max;
    int nx, ny, nz;
    double dx, dy, dz;
    std::vector<double> Bx_grid, By_grid, Bz_grid;

    MagneticGrid() : nx(0), ny(0), nz(0) {}

    bool is_valid() const {
        return nx > 0 && ny > 0 && nz > 0 && Bx_grid.size() == (size_t)(nx * ny * nz);
    }

    void set_grid(double xmin, double xmax, int nx_,
                  double ymin, double ymax, int ny_,
                  double zmin, double zmax, int nz_,
                  const std::vector<double>& bx,
                  const std::vector<double>& by,
                  const std::vector<double>& bz) {
        x_min = xmin; x_max = xmax; nx = nx_; dx = (nx > 1) ? (xmax - xmin) / (nx - 1) : 1.0;
        y_min = ymin; y_max = ymax; ny = ny_; dy = (ny > 1) ? (ymax - ymin) / (ny - 1) : 1.0;
        z_min = zmin; z_max = zmax; nz = nz_; dz = (nz > 1) ? (zmax - zmin) / (nz - 1) : 1.0;
        Bx_grid = bx; By_grid = by; Bz_grid = bz;
    }

    Vec3 interpolate(double x, double y, double z) const {
        if (!is_valid()) return Vec3(0,0,0);
        
        // Clamp to grid boundaries
        if (x < x_min) x = x_min;
        if (x > x_max) x = x_max;
        if (y < y_min) y = y_min;
        if (y > y_max) y = y_max;
        if (z < z_min) z = z_min;
        if (z > z_max) z = z_max;

        double fi = (x - x_min) / dx;
        double fj = (y - y_min) / dy;
        double fk = (z - z_min) / dz;

        int i = (int)fi; int j = (int)fj; int k = (int)fk;
        if (i >= nx - 1) i = nx - 2;
        if (j >= ny - 1) j = ny - 2;
        if (k >= nz - 1) k = nz - 2;

        double tx = fi - i;
        double ty = fj - j;
        double tz = fk - k;

        auto get_val = [&](const std::vector<double>& arr, int i0, int j0, int k0) {
            return arr[(i0 * ny + j0) * nz + k0];
        };

        auto trilinear = [&](const std::vector<double>& arr) {
            double c00 = get_val(arr, i, j, k) * (1 - tx) + get_val(arr, i+1, j, k) * tx;
            double c01 = get_val(arr, i, j, k+1) * (1 - tx) + get_val(arr, i+1, j, k+1) * tx;
            double c10 = get_val(arr, i, j+1, k) * (1 - tx) + get_val(arr, i+1, j+1, k) * tx;
            double c11 = get_val(arr, i, j+1, k+1) * (1 - tx) + get_val(arr, i+1, j+1, k+1) * tx;

            double c0 = c00 * (1 - ty) + c10 * ty;
            double c1 = c01 * (1 - ty) + c11 * ty;

            return c0 * (1 - tz) + c1 * tz;
        };

        return Vec3(trilinear(Bx_grid), trilinear(By_grid), trilinear(Bz_grid));
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
        day_of_year = 172.0; // Default summer solstice
        solar_wind_compression = 1.0;
        max_range = 10.0;
        b_multiplier = 1.0;
        update_tilt();
    }

    void update_tilt() {
        double tilt_rot_max = 23.44 * M_PI / 180.0;
        double tilt_mag_offset = 11.0 * M_PI / 180.0;
        
        // Seasonal tilt towards the Sun (+X is Sun).
        // At day 172 (summer solstice), North pole tilts towards Sun by max amount.
        seasonal_tilt = tilt_rot_max * std::cos(2.0 * M_PI * (day_of_year - 172.0) / 365.25);
        total_tilt = seasonal_tilt + tilt_mag_offset;
        
        m = Vec3(-std::sin(total_tilt), 0.0, -std::cos(total_tilt)) * dipole_moment;
    }

    Vec3 get_field(const Vec3& r_vec) const {
        double r = r_vec.norm();
        if (r < 0.1) return Vec3(0, 0, 0);

        Vec3 r_hat = r_vec / r;
        Vec3 B_earth = (r_hat * (3.0 * m.dot(r_hat)) - m) * (1.0 / (r * r * r));

        if (ext_grid.is_valid()) {
            Vec3 B_ext = ext_grid.interpolate(r_vec.x, r_vec.y, r_vec.z);
            // Convert Tsyganenko output (nT) to simulation units.
            // 31200 nT corresponds to dipole_moment = 1.0 at 1 RE equator.
            double conversion_factor = dipole_moment / 31200.0;
            return (B_earth + B_ext * conversion_factor) * b_multiplier;
        }

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
            double tail_strength = 0.8 * solar_wind_compression;  // 强度调大 
            double z_decay = std::exp(-z * z / 6.0);              // 赤道面最强 
            double Bx = -tail_strength * z_decay;                 // 始终指向 -X (远离太阳) 
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
    int status; // 0: alive, 1: collided, 2: out of bounds
    int color;
};

class SimulationEngine {
public:
    MagneticField b_field;
    std::vector<Particle> particles;
    double dt;
    bool needs_field_update;
    int next_id;
    int model_precision; // 0: low, 1: med, 2: high, 3: ultra
    int field_precision; // 0: low, 1: med, 2: high, 3: ultra
    double spawn_radius_ratio;
    std::vector<ParticleType> active_particle_types;
    double emitter_v_base;
    int emitter_mode; // 0: directional, 1: omnidirectional
    double emitter_lon; // degrees (0 is sun, 180 is night)
    double emitter_lat; // degrees
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
        
        // Default mixed types
        active_particle_types.push_back({1.0, 0.1, 0xff3333, 1.0, 1.0});
        active_particle_types.push_back({-1.0, 0.1, 0x3333ff, 1.0, 1.0});
        
        set_particle_count(100);
    }

    Particle spawn_particle(int id, Particle* p = nullptr) {
        double max_r = b_field.max_range;
        
        static thread_local std::mt19937 gen(std::random_device{}());
        Vec3 pos;
        Vec3 base_dir;

        if (emitter_mode == 1) {
            // Omnidirectional mode
            std::uniform_real_distribution<double> dist_z(-1.0, 1.0);
            double z = dist_z(gen);
            std::uniform_real_distribution<double> dist_theta(0.0, 2.0 * M_PI);
            double theta = dist_theta(gen);
            double r_xy = std::sqrt(1.0 - z * z);
            
            double r = max_r * emitter_distance_ratio;
            pos = Vec3(r * r_xy * std::cos(theta), r * r_xy * std::sin(theta), r * z);
            base_dir = pos * (-1.0 / std::max(r, 0.001)); // Points exactly to origin
        } else if (emitter_mode == 2) {
            // Volume random mode
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
            base_dir = W * -1.0; // Base direction is towards origin
        } else {
            // Directional mode
            double lon = emitter_lon * M_PI / 180.0;
            double lat = emitter_lat * M_PI / 180.0;
            
            // W is the vector from origin to the center of the emitter disk
            // GSE coords: X is Sun (0 lon, 0 lat). Y is dusk (90 lon). Z is North (90 lat).
            Vec3 W(std::cos(lat) * std::cos(lon), std::cos(lat) * std::sin(lon), std::sin(lat));
            
            // Calculate orthogonal basis (U, V) for the disk
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
            base_dir = W * -1.0; // Emission direction is opposite to the center vector
        }

        double v_sw_internal = emitter_v_base / 6371.0; // Convert km/s to RE/s
        std::normal_distribution<double> dist_v_mag(1.0, emitter_v_random / 100.0);
        double mag_factor = dist_v_mag(gen);
        // Prevent particles from having exactly 0 velocity (which would cause them to freeze forever)
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

        // Prevent particles from spawning directly inside the Earth (which causes instant collision and leaves garbage trails)
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

    void set_particle_count(int count) {
        int current = particles.size();
        if (count > current) {
            for (int i = 0; i < count - current; ++i) {
                particles.push_back(spawn_particle(next_id++));
            }
        } else if (count < current) {
            particles.resize(count);
        }
    }

    void set_solar_activity(double kp_index) {
        double new_comp = 1.0 + (kp_index / 9.0);
        if (std::abs(new_comp - b_field.solar_wind_compression) > 0.01) {
            b_field.solar_wind_compression = new_comp;
            needs_field_update = true;
        }
    }

    void set_max_range(double r) {
        if (std::abs(r - b_field.max_range) > 0.01) {
            b_field.max_range = r;
            needs_field_update = true;
        }
    }

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

    void set_magnetic_grid(double xmin, double xmax, int nx,
                           double ymin, double ymax, int ny,
                           double zmin, double zmax, int nz,
                           const std::vector<double>& bx,
                           const std::vector<double>& by,
                           const std::vector<double>& bz) {
        b_field.ext_grid.set_grid(xmin, xmax, nx, ymin, ymax, ny, zmin, zmax, nz, bx, by, bz);
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

    double get_max_range() const { return b_field.max_range; }
    double get_compression() const { return b_field.solar_wind_compression; }
    bool get_needs_field_update() const { return needs_field_update; }
    void set_needs_field_update(bool v) { needs_field_update = v; }

    void boris_step(Particle& particle) {
        if (particle.status != 0) {
            spawn_particle(particle.id, &particle);
            return;
        }

        // Failsafe: if a particle ever becomes NaN (e.g. from Python grid singularities), kill it immediately
        if (std::isnan(particle.pos.x) || std::isnan(particle.pos.y) || std::isnan(particle.pos.z) ||
            std::isnan(particle.vel.x) || std::isnan(particle.vel.y) || std::isnan(particle.vel.z)) {
            particle.status = 2;
            return;
        }

        // Real physical Lorentz force conversion
        // Elementary charge e = 1.602176634e-19 C
        // Atomic mass unit amu = 1.67262192e-27 kg
        // Earth radius RE = 6371000 m
        // B field unit = 31200 nT = 3.12e-5 T (since dipole_moment=1.0 is 31200 nT at equator)
        // Acceleration in RE/s^2 requires scaling by 1/RE
        // factor = (e/amu) * 3.12e-5 = 2988.5959
        double q_prime = (particle.q / particle.mass) * 2988.5959; 
        
        const double c = 299792.458 / 6371.0; // speed of light in RE/s
        
        double v_mag2 = particle.vel.dot(particle.vel);
        if (v_mag2 >= c * c) {
            v_mag2 = c * c * 0.999999;
            particle.vel = particle.vel * (std::sqrt(v_mag2) / particle.vel.norm());
        }
        
        double gamma = 1.0 / std::sqrt(1.0 - v_mag2 / (c * c));
        Vec3 u = particle.vel * gamma; // Relativistic momentum per unit mass
        
        Vec3 B = b_field.get_field(particle.pos);
        double B_mag = B.norm();
        
        // Effective cyclotron frequency incorporating relativistic mass increase
        double wc = std::abs(q_prime * B_mag) / gamma;
        
        // Adaptive sub-stepping for stability and accuracy
        // We want wc * sub_dt < 0.5 rad per step ideally
        int num_substeps = 1;
        if (wc * dt > 0.5) {
            num_substeps = (int)std::ceil(wc * dt / 0.5);
        }
        // Cap substeps to prevent extreme lag for lightweight particles (e.g., electrons)
        // Boris algorithm is unconditionally stable for energy, so capping at 20 is safe
        // and keeps the simulation running at 60 FPS even with 2000 electrons.
        if (num_substeps > 20) num_substeps = 20;

        double sub_dt = dt / num_substeps;
        double sub_dt2 = sub_dt / 2.0;

        double GM = 1.5398e-6 * gravity_multiplier;

        for (int i = 0; i < num_substeps; ++i) {
            if (i > 0) {
                // Update B only every 5 substeps to save CPU, or just let it update.
                // Given max substeps=20, updating B is fine, but we can optimize.
                B = b_field.get_field(particle.pos); 
            }

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
                    // Simple Convection
                    Vec3 E_conv(0, 5.0e-6 * electric_field_multiplier, 0);
                    Vec3 Omega(0, 0, 7.27e-5);
                    Vec3 v_corot = Omega.cross(particle.pos);
                    Vec3 E_corot = v_corot.cross(B) * -1.0;
                    E = E_conv + E_corot;
                } else if (efield_model == 1) {
                    // Volland-Stern-like Model (Shielded Convection)
                    double r_norm = particle.pos.norm();
                    Vec3 Omega(0, 0, 7.27e-5);
                    Vec3 v_corot = Omega.cross(particle.pos);
                    Vec3 E_corot = v_corot.cross(B) * -1.0;
                    
                    // Convection shielded inside r < 4
                    double shielding = 1.0;
                    if (r_norm < 4.0 && r_norm > 0.1) {
                        shielding = std::pow(r_norm / 4.0, 2.0);
                    }
                    Vec3 E_conv(0, 5.0e-6 * electric_field_multiplier * shielding, 0);
                    E = E_conv + E_corot;
                }
            }

            // Effective force impulse from Electric Field and Gravity
            // g is acceleration, E * q_prime is acceleration
            Vec3 force_impulse = (E * q_prime + g) * sub_dt2;

            Vec3 u_minus = u + force_impulse;
            double gamma_minus = std::sqrt(1.0 + u_minus.dot(u_minus) / (c * c));
            
            // Relativistic Boris rotation
            Vec3 t = B * (q_prime * sub_dt2 / gamma_minus);
            double t_mag2 = t.dot(t);
            Vec3 s = t * (2.0 / (1.0 + t_mag2));

            Vec3 u_prime = u_minus + u_minus.cross(t);
            Vec3 u_plus = u_minus + u_prime.cross(s);

            u = u_plus + force_impulse;
            
            // Atmosphere Drag & Scattering (Thermosphere/Ionosphere)
            if (enable_atmosphere) {
                double r_norm = particle.pos.norm();
                if (r_norm < 1.15 && r_norm > 0.0) {
                    double nu = 0.0;
                    if (atmos_model == 0) {
                        // Exponential density decay, scale height ~0.01 Re (63km)
                        nu = 100.0 * atmosphere_multiplier * std::exp(-(r_norm - 1.0) / 0.01);
                    } else if (atmos_model == 1) {
                        // Piecewise exponential (Thermosphere + Exosphere)
                        double h = (r_norm - 1.0) * 6371.0; // height in km
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
                    if (factor < 0.0) factor = 0.0; // Prevent negative oscillation
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
            particle.pos = Vec3(2000.0, 0, 0); // safe position far away
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

    py::list get_state() {
        py::list state;
        for (const auto& p : particles) {
            py::dict p_dict;
            p_dict["id"] = p.id;
            p_dict["q"] = p.q;
            
            py::list pos_list;
            pos_list.append(std::isfinite(p.pos.x) ? p.pos.x : 2000.0);
            pos_list.append(std::isfinite(p.pos.y) ? p.pos.y : 0.0);
            pos_list.append(std::isfinite(p.pos.z) ? p.pos.z : 0.0);
            p_dict["pos"] = pos_list;

            py::list vel_list;
            vel_list.append(std::isfinite(p.vel.x) ? p.vel.x : 0.0);
            vel_list.append(std::isfinite(p.vel.y) ? p.vel.y : 0.0);
            vel_list.append(std::isfinite(p.vel.z) ? p.vel.z : 0.0);
            p_dict["vel"] = vel_list;

            p_dict["status"] = p.status;
            p_dict["color"] = p.color;

            state.append(p_dict);
        }
        return state;
    }

    py::list compute_field_lines() {
        py::list lines;
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

                py::list full_line;
                for (int j = line_bwd.size() - 1; j >= 1; --j) {
                    py::list pt;
                    pt.append(line_bwd[j].x); pt.append(line_bwd[j].y); pt.append(line_bwd[j].z);
                    full_line.append(pt);
                }
                for (size_t j = 0; j < line_fwd.size(); ++j) {
                    py::list pt;
                    pt.append(line_fwd[j].x); pt.append(line_fwd[j].y); pt.append(line_fwd[j].z);
                    full_line.append(pt);
                }
                if (full_line.size() > 1) {
                    lines.append(full_line);
                }
            }
        }
        return lines;
    }
};

PYBIND11_MODULE(physics_ext, m) {
    py::class_<SimulationEngine>(m, "SimulationEngine")
        .def(py::init<>())
        .def("set_particle_count", &SimulationEngine::set_particle_count)
        .def("set_solar_activity", &SimulationEngine::set_solar_activity)
        .def("set_max_range", &SimulationEngine::set_max_range)
        .def("set_day_of_year", &SimulationEngine::set_day_of_year)
        .def("set_model_precision", &SimulationEngine::set_model_precision)
        .def("set_field_precision", &SimulationEngine::set_field_precision)
        .def("set_b_multiplier", &SimulationEngine::set_b_multiplier)
        .def("set_spawn_radius_ratio", &SimulationEngine::set_spawn_radius_ratio)
        .def("set_emitter_params", &SimulationEngine::set_emitter_params)
        .def("set_magnetic_grid", &SimulationEngine::set_magnetic_grid)
        .def("clear_particle_types", &SimulationEngine::clear_particle_types)
        .def("add_particle_type", &SimulationEngine::add_particle_type)
        .def("respawn_all", &SimulationEngine::respawn_all)
        .def_property("max_range", &SimulationEngine::get_max_range, &SimulationEngine::set_max_range)
        .def_property_readonly("solar_wind_compression", &SimulationEngine::get_compression)
        .def_property_readonly("seasonal_tilt", [](SimulationEngine& self) { return self.b_field.seasonal_tilt; })
        .def_property_readonly("total_tilt", [](SimulationEngine& self) { return self.b_field.total_tilt; })
        .def_property("needs_field_update", &SimulationEngine::get_needs_field_update, &SimulationEngine::set_needs_field_update)
        .def_readwrite("enable_gravity", &SimulationEngine::enable_gravity)
        .def_readwrite("gravity_multiplier", &SimulationEngine::gravity_multiplier)
        .def_readwrite("enable_electric_field", &SimulationEngine::enable_electric_field)
        .def_readwrite("electric_field_multiplier", &SimulationEngine::electric_field_multiplier)
        .def_readwrite("enable_atmosphere", &SimulationEngine::enable_atmosphere)
        .def_readwrite("atmosphere_multiplier", &SimulationEngine::atmosphere_multiplier)
        .def_readwrite("atmos_model", &SimulationEngine::atmos_model)
        .def_readwrite("efield_model", &SimulationEngine::efield_model)
        .def("step", &SimulationEngine::step)
        .def("get_state", &SimulationEngine::get_state)
        .def("compute_field_lines", &SimulationEngine::compute_field_lines);
}