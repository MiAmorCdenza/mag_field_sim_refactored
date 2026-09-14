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

// L2 单粒子初条件预览(服务器算,含需要场表的局部 B)。
// 位置/方向为 GSM;标量按积分器自身单位换算(非独立 SI 估算):
//   B_nT   = |B_code| · 31200                 (nodes/efield.py 同一常数)
//   ω_c    = |q/m| · 2988.5959 · |B_code|     (boris.h q_prime 同一常数)
//   R_g    = (v_kms/6371) / ω_c   [Re]
//   回旋周期 = 2π / ω_c            [s]
struct SourcePreview {
    bool valid = false;
    bool has_b = false;          // 局部 B 可用(否则速度方向回退 z 轴)
    Vec3 pos;                    // GSM / Re
    Vec3 b_dir;                  // b̂(表单位方向,仅方向有意义)
    Vec3 v_dir;                  // 速度方向单位矢量(GSM)
    double b_nt = 0.0;           // |B| (nT)
    double v_kms = 0.0;          // 速率 (km/s)
    double r_g_re = 0.0;         // 回旋半径 (Re)
    double gyro_s = 0.0;         // 回旋周期 (s)
    double pitch_deg = 0.0, phase_deg = 0.0;
    double q_over_m = 1.0;       // 物种 q/m(归一化)
    int pos_mode = 0, vel_mode = 0;
    std::string note;            // 诊断文本(表外/B≈0 等)
};

class SimPipeline {
public:
    Table3D b_table, e_table, drag_table;
    Particles particles;
    Plan plan;                 // 当前执行计划
    Emitter emitter;           // 运行时发射器(计划 EmitterOp 或后备配置)
    bool has_emitter_op = false;  // 计划含图内发射器节点(legacy WS 发射器参数被忽略)
    bool has_injection_ = false;  // 计划含单粒子注入(确定性 mode 3)
    double max_range = 90.0;   // 当前计划最大作用半径(渲染绑定 rlim 用)

    explicit SimPipeline(const PipelineConfig& cfg);
    SimPipeline() : emitter(EmitterConfig{}) {}

    // 切换执行计划(校验内核存在;含 EmitterOp 时重建发射器)
    bool set_plan(const Plan& p, std::string& err);

    // 图内粒子数覆盖(0 = 沿用全局 --particles / UI 设置)
    int plan_particle_count() const { return plan_count_; }
    bool has_injection() const { return has_injection_; }
    // 注入生效且数量 >1:所有粒子初条件相同 → 完全重合(仅告警,不改变行为)
    bool degenerate_injection() const { return degenerate_injection_; }

    // 解析后的真实种群(聚合结果;供 UI 读数 —— 画布上的链/接线只是表达,
    // 实际生效的是这个列表)
    struct PopulationEntry {
        std::string name;
        double q = 0.0, mass = 1.0, v_mult = 1.0, weight = 0.0;
        int32_t color = 0xffffff;
        double share = 0.0;   // 生成占比 = weight / Σweight
    };
    const std::vector<PopulationEntry>& population() const { return population_; }
    double population_weight() const { return population_weight_; }

    // 单粒子初条件预览(无注入节点 / 无 B 表 → valid=false)
    SourcePreview source_preview() const;

    // 仿真时间(名义步进累积:每子步加 op.step.dt)。
    // 只在换图(reset_sim_time)归零:调参重编译计划不重置,便于观察连续演化。
    double sim_time() const { return sim_time_; }
    void reset_sim_time() { sim_time_ = 0.0; }

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
    int plan_count_ = 0;                       // 图内粒子数(0 = 无覆盖)
    bool degenerate_injection_ = false;        // 注入 + count>1 → 粒子全重合
    std::vector<PopulationEntry> population_;  // 解析后的种群(UI 读数)
    double population_weight_ = 0.0;           // Σweight
    double sim_time_ = 0.0;                    // 仿真时间累积(s)
};
