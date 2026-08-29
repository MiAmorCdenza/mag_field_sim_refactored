#include "sim_pipeline.h"

#include "encoder.h"
#include "../core/plan_compiler.h"

SimPipeline::SimPipeline(const PipelineConfig& cfg) : emitter(cfg.emitter) {
    particles.resize((size_t)cfg.particle_count);
    Plan p = plancomp::make_default_plan(cfg.emitter, cfg.steps_per_frame,
                                         cfg.integrator);
    std::string err;
    if (!set_plan(p, err)) {
        // 后备计划必然合法;防御性保留(内核注册表缺失时无法推进)
    }
    respawn();
}

bool SimPipeline::set_plan(const Plan& p, std::string& err) {
    for (const auto& op : p.ops) {
        if (op.kind == OpKind::Step && find_advancer(op.step.kernel) == nullptr) {
            err = "未知推进内核: " + op.step.kernel;
            return false;
        }
    }
    plan = p;
    max_range = 90.0;
    for (const auto& op : plan.ops) {
        if (op.kind == OpKind::Step && op.step.max_range > max_range)
            max_range = op.step.max_range;
    }
    // 物种聚合:图中声明式 particle_species 节点 → 发射器类型列表
    // (一个节点 = 一个物种;enabled=false 不参与生成)
    species_types_.clear();
    for (const auto& op : plan.ops) {
        if (op.kind == OpKind::Species && op.species.enabled)
            species_types_.push_back(op.species.type);
    }
    // 图内发射器节点(node_id != "__default")→ 重建发射器并接管;
    // 后备计划的发射器保持由服务器 st.emitter 驱动(legacy 兼容)
    has_emitter_op = false;
    for (const auto& op : plan.ops) {
        if (op.kind != OpKind::Emitter) continue;
        EmitterConfig ecfg = op.emitter.cfg;
        if (!species_types_.empty()) ecfg.types = species_types_;  // 物种节点优先
        emitter = Emitter(ecfg);
        if (op.node_id != "__default") has_emitter_op = true;
        break;  // 首个 EmitterOp 生效(v1)
    }
    return true;
}

void SimPipeline::reapply_species() {
    if (!species_types_.empty()) emitter.set_types(species_types_);
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

const Table3D* SimPipeline::table_for(const std::string& slot) const {
    if (slot == "B" && b_table.has_data()) return &b_table;
    if (slot == "E" && e_table.has_data()) return &e_table;
    if (slot == "drag" && drag_table.has_data()) return &drag_table;
    return nullptr;
}

void SimPipeline::respawn() {
    for (size_t i = 0; i < particles.count; ++i) {
        if (particles.status[i] == 1 || particles.status[i] == 2 ||
            particles.id[i] == 0) {
            emitter.spawn(particles, i, ++next_id_);
        }
    }
}

void SimPipeline::respawn_all() {
    for (size_t i = 0; i < particles.count; ++i)
        emitter.spawn(particles, i, ++next_id_);
}

void SimPipeline::step_frame() {
    for (const auto& op : plan.ops) {
        if (op.kind != OpKind::Step) continue;
        const IBatchAdvancer* adv = find_advancer(op.step.kernel);
        if (!adv) continue;  // set_plan 已校验;防御
        AdvanceInput in;
        in.b = table_for(op.step.b_slot);
        in.e = table_for(op.step.e_slot);
        in.drag = table_for(op.step.drag_slot);
        in.dt = op.step.dt;
        in.max_range = op.step.max_range;
        in.enable_gravity = op.step.enable_gravity;
        in.gravity_mult = op.step.gravity_mult;
        in.substep_cap = op.step.substep_cap;
        for (int s = 0; s < op.step.substeps; ++s) adv->step(particles, in);
    }
}

void SimPipeline::encode(std::vector<uint8_t>& out) const {
    encode_particles(particles, out);
}
