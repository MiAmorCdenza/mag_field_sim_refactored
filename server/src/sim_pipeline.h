// 仿真管线:按执行计划(Plan)驱动 —— 发射/步进/编码全部来自粒子域子图。
// 无粒子域节点时使用默认后备计划(行为与 legacy 硬编码管线位级一致)。
#pragma once
#include <cstdint>
#include <string>
#include <vector>

#include "bake_bridge.h"
#include "../core/particles.h"
#include "../core/emitters.h"
#include "../core/boris.h"
#include "../core/advancers.h"
#include "../core/table3d.h"
#include "../core/plan.h"

struct PipelineConfig {
    int particle_count = 100;
    int steps_per_frame = 5;
    EmitterConfig emitter;
    IntegratorConfig integrator;
};

class SimPipeline {
public:
    Table3D b_table, e_table, drag_table;
    Particles particles;
    Plan plan;                 // 当前执行计划
    Emitter emitter;           // 运行时发射器(计划 EmitterOp 或后备配置)
    bool has_emitter_op = false;  // 计划含图内发射器节点(legacy WS 发射器参数被忽略)
    double max_range = 90.0;   // 当前计划最大作用半径(渲染绑定 rlim 用)

    explicit SimPipeline(const PipelineConfig& cfg);
    SimPipeline() : emitter(EmitterConfig{}) {}

    // 切换执行计划(校验内核存在;含 EmitterOp 时重建发射器)
    bool set_plan(const Plan& p, std::string& err);

    // 按槽位名安装烘焙结果(B/E/drag/gravity)
    bool install_baked(const BakedField& f, std::string& err);

    // 槽位名 → 表(无数据返回 nullptr)
    const Table3D* table_for(const std::string& slot) const;

    void respawn();          // 只重生死亡粒子(与 legacy 语义一致)
    void respawn_all();      // 全量重生(计划变更:发射器配置换了,旧位置作废)
    void reapply_species();  // 物种声明重新应用到发射器(legacy 参数路径后调用)
    void step_frame();       // 按计划 Step 算子执行(内核/子步数来自计划)
    void encode(std::vector<uint8_t>& out) const;

private:
    int32_t next_id_ = 0;
    std::vector<ParticleType> species_types_;  // 计划内启用的物种(空 = 用发射器自身类型)
};
