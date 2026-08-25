#include "sim_pipeline.h"
#include "encoder.h"

SimPipeline::SimPipeline(const PipelineConfig& cfg)
    : emitter(cfg.emitter), icfg(cfg.integrator),
      steps_per_frame(cfg.steps_per_frame), max_range(cfg.integrator.max_range) {
    particles.resize((size_t)cfg.particle_count);
    respawn();
}

bool SimPipeline::install_baked(const BakedField& f, std::string& err) {
    Table3D* t = nullptr;
    bool scale_to_normalized = false;
    if (f.slot == "B") { t = &b_table; scale_to_normalized = true; }
    else if (f.slot == "E") { t = &e_table; }           // 节点已输出归一化单位
    else if (f.slot == "drag") { t = &drag_table; }      // 无量纲系数
    else if (f.slot == "gravity") { t = &drag_table; }   // v1 引力走解析;槽位预留
    else { err = "未知槽位: " + f.slot; return false; }

    if (f.is_vector) {
        if (scale_to_normalized) {
            // nT → 归一化单位(与旧引擎 get_field 的 scale_factor 一致,
            // 使 q_prime=(q/m)*2988.5959 给出正确回旋频率)
            const double s = 1.0 / 31200.0;
            std::vector<double> c0(f.c0), c1(f.c1), c2(f.c2);
            for (auto& v : c0) v *= s;
            for (auto& v : c1) v *= s;
            for (auto& v : c2) v *= s;
            t->set_grid(f.xs, f.ys, f.zs, c0, c1, c2);
        } else {
            t->set_grid(f.xs, f.ys, f.zs, f.c0, f.c1, f.c2);
        }
    } else {
        t->set_grid(f.xs, f.ys, f.zs, f.c0, {}, {});
    }
    return true;
}

void SimPipeline::respawn() {
    for (size_t i = 0; i < particles.count; ++i) {
        if (particles.status[i] == 1 || particles.status[i] == 2 ||
            particles.id[i] == 0) {
            emitter.spawn(particles, i, ++next_id_);
        }
    }
}

void SimPipeline::step_frame() {
    ForceTables ft;
    ft.b = b_table.has_data() ? &b_table : nullptr;
    ft.e = e_table.has_data() ? &e_table : nullptr;
    ft.drag = drag_table.has_data() ? &drag_table : nullptr;
    for (int s = 0; s < steps_per_frame; ++s) step_parallel(particles, icfg, ft);
}

void SimPipeline::encode(std::vector<uint8_t>& out) const {
    encode_particles(particles, out);
}
