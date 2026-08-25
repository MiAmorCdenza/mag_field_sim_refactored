// WebSocket 服务层实现。
#include "server_app.h"

#include <chrono>
#include <condition_variable>
#include <fstream>
#include <iostream>
#include <mutex>
#include <optional>
#include <sstream>
#include <thread>
#include <unordered_set>

#include "crow.h"
#include <nlohmann/json.hpp>

#include "bake_bridge.h"
#include "sim_pipeline.h"
#include "encoder.h"

using json = nlohmann::json;

namespace {

// ---- 烘焙队列(latest-wins,seq 过期) ----
struct BakeJob {
    uint64_t seq = 0;
    std::vector<std::string> slots;
    std::string graph_json;  // 触发本次烘焙的图快照
};

struct SharedState {
    std::mutex m;
    std::string graph_json;            // 当前图
    std::vector<std::string> slots;    // 声明输出槽
    bool request_pending = false;
    bool active = false;
    uint64_t seq = 0;
    BakeJob latest;
    std::optional<std::map<std::string, BakedField>> completed;  // 按 seq
    uint64_t completed_seq = 0;
    bool respawn_flag = false;
    bool emitter_dirty = false;
    int particle_count = 100;
    uint64_t graph_version = 0;      // 由 WS 线程/主线程维护,仿真线程只读
    EmitterConfig emitter;
    std::string bake_error;
    bool bake_failed = false;
    uint64_t bake_failed_seq = 0;
    bool running = true;
};

std::string read_file(const std::string& path) {
    std::ifstream f(path, std::ios::binary);
    std::ostringstream ss;
    ss << f.rdbuf();
    return ss.str();
}

std::string default_graph_json() {
    return R"JSON({
  "version": 1,
  "lattice": {"preset": "tiny"},
  "nodes": [
    {"id": "kp", "type": "kp_source", "params": {"kp": 2.0}},
    {"id": "day", "type": "day_source", "params": {"day": 172.0}},
    {"id": "t89", "type": "t89", "input_defaults": {"kp": 2.0, "ps": 0.5}},
    {"id": "tail", "type": "tail", "params": {"model": "flaring"}, "input_defaults": {"kp": 2.0, "ps": 0.5}},
    {"id": "dipole", "type": "dipole", "input_defaults": {"ps": 0.5}},
    {"id": "imf", "type": "imf_source", "params": {"polarity": -1, "parker_custom": true, "parker_angle": 40.0}, "input_defaults": {"kp": 2.0}},
    {"id": "internal", "type": "internal_blend", "input_defaults": {"kp": 2.0, "ps": 0.5}},
    {"id": "mp", "type": "magnetopause", "params": {"mp_model": 2}, "input_defaults": {"kp": 2.0, "ps": 0.5}},
    {"id": "efield", "type": "convection_corotation", "params": {"multiplier": 1.0}},
    {"id": "drag", "type": "drag_layered", "params": {"multiplier": 1.0}}
  ],
  "edges": [
    {"from": ["kp", "kp"], "to": ["t89", "kp"]},
    {"from": ["kp", "kp"], "to": ["tail", "kp"]},
    {"from": ["kp", "kp"], "to": ["imf", "kp"]},
    {"from": ["day", "ps"], "to": ["t89", "ps"]},
    {"from": ["day", "ps"], "to": ["tail", "ps"]},
    {"from": ["day", "ps"], "to": ["dipole", "ps"]},
    {"from": ["t89", "field"], "to": ["internal", "base"]},
    {"from": ["tail", "field"], "to": ["internal", "tail"]},
    {"from": ["internal", "field"], "to": ["mp", "internal"]},
    {"from": ["dipole", "field"], "to": ["mp", "dipole"]},
    {"from": ["imf", "field"], "to": ["mp", "imf"]},
    {"from": ["mp", "field"], "to": ["efield", "b"]}
  ],
  "outputs": {"B": ["mp", "field"], "E": ["efield", "field"], "drag": ["drag", "coef"]}
})JSON";
}

}  // namespace

struct ServerApp::Impl {
    ServerConfig cfg;
    BakeBridge bridge;
    std::mutex bridge_m;
    SharedState st;
    std::condition_variable bake_cv;

    // Crow 连接
    std::mutex conn_m;
    std::unordered_set<crow::websocket::connection*> conns;

