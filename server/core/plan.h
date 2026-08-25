// 执行计划与原生算子注册(REFACTOR_PLAN §5.7 / §"统一插件注册表")。
//
// 粒子域子图在编辑期编译为执行计划:全原生 = 每帧零 Python。
// 原生算子参数 schema 与 Python 侧描述镜像(节点编辑器中同一套参数 UI)。
#pragma once
#include <string>
#include <vector>

// 算子类别(编辑期编译的粒度)
enum class OpKind : uint8_t {
    Emitter,   // 粒子发射器(respawn 一次性)
    Step,      // Boris 积分步进(每帧热路径)
    Encode,    // 二进制编码(每帧热路径)
    Respawn,   // 状态 1/2 粒子重生(每帧)
};

struct PlanOp {
    OpKind kind;
    int target = 0;  // 缓冲/表索引(未来多缓冲用;v1 保留)
};

struct Plan {
    std::vector<PlanOp> ops;
    bool slow_path = false;  // 含 Python 算子时置位(成本徽标)
};

// 原生节点描述(与 Python 注册表镜像;参数由编辑器按 schema 渲染)
struct NativeNodeInfo {
    const char* type;
    const char* name;
    const char* category;
};

// 内置原生内核插件(逻辑固定,参数/开关/连线热,可被用户 Python 节点替换)
inline const std::vector<NativeNodeInfo>& native_builtins() {
    static const std::vector<NativeNodeInfo> builtins = {
        {"boris_integrator", "Boris 积分器", "粒子/积分"},
        {"field_sampler", "查表采样器", "粒子/采样"},
        {"particle_emitter", "粒子发射器", "粒子/来源"},
        {"output_encoder", "输出编码器", "粒子/输出"},
        {"field_tracer", "磁力线追踪", "粒子/几何"},
    };
    return builtins;
}
