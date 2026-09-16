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
    warnings_ = p.warnings;   // 编译期诊断(含 step_no_b / no_encoder …)
    // 积分器实际使用的磁场槽位(#41):多场并存时粒子只走这一张表
    step_b_slot_ = "B";
    for (const auto& op0 : plan.ops) {
        if (op0.kind == OpKind::Step && !op0.step.b_slot.empty()) {
            step_b_slot_ = op0.step.b_slot;
            break;
        }
    }
    has_encoder_ = false;
    has_step_op_ = false;
    has_respawn_ = false;          // ⚠ 必须复位:否则旧计划的标记会残留
    dead_ratio_ = 0.0;
    runtime_decay_warned_ = false;  // (warnings_ 已在上面整体重建)
    for (const auto& op : plan.ops) {
        if (op.kind == OpKind::Encode) has_encoder_ = true;
        if (op.kind == OpKind::Step) has_step_op_ = true;
        if (op.kind == OpKind::Respawn) has_respawn_ = true;   // 持续创生(#35)
    }
    for (const auto& op : plan.ops) {
        if (op.kind == OpKind::Step && op.step.max_range > max_range)
            max_range = op.step.max_range;
    }
    // 物种聚合:图中声明式 particle_species 节点 → 发射器类型列表
    // (一个节点 = 一个物种;enabled=false 不参与生成)
    // ⚠ 这里是**图级**聚合:计划里所有 Species 算子都算数,与画布上是否
    // 链式接线无关(实测:未接线的物种节点照样参与生成)。UI 读数直接取
    // 本结果(population_),不再让用户去猜接线语义。
    species_types_.clear();
    population_.clear();
    population_weight_ = 0.0;
    for (const auto& op : plan.ops) {
        if (op.kind != OpKind::Species || !op.species.enabled) continue;
        species_types_.push_back(op.species.type);
        PopulationEntry e;
        e.name = op.species.name.empty() ? op.node_id : op.species.name;
        e.q = op.species.type.q;
        e.mass = op.species.type.mass;
        e.v_mult = op.species.type.v_mult;
        e.weight = op.species.type.weight;
        e.color = op.species.type.color;
        population_weight_ += e.weight;
        population_.push_back(std::move(e));
    }
    for (auto& e : population_)
        e.share = (population_weight_ > 1e-12) ? e.weight / population_weight_ : 0.0;
    // 图内发射器节点(node_id != "__default")→ 重建发射器并接管;
    // 后备计划的发射器保持由服务器 st.emitter 驱动(legacy 兼容)
    has_emitter_op = false;
    plan_count_ = 0;
    std::string wired_init;   // 发射器 init 输入接的注入节点(空 = 未接线)
    for (const auto& op : plan.ops) {
        if (op.kind != OpKind::Emitter) continue;
        EmitterConfig ecfg = op.emitter.cfg;
        if (!species_types_.empty()) ecfg.types = species_types_;  // 物种节点优先
        plan_count_ = ecfg.count;                                  // 图内粒子数覆盖
        wired_init = op.emitter.init_node;
        emitter = Emitter(ecfg);
        if (op.node_id != "__default") has_emitter_op = true;
        break;  // 首个 EmitterOp 生效(v1)
    }
    // 单粒子注入:**接线决定归属**(#30)——只有发射器 init 实际接到的那个
    // 注入节点生效(以前只要图里有注入节点就生效,画布在骗人)
    has_injection_ = false;
    for (const auto& op : plan.ops) {
        if (op.kind != OpKind::Injection || !op.injection.enabled) continue;
        if (wired_init.empty() || op.node_id != wired_init) continue;
        emitter.set_injection(op.injection);
        has_injection_ = true;
        if (plan_count_ <= 0) plan_count_ = 1;  // 单粒子默认 1
        break;
    }
    // 俯仰角模式需要局部 B:绑定本管线的 B 表(spawn 时实时采样)
    emitter.set_field(&b_table());   // 指向积分器实际使用的磁场槽位
    // 注入 + count>1 = 所有粒子初条件完全相同(确定性 mode 3 零随机扰动)
    // → N 个粒子精确重合,视觉上仍是 1 个(用户实测踩到过)。此处只标记,
    // 由上层写日志/广播 plan_status 告警。
    degenerate_injection_ = has_injection_ && plan_count_ > 1;
    if (degenerate_injection_) {
        warnings_.push_back(PlanWarning{
            "degenerate_injection", "", "",
            "注入节点生效且 count>1:所有粒子初条件相同(完全重合);"
            "要撒多粒子请删除注入节点后重新应用图"});
    }
    if (!has_respawn_ && plan_count_ > 0) {
        // 一次性播撒:粒子死亡后不会重生,种群会衰减 —— 提前说清(运行期
        // 死伤过半还会再报一次 population_decaying)
        warnings_.push_back(PlanWarning{
            "respawn_off", "", "",
            "发射器关闭了「持续创生」:粒子沉降/越界后不会重生,种群会逐渐衰减"
            "(想要稳态种群请打开 respawn)"});
    }
    return true;
}

void SimPipeline::reapply_species() {
    if (!species_types_.empty()) emitter.set_types(species_types_);
}

