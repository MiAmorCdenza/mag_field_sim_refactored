// 仿真管线:烘焙表安装 + 发射/步进/编码(执行计划的当前原生形态)。
#pragma once
#include <cstdint>
#include <vector>

#include "bake_bridge.h"
#include "../core/particles.h"
#include "../core/emitters.h"
#include "../core/boris.h"
#include "../core/table3d.h"

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
    Emitter emitter;
    IntegratorConfig icfg;
    int steps_per_frame = 5;
    double max_range = 90.0;

    explicit SimPipeline(const PipelineConfig& cfg);
    SimPipeline() : emitter(EmitterConfig{}), steps_per_frame(5), max_range(90.0) {}

    // 按槽位名安装烘焙结果(B/E/drag/gravity)
    bool install_baked(const BakedField& f, std::string& err);

    void respawn();

    void step_frame();  // steps_per_frame × step_parallel

    void encode(std::vector<uint8_t>& out) const;

private:
    int32_t next_id_ = 0;
};