    SimPipeline pipeline;

    void broadcast_text(const std::string& s) {
        std::lock_guard<std::mutex> g(conn_m);
        for (auto* c : conns) c->send_text(s);
    }
    void broadcast_bin(const std::string& s) {
        std::lock_guard<std::mutex> g(conn_m);
        for (auto* c : conns) c->send_binary(s);
    }
    void broadcast_progress(uint64_t seq, const std::string& state,
                            const std::string& note = "") {
        json j{{"type", "bake_progress"}, {"seq", seq}, {"state", state}};
        if (!note.empty()) j["note"] = note;
        broadcast_text(j.dump());
    }

    // 提交烘焙请求(latest-wins)
    void submit_bake() {
        std::lock_guard<std::mutex> g(st.m);
        st.latest.seq = ++st.seq;
        st.latest.slots = st.slots;
        st.latest.graph_json = st.graph_json;
        st.request_pending = true;
        broadcast_progress(st.latest.seq, "queued");
        bake_cv.notify_one();
    }

    void bake_worker() {
        try {
        while (true) {
            BakeJob job;
            {
                std::unique_lock<std::mutex> lock(st.m);
                bake_cv.wait(lock, [&] { return st.request_pending || !st.running; });
                if (!st.running && !st.request_pending) break;
                job = st.latest;
                st.request_pending = false;
                st.active = true;
            }
            broadcast_progress(job.seq, "computing");

            std::map<std::string, BakedField> fields;
            std::string err;
            bool ok = true;
            {
                std::lock_guard<std::mutex> g(bridge_m);
                for (const auto& slot : job.slots) {
                    auto f = bridge.bake(slot, err);
                    if (!f) { ok = false; break; }
                    fields[slot] = std::move(*f);
                }
            }

            bool stale = false;
            {
                std::lock_guard<std::mutex> g(st.m);
                st.active = false;
                stale = st.seq != job.seq;
                if (!stale) {
                    if (ok) {
                        st.completed = std::move(fields);
                        st.completed_seq = job.seq;
                    } else {
                        st.bake_failed = true;
                        st.bake_failed_seq = job.seq;
                        st.bake_error = err;
                    }
                }
            }
            if (stale) {
                broadcast_progress(job.seq, "superseded");
                std::cout << "[bake] 丢弃过期结果 seq=" << job.seq << std::endl;
            }
        }
        } catch (const std::exception& e) {
            std::cerr << "[bake] EXCEPTION: " << e.what() << std::endl;
        } catch (...) {
            std::cerr << "[bake] UNKNOWN EXCEPTION" << std::endl;
        }
    }

    void sim_loop() {
        try {
        auto next_frame = std::chrono::steady_clock::now();
        auto frame_dt = std::chrono::milliseconds(1000 / std::max(1, cfg.fps));
        int frame_count = 0;
        int interval = std::max(1, cfg.fps / std::max(1, cfg.network_fps));

        while (st.running) {
            auto frame_start = std::chrono::steady_clock::now();

            // 1) 应用完成的烘焙结果
            {
                std::optional<std::map<std::string, BakedField>> done;
                bool failed = false;
                uint64_t fseq = 0;
                std::string ferr;
                {
                    std::lock_guard<std::mutex> g(st.m);
                    if (st.completed) { done = std::move(st.completed); st.completed.reset(); }
                    if (st.bake_failed) { failed = true; fseq = st.bake_failed_seq; ferr = st.bake_error; st.bake_failed = false; }
                }
                if (done) {
                    std::string err;
                    for (auto& [slot, field] : *done) pipeline.install_baked(field, err);
                    broadcast_progress(st.completed_seq, "done");
                    std::cout << "[bake] 已应用 seq=" << st.completed_seq
                              << " slots=" << done->size() << std::endl;
                }
                if (failed) {
                    broadcast_progress(fseq, "error", ferr);
                    std::cout << "[bake] 失败 seq=" << fseq << ": " << ferr << std::endl;
                }
            }

            // 2) 粒子数/发射器/respawn 变更
            {
                bool respawn = false;
                bool rebuild_emitter = false;
                {
                    std::lock_guard<std::mutex> g(st.m);
                    respawn = st.respawn_flag;
                    st.respawn_flag = false;
                    rebuild_emitter = st.emitter_dirty;
                    st.emitter_dirty = false;
                    if (pipeline.particles.count != (size_t)st.particle_count) {
                        pipeline.particles.resize((size_t)st.particle_count);
                        respawn = true;
                    }
                    if (rebuild_emitter) {
                        pipeline.emitter = Emitter(st.emitter);
                        respawn = true;
                    }
                }
                if (respawn) pipeline.respawn();
            }

            // 3) 物理步进(首次烘焙完成前不积分:空表步进无物理意义)
            if (pipeline.b_table.has_data()) pipeline.step_frame();

            // 4) 广播(网络帧率)——仿真线程零 Python(红线)
            if (frame_count % interval == 0) {
                std::vector<uint8_t> body;
                pipeline.encode(body);
                uint64_t ver = 0;
                {
                    std::lock_guard<std::mutex> g(st.m);
                    ver = st.graph_version;
                }
                json header{{"type", "s"}, {"n", body.size() / 21}, {"v", ver}};
                std::string hs = header.dump();
                uint32_t hlen = (uint32_t)hs.size();
                std::string packet;
                packet.reserve(4 + hs.size() + body.size());
                packet.append((const char*)&hlen, 4);
                packet.append(hs);
                packet.append((const char*)body.data(), body.size());
                broadcast_bin(packet);
            }

            ++frame_count;
            next_frame = frame_start + frame_dt;
            std::this_thread::sleep_until(next_frame);
        }
        } catch (const std::exception& e) {
            std::cerr << "[sim] EXCEPTION: " << e.what() << std::endl;
        } catch (...) {
            std::cerr << "[sim] UNKNOWN EXCEPTION" << std::endl;
        }
    }

