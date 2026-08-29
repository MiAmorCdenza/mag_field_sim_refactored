// 执行计划(REFACTOR_PLAN §5.7):粒子域子图在编辑期编译为 Plan,
// SimPipeline 每帧按 Plan 执行 —— 换步进器 = 图上换节点(L1)。
//
// 编译链:图 JSON → 引擎 Graph.particle_plan() → plan_compiler.h(JSON→Plan)
// → SimPipeline::set_plan。无粒子域节点时使用默认后备计划(与 legacy
// 硬编码管线位级一致)。全原生计划 = 每帧零 Python;slow_path 标志保留
// 给未来 Python 算子(成本徽标)。
#pragma once
#include <cstdint>
#include <string>
#include <vector>

#include "emitters.h"

// 算子类别(编辑期编译的粒度)
enum class OpKind : uint8_t {
    Emitter,   // 粒子发射(重生事件时执行;v1 参数镜像 EmitterConfig)
    Step,      // 批次推进(每帧热路径;内核选择/子步数来自节点参数)
    Encode,    // 二进制编码(网络帧;21 字节/粒子)
    Respawn,   // 预留:状态 1/2 粒子逐帧重生(v1 未启用,legacy 语义 = 事件重生)
    Species,   // 粒子物种声明(particle_species 节点 → 聚合进发射器类型列表)
};

struct EmitterOp {
    EmitterConfig cfg;
};

struct StepOp {
    std::string kernel = "boris";  // 内核注册表键(advancers.h)
    double dt = 0.01;
    int substeps = 5;              // 每帧子步数(节点参数)
    double max_range = 90.0;
    bool enable_gravity = false;
    double gravity_mult = 1.0;
    int substep_cap = 20;
    std::string b_slot, e_slot, drag_slot;  // 场槽位绑定("" = 未绑定)
};

struct EncodeOp {};
struct RespawnOp {};

// 物种算子参数(对应老版 particle_types 的 name/q/m/v_mult/weight/color/checked)
struct SpeciesOp {
    ParticleType type;
    std::string name;
    bool enabled = true;
};

struct PlanOp {
    OpKind kind = OpKind::Step;
    std::string node_id;
    EmitterOp emitter;
    StepOp step;
    EncodeOp encode;
    RespawnOp respawn;
    SpeciesOp species;
};

struct Plan {
    std::vector<PlanOp> ops;
    bool slow_path = false;  // 含未编译粒子域节点时置位(成本徽标)
};

// 原生节点描述(与 Python 侧 nodes/particle_nodes.py 声明桩镜像;
// 参数由编辑器按 schema 渲染,见 engine.registry.describe())
struct NativeNodeInfo {
    const char* type;
    const char* name;
    const char* category;
};

// 内置原生内核节点(L1:发射/步进/编码;内核实现在 advancers.h 注册)
inline const std::vector<NativeNodeInfo>& native_builtins() {
    static const std::vector<NativeNodeInfo> builtins = {
        {"particle_emitter", "粒子发射器", "粒子/来源"},
        {"boris_integrator", "Boris 积分器", "粒子/积分"},
        {"leapfrog_integrator", "蛙跳积分器", "粒子/积分"},
        {"rk4_integrator", "RK4 积分器", "粒子/积分"},
        {"verlet_integrator", "速度 Verlet 积分器", "粒子/积分"},
        {"output_encoder", "输出编码器", "粒子/输出"},
    };
    return builtins;
}