bool SimPipeline::install_baked(const BakedField& f, std::string& err) {
    Table3D* t = nullptr;
    bool scale_to_normalized = false;
        // 多场槽位(#41):任意槽位名都建表(以前只认 B/E/drag/gravity,第二个磁场
    // 会被直接丢掉)。命名以 "B" 开头视为磁场 → nT 转归一化单位;
    // 其它槽位按"已输出归一化/无量纲量"处理(沿用旧约定)。
    if (f.slot.empty()) { err = "槽位名为空"; return false; }
    t = &tables_[f.slot];
    scale_to_normalized = (f.slot.rfind("B", 0) == 0);

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
        auto it = tables_.find(slot);
    if (it != tables_.end() && it->second.has_data()) return &it->second;
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
        for (int s = 0; s < op.step.substeps; ++s) {
            adv->step(particles, in);
            sim_time_ += op.step.dt;   // 名义推进(内核内部细分不减总时长)
        }
    }
    // 持续创生(#35):计划含 respawn 算子 → 逐帧重生死亡粒子(沉降 status=1 /
    // 越界 status=2),种群维持稳态。放在所有步进之后,与算子 order 无关。
    if (has_respawn_) {
        respawn();
        dead_ratio_ = 0.0;
    } else if (particles.count > 0) {
        // 没有重生算子:统计死亡率,供 population_decaying 告警(否则用户只会
        // 看到粒子一个个消失却不知道为什么)
        size_t dead = 0;
        for (size_t i = 0; i < particles.count; ++i) {
            const int s = particles.status[i];
            if (s == 1 || s == 2 || particles.id[i] == 0) ++dead;
        }
        dead_ratio_ = static_cast<double>(dead) /
                      static_cast<double>(particles.count);
    }
}

// L2 单粒子初条件预览:与发射器生成路径共用 injection_position /
// injection_velocity(同一套数学,不会预览/实际漂移)。
SourcePreview SimPipeline::source_preview() const {
    SourcePreview sp;
    if (!has_injection_) return sp;
    const InjectionConfig& inj = emitter.injection();
    sp.pos_mode = inj.pos_mode;
    sp.vel_mode = inj.vel_mode;
    sp.pos = injection_position(inj);
    sp.pitch_deg = inj.pitch_deg;
    sp.phase_deg = inj.phase_deg;

    // 物种:与生成路径一致取链首(确定性,不参与加权随机)
    static const ParticleType kFallback{};
    const ParticleType* pt = nullptr;
    if (!species_types_.empty()) pt = &species_types_.front();
    else if (!emitter.types().empty()) pt = &emitter.types().front();
    if (!pt) pt = &kFallback;
    sp.q_over_m = (pt->mass > 1e-12) ? std::abs(pt->q / pt->mass) : 1.0;

    // 局部 B(表内为归一化单位;越界钳制 → 显式提示"点在表域外")
    Vec3 b(0, 0, 0);
    bool outside = false;
    if (inj.vel_mode != 1 && b_table().has_data()) {
        b_table().sample(sp.pos.x, sp.pos.y, sp.pos.z, b.x, b.y, b.z);
        const double eps = 1e-9;
        outside = sp.pos.x < b_table().xs.front() - eps || sp.pos.x > b_table().xs.back() + eps ||
                  sp.pos.y < b_table().ys.front() - eps || sp.pos.y > b_table().ys.back() + eps ||
                  sp.pos.z < b_table().zs.front() - eps || sp.pos.z > b_table().zs.back() + eps;
    }
    bool has_b = false;
    sp.v_dir = injection_velocity(inj, b, has_b, sp.v_kms);
    sp.has_b = has_b;

    // 生成路径的两处钳制(emitters.h spawn):预览必须反映实际生效值,
    // 否则读数与屏幕上真实出现的粒子不符。
    const double c_speed = 299792.458 / 6371.0;
    if (sp.v_kms / 6371.0 >= c_speed) {
        sp.v_kms = c_speed * 0.999999 * 6371.0;
        sp.note = "速率 ≥ c:已钳制到 0.999999c";
    }
    double rn = sp.pos.norm();
    if (rn < 1.05) {
        sp.pos = (rn > 1e-6) ? sp.pos * (1.05 / rn) : Vec3(1.05, 0, 0);
        if (!sp.note.empty()) sp.note += ";";
        sp.note += "注入点 < 1.05 Re:发射器抬升至 1.05 Re";
    }

    double bm = b.norm();
    if (bm > 1e-12) sp.b_dir = b * (1.0 / bm);
    sp.b_nt = bm * B_NT_PER_CODE;

    // 回旋半径/周期:直接用积分器常数(q_prime = |q/m|·2988.5959 每表单位)
    const double wc = sp.q_over_m * Q_PRIME_PER_B * bm;   // rad/s
    if (wc > 1e-12) {
        double v_re_s = sp.v_kms / 6371.0;               // Re/s
        sp.r_g_re = v_re_s / wc;
        sp.gyro_s = 2.0 * M_PI / wc;
    }
    if (sp.note.empty()) {                               // 无钳制时才写常规提示
        if (inj.vel_mode == 1) {
            sp.note = "vxyz:方向直接给定(不依赖 B)";
        } else if (!b_table().has_data()) {
            sp.note = "B 表未烘焙:方向回退 z 轴";
        } else if (outside) {
            sp.note = "注入点在 B 表域外(采样被钳制)";
        } else if (!has_b) {
            sp.note = "局部 B≈0:方向回退 z 轴";
        }
    }
    sp.valid = true;
    return sp;
}

void SimPipeline::encode(std::vector<uint8_t>& out) const {
    encode_particles(particles, out);
}
