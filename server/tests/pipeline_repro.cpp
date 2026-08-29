// 最小复现:SimPipeline 构造/移动赋值崩溃定位。
#include <cstdio>

#include "sim_pipeline.h"

int main() {
    PipelineConfig pc;
    pc.particle_count = 5000;
    pc.steps_per_frame = 5;
    pc.emitter.mode = 0;
    pc.emitter.v_base = 400.0;
    pc.emitter.max_range = 90.0;
    pc.emitter.types = {{1.0, 0.1, 1.0, 1.0, 0xff3333},
                        {-1.0, 0.1, 1.0, 1.0, 0x3333ff},
                        {1.0, 1.0, 1.0, 1.0, 0xff8800}};
    pc.integrator.dt = 0.01;
    pc.integrator.max_range = 90.0;

    std::printf("a) 默认构造\n");
    SimPipeline pipeline;
    std::printf("b) 默认构造完成\n");

    std::printf("c) 临时构造\n");
    SimPipeline tmp(pc);
    std::printf("d) 临时构造完成 count=%zu\n", tmp.particles.count);

    std::printf("e) 移动赋值\n");
    pipeline = std::move(tmp);
    std::printf("f) 移动赋值完成 count=%zu\n", pipeline.particles.count);

    std::printf("g) 全 OK\n");
    return 0;
}
