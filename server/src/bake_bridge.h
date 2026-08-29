// 内嵌 Python 桥:C++ 服务器 ↔ 节点引擎(图加载/参数/烘焙)。
//
// 职责边界(REFACTOR_PLAN):Python 只管烘焙(离线秒级),C++ 热路径零 Python。
// 烘焙在专用线程执行(GIL 由该线程持有),仿真线程只消费烘焙产物。
#pragma once
#include <cstdint>
#include <memory>
#include <optional>
#include <string>
#include <vector>

// 烘焙结果(六列表,与 engine.Graph.bake() 输出一致)
struct BakedField {
    std::string slot;
    bool is_vector = true;              // false = 标量场(阻力系数)
    std::vector<double> xs, ys, zs;
    std::vector<double> c0, c1, c2;     // bx/by/bz 或 scalar→c0
};

class BakeBridge {
public:
    BakeBridge();
    ~BakeBridge();

    // 初始化解释器(需在程序早期调用一次);root = 仓库根(engine/nodes 所在)
    bool init(const std::string& root, std::string& err);

    // 释放主线程持有的 GIL(必须:scoped_interpreter 创建后主线程持续持 GIL,
    // 不释放则烘焙线程的 gil_scoped_acquire 将永久阻塞)
    bool release_main_thread();

    // 加载图 JSON(替换当前图;失败保留上次可用图并返回 false)
    bool load_graph(const std::string& json, std::string& err);

    // 设置节点参数(输入端口参数或 params);成功 → 图版本 +1
    bool set_param(const std::string& node, const std::string& name,
                   double value, std::string& err);

    // 通用值版本(JSON 标量:数字/布尔/枚举字符串)
    bool set_param_value(const std::string& node, const std::string& name,
                         const std::string& json_value, std::string& err);

    uint64_t graph_version();

    // 求值并烘焙单个命名输出槽位(B/E/drag/...)
    std::optional<BakedField> bake(const std::string& slot, std::string& err);

    // 节点类型描述(前端编辑器面板):JSON 数组
    bool describe_types(std::string& out_json, std::string& err);

    // 图中声明的输出槽位(含 output_slot 节点自动推导)
    bool declared_outputs(std::vector<std::string>& slots, std::string& err);

    // 当前图序列化(引擎权威快照,含自动推导的输出声明)
    bool graph_json(std::string& out_json, std::string& err);

    // 渲染域绑定表(渲染节点 → 上游数据契约)
    bool render_bindings(std::string& out_json, std::string& err);

    // 粒子域执行计划(粒子子图 → C++ Plan;L1 图驱动管线)
    bool particle_plan(std::string& out_json, std::string& err);

    // 重新扫描插件目录(热加载新节点:丢文件即注册)
    bool rescan(std::string& err);

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};
