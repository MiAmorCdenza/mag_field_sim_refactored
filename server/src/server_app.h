// WebSocket 服务层:Crow 应用 + 烘焙线程(latest-wins)+ 仿真线程 + 广播。
//
// 协议(v1,与旧前端二进制帧格式兼容,便于过渡):
//   客户端 → 服务端(文本 JSON):
//     graph.upload       {graph:{...}}            上传新图 → 重烘焙
//     node.param         {node,name,value}        改参数 → 重烘焙
//     set_particle_count {value}                  粒子数
//     set_emitter_params {...}                    发射器参数
//     respawn                                     重置全部粒子
//   服务端 → 客户端:
//     文本: init_config {graph, particles, ...}
//     文本: bake_progress {slot, seq, state, note}
//     文本: graph.error {message}
//     二进制: [u32 头长][头 JSON {"type":"s","n":..,"k":..,"v":..,"seq":..}][21B×N]
#pragma once
#include <cstdint>
#include <map>
#include <string>
#include <vector>

struct ServerConfig {
    std::string root = ".";
    std::string graph_path;                 // 初始图(空 = 内置默认)
    std::string host = "0.0.0.0";
    int port = 8001;
    int fps = 60;
    int network_fps = 30;
    int steps_per_frame = 5;
    int particle_count = 100;
};

class ServerApp {
public:
    int run(const ServerConfig& cfg);

private:
    struct Impl;
};
