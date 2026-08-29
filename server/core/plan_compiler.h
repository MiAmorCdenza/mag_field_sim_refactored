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
