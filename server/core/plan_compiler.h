// 执行计划编译:引擎 Graph.particle_plan() JSON → Plan;以及无粒子域
// 节点时的默认后备计划(行为与 legacy 硬编码管线一致 → 位级一致)。
#pragma once
#include <nlohmann/json.hpp>
#include <string>

#include "plan.h"
#include "boris.h"  // IntegratorConfig(后备计划参数)

namespace plancomp {

namespace detail {
// JSON null 或非字符串 → 空字符串(未绑定槽位)
inline std::string slot_str(const nlohmann::json& j, const char* key) {
    if (!j.contains(key) || !j[key].is_string()) return "";
    return j[key].get<std::string>();
}
}  // namespace detail

// 单个算子 JSON → PlanOp
inline bool op_from_json(const nlohmann::json& j, PlanOp& op, std::string& err) {
    const std::string kind = j.value("kind", "");
    op.node_id = j.value("node", "");
    op.kind = OpKind::Step;  // 重置默认
    op.emitter = EmitterOp{};
    op.step = StepOp{};
    op.encode = EncodeOp{};
    op.respawn = RespawnOp{};
    op.species = SpeciesOp{};
    op.injection = InjectionConfig{};

    if (kind == "emitter") {
        op.kind = OpKind::Emitter;
        const auto& p = j.value("params", nlohmann::json::object());
        auto& c = op.emitter.cfg;
        c.mode = p.value("mode", 0);
        c.lon_deg = p.value("lon", 0.0);
        c.lat_deg = p.value("lat", 0.0);
        c.v_base = p.value("v_base", 400.0);
        c.v_random = p.value("v_random", 10.0);
        c.angle_random = p.value("angle_random", 5.0);
        c.dist_ratio = p.value("dist_ratio", 1.0);
        c.spawn_radius_ratio = p.value("spawn_radius_ratio", 0.5);
        c.max_range = p.value("max_range", 90.0);
        c.count = p.value("count", 0);
        return true;
    }
    if (kind == "step") {
        op.kind = OpKind::Step;
        const auto& p = j.value("params", nlohmann::json::object());
        auto& s = op.step;
        s.kernel = j.value("kernel", "boris");
        s.dt = p.value("dt", 0.01);
        s.substeps = p.value("substeps", 5);
        s.max_range = p.value("max_range", 90.0);
        s.enable_gravity = p.value("enable_gravity", false);
        s.gravity_mult = p.value("gravity_mult", 1.0);
        s.substep_cap = p.value("substep_cap", 20);
        const auto& slots = j.value("slots", nlohmann::json::object());
        s.b_slot = detail::slot_str(slots, "b");
        s.e_slot = detail::slot_str(slots, "e");
        s.drag_slot = detail::slot_str(slots, "drag");
        return true;
    }
    if (kind == "encode") {
        op.kind = OpKind::Encode;
        return true;
    }
    if (kind == "respawn") {
        op.kind = OpKind::Respawn;
        return true;
    }
    if (kind == "species") {
        op.kind = OpKind::Species;
        const auto& p = j.value("params", nlohmann::json::object());
        op.species.type.q = p.value("q", 1.0);
        op.species.type.mass = p.value("mass", 1.0);
        op.species.type.v_mult = p.value("v_mult", 1.0);
        op.species.type.weight = p.value("weight", 1.0);
        std::string c = p.value("color", "#ffffff");
        if (!c.empty() && c[0] == '#') c = c.substr(1);
        int32_t col = 0xffffff;
        try {
            col = (int32_t)std::stoul(c, nullptr, 16);
        } catch (...) {
        }
        op.species.type.color = col;
        op.species.name = p.value("name", "粒子");
        op.species.enabled = p.value("enabled", true);
        return true;
    }
    if (kind == "injection") {
        op.kind = OpKind::Injection;
        const auto& p = j.value("params", nlohmann::json::object());
        auto& inj = op.injection;
        inj.enabled = true;
        inj.pos_mode = (p.value("pos_mode", std::string("rll")) == "xyz") ? 1 : 0;
        inj.r = p.value("r", 6.6);
        inj.lat_deg = p.value("lat", 0.0);
        inj.lon_deg = p.value("lon", 0.0);
        inj.x = p.value("x", 6.6);
        inj.y = p.value("y", 0.0);
        inj.z = p.value("z", 0.0);
        inj.vel_mode = (p.value("vel_mode", std::string("vpitch")) == "vxyz") ? 1 : 0;
        inj.v_kms = p.value("v", 400.0);
        inj.pitch_deg = p.value("pitch", 90.0);
        inj.phase_deg = p.value("phase", 0.0);
        inj.vx_kms = p.value("vx", 0.0);
        inj.vy_kms = p.value("vy", 0.0);
        inj.vz_kms = p.value("vz", 400.0);
        return true;
    }
    err = "未知计划算子: " + kind;
    return false;
}

// 计划 JSON → Plan(引擎权威输出;失败返回 false 并写 err)
inline bool plan_from_json(const nlohmann::json& doc, Plan& out, std::string& err) {
    Plan p;
    if (!doc.is_object() || !doc.contains("ops")) {
        err = "计划 JSON 缺少 ops 字段";
        return false;
    }
    for (const auto& j : doc["ops"]) {
        PlanOp op;
        if (!op_from_json(j, op, err)) return false;
        p.ops.push_back(std::move(op));
    }
    p.slow_path = doc.value("slow_path", false);
    // 编译期诊断(静默失败可见化:步进无 B 表 / 无编码器 / 无发射器…)
    p.warnings.clear();
    for (const auto& w : doc.value("warnings", nlohmann::json::array())) {
        PlanWarning pw;
        pw.code = w.value("code", "");
        pw.node = w.value("node", "");
        pw.port = w.value("port", "");
        pw.msg = w.value("msg", "");
        if (!pw.msg.empty()) p.warnings.push_back(std::move(pw));
    }
    out = std::move(p);
    return true;
}

// 默认后备计划(图内无粒子域节点):Emitter(事件重生)+ Step(boris)+ Encode。
// 参数与 legacy PipelineConfig 语义一致 → 默认图行为位级一致。
inline Plan make_default_plan(const EmitterConfig& emitter, int steps_per_frame,
                              const IntegratorConfig& icfg) {
    Plan p;
    {
        PlanOp op;
        op.kind = OpKind::Emitter;
        op.node_id = "__default";
        op.emitter.cfg = emitter;
        p.ops.push_back(std::move(op));
    }
    {
        PlanOp op;
        op.kind = OpKind::Step;
        op.node_id = "__default";
        op.step.kernel = "boris";
        op.step.dt = icfg.dt;
        op.step.substeps = steps_per_frame;
        op.step.max_range = icfg.max_range;
        op.step.enable_gravity = icfg.enable_gravity;
        op.step.gravity_mult = icfg.gravity_mult;
        op.step.substep_cap = icfg.substep_cap;
        op.step.b_slot = "B";
        op.step.e_slot = "E";
        op.step.drag_slot = "drag";
        p.ops.push_back(std::move(op));
    }
    {
        PlanOp op;
        op.kind = OpKind::Encode;
        op.node_id = "__default";
        p.ops.push_back(std::move(op));
    }
    return p;
}

}  // namespace plancomp