    int run() {
        std::cout << "🚀 mf_server: 动态节点仿真服务器" << std::endl;

        // Python 引擎
        std::string err;
        if (!bridge.init(cfg.root, err)) {
            std::cerr << "❌ 引擎初始化失败: " << err << std::endl;
            return 1;
        }
        std::cout << "✅ Python 引擎就绪" << std::endl;

        // 初始图
        st.graph_json = cfg.graph_path.empty() ? default_graph_json()
                                               : read_file(cfg.graph_path);
        {
            std::lock_guard<std::mutex> g(bridge_m);
            if (!bridge.load_graph(st.graph_json, err)) {
                std::cerr << "❌ 初始图加载失败: " << err << std::endl;
                return 1;
            }
            st.graph_version = bridge.graph_version();
        }
        // 提取声明槽
        auto doc = json::parse(st.graph_json);
        for (auto& [k, v] : doc["outputs"].items()) st.slots.push_back(k);
        std::cout << "✅ 初始图加载,槽位: ";
        for (auto& s : st.slots) std::cout << s << " ";
        std::cout << std::endl;

        // 主线程释放 GIL(必须,见 BakeBridge::release_main_thread 注释)
        if (!bridge.release_main_thread())
            std::cerr << "⚠️ 主线程 GIL 释放失败" << std::endl;

        // 管线
        PipelineConfig pc;
        pc.particle_count = cfg.particle_count;
        pc.steps_per_frame = cfg.steps_per_frame;
        pc.emitter = st.emitter;
        pc.integrator.dt = 0.01;
        pc.integrator.max_range = 90.0;
        pipeline = SimPipeline(pc);

        // 线程
        std::thread baker([this] { bake_worker(); });
        std::thread sim([this] { sim_loop(); });

        submit_bake();

        // Crow
        crow::SimpleApp app;
        CROW_WEBSOCKET_ROUTE(app, "/ws")
            .onopen([this](crow::websocket::connection& conn) {
                std::lock_guard<std::mutex> g(conn_m);
                conns.insert(&conn);
                uint64_t ver = 0;
                {
                    std::lock_guard<std::mutex> g2(st.m);
                    ver = st.graph_version;
                }
                json init{{"type", "init_config"},
                          {"graph", json::parse(st.graph_json)},
                          {"particles", st.particle_count},
                          {"version", ver}};
                conn.send_text(init.dump());
                std::cout << "[ws] 连接建立" << std::endl;
            })
            .onclose([this](crow::websocket::connection& conn, const std::string&) {
                std::lock_guard<std::mutex> g(conn_m);
                conns.erase(&conn);
                std::cout << "[ws] 连接关闭" << std::endl;
            })
            .onmessage([this](crow::websocket::connection& conn,
                              const std::string& data, bool is_binary) {
                if (is_binary) return;
                try {
                    auto msg = json::parse(data);
                    std::string type = msg.value("type", "");
                    if (type == "graph.upload") {
                        std::string gjson = msg["graph"].dump();
                        bool ok = false;
                        std::string err;
                        std::vector<std::string> slots;
                        uint64_t ver = 0;
                        {
                            std::lock_guard<std::mutex> g(bridge_m);
                            ok = bridge.load_graph(gjson, err);
                            if (ok) ver = bridge.graph_version();
                        }
                        if (ok) {
                            for (auto& [k, v] : msg["graph"]["outputs"].items())
                                slots.push_back(k);
                            {
                                std::lock_guard<std::mutex> g(st.m);
                                st.graph_json = gjson;
                                st.slots = slots;
                                st.graph_version = ver;
                            }
                            submit_bake();  // 在 st.m 锁外提交(submit_bake 内部会再锁 st.m)
                        } else {
                            json e{{"type", "graph.error"}, {"message", err}};
                            conn.send_text(e.dump());
                        }
                    } else if (type == "node.param") {
                        bool ok = false;
                        std::string err;
                        uint64_t ver = 0;
                        {
                            std::lock_guard<std::mutex> g(bridge_m);
                            ok = bridge.set_param(msg["node"], msg["name"],
                                                  msg["value"].get<double>(), err);
                            if (ok) ver = bridge.graph_version();
                        }
                        if (ok) {
                            {
                                std::lock_guard<std::mutex> g(st.m);
                                st.graph_version = ver;
                            }
                            submit_bake();
                        } else {
                            json e{{"type", "graph.error"}, {"message", err}};
                            conn.send_text(e.dump());
                        }
                    } else if (type == "set_particle_count") {
                        std::lock_guard<std::mutex> g(st.m);
                        st.particle_count = std::max(1, msg["value"].get<int>());
                    } else if (type == "set_emitter_params") {
                        std::lock_guard<std::mutex> g(st.m);
                        st.emitter.mode = msg.value("mode", 0);
                        st.emitter.lon_deg = msg.value("lon", 0.0);
                        st.emitter.lat_deg = msg.value("lat", 0.0);
                        st.emitter.v_base = msg.value("v_base", 400.0);
                        st.emitter.v_random = msg.value("v_random", 10.0);
                        st.emitter.angle_random = msg.value("angle_random", 5.0);
                        st.emitter.dist_ratio = msg.value("dist_ratio", 1.0);
                        st.emitter_dirty = true;
                    } else if (type == "respawn") {
                        std::lock_guard<std::mutex> g(st.m);
                        st.respawn_flag = true;
                    }
                } catch (const std::exception& e) {
                    std::cerr << "[ws] 消息处理失败: " << e.what() << std::endl;
                }
            });

        CROW_ROUTE(app, "/")([this]() {
            std::ifstream f(cfg.root + "/static/index.html");
            std::ostringstream ss;
            ss << f.rdbuf();
            return crow::response(ss.str());
        });
        CROW_ROUTE(app, "/<path>")([this](std::string path) {
            std::ifstream f(cfg.root + "/static/" + path);
            std::ostringstream ss;
            ss << f.rdbuf();
            return crow::response(ss.str());
        });

        std::cout << "✅ 服务启动: http://" << cfg.host << ":" << cfg.port
                  << " (ws://.../ws)" << std::endl;
        app.bindaddr(cfg.host).port(cfg.port).run();

        // 关闭
        {
            std::lock_guard<std::mutex> g(st.m);
            st.running = false;
        }
        bake_cv.notify_all();
        if (baker.joinable()) baker.join();
        if (sim.joinable()) sim.join();
        return 0;
    }
};

int ServerApp::run(const ServerConfig& cfg) {
    Impl impl;
    impl.cfg = cfg;
    // 发射器默认
    impl.st.emitter.mode = 0;
    impl.st.emitter.v_base = 400.0;
    impl.st.emitter.max_range = 90.0;
    impl.st.emitter.types = {{1.0, 0.1, 1.0, 1.0, 0xff3333},
                             {-1.0, 0.1, 1.0, 1.0, 0x3333ff},
                             {1.0, 1.0, 1.0, 1.0, 0xff8800}};
    return impl.run();
}
