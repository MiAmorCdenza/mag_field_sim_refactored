// WebSocket 服务层实现。
#include "server_app.h"

#include <chrono>
#include <condition_variable>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
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
#include "../core/logger.h"
#include "../core/tracer.h"
#include "../core/plan_compiler.h"

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
    std::string render_bindings_json = "[]";  // 渲染域绑定表(引擎权威)
    std::string particle_plan_json = "{}";    // 粒子域执行计划(引擎权威)
    bool plan_dirty = false;
    bool plan_slow_path = false;
    std::map<std::string, std::string> geom_cache;  // 渲染节点 id → 最近几何帧(新连接重放)
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
  "lattice": {"preset": "coarse"},
  "nodes": [
    {"id": "kp", "type": "kp_source", "params": {"kp": 2.0}},
    {"id": "day", "type": "day_source", "params": {"day": 172.0}},
    {"id": "t89", "type": "t89", "input_defaults": {"kp": 2.0, "ps": 0.5}},
    {"id": "tail", "type": "tail", "params": {"model": "flaring"}, "input_defaults": {"kp": 2.0, "ps": 0.5}},
    {"id": "dipole", "type": "dipole", "input_defaults": {"ps": 0.5}},
    {"id": "imf", "type": "imf_source", "params": {"polarity": -1, "parker_custom": true, "parker_angle": 40.0}, "input_defaults": {"kp": 2.0}},
    {"id": "internal", "type": "internal_blend", "input_defaults": {"kp": 2.0, "ps": 0.5}},
    {"id": "mp", "type": "magnetopause", "params": {"mp_model": 2}, "input_defaults": {"kp": 2.0, "ps": 0.5}},
    {"id": "conv", "type": "convection", "params": {"multiplier": 1.0}},
    {"id": "corot", "type": "corotation"},
    {"id": "shield", "type": "volland_shield", "params": {"r0": 4.0}},
    {"id": "emul", "type": "mul"},
    {"id": "eadd", "type": "add"},
    {"id": "drag", "type": "drag_layered", "params": {"multiplier": 1.0}},
    {"id": "ob", "type": "output_slot", "params": {"slot": "B"}},
    {"id": "oe", "type": "output_slot", "params": {"slot": "E"}},
    {"id": "od", "type": "output_slot", "params": {"slot": "drag"}},
    {"id": "rp", "type": "render_pipeline_start"},
    {"id": "rfl", "type": "render_item_field_lines"},
    {"id": "rel", "type": "render_item_efield_lines"},
    {"id": "rpt", "type": "render_item_particles"},
    {"id": "rdi", "type": "render_item_diagnostics"}
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
    {"from": ["mp", "field"], "to": ["corot", "b"]},
    {"from": ["conv", "field"], "to": ["emul", "a"]},
    {"from": ["shield", "coef"], "to": ["emul", "w"]},
    {"from": ["corot", "field"], "to": ["eadd", "a"]},
    {"from": ["emul", "field"], "to": ["eadd", "b"]},
    {"from": ["mp", "field"], "to": ["ob", "field"]},
    {"from": ["eadd", "field"], "to": ["oe", "field"]},
    {"from": ["drag", "coef"], "to": ["od", "field"]},
    {"from": ["rp", "next"], "to": ["rfl", "prev"]},
    {"from": ["rfl", "next"], "to": ["rel", "prev"]},
    {"from": ["rel", "next"], "to": ["rpt", "prev"]},
    {"from": ["rpt", "next"], "to": ["rdi", "prev"]},
    {"from": ["ob", "out"], "to": ["rfl", "data"]},
    {"from": ["oe", "out"], "to": ["rel", "data"]},
    {"from": ["od", "out"], "to": ["rdi", "data"]}
  ],
  "outputs": {}
})JSON";
}

}  // namespace

// 几何帧序列化:[u32 meta_len][JSON meta][每线:u8 class u8 reason u16 n f32xyz×n]
// 坐标重映射与粒子帧一致(Three.js 约定):(x, y, z) → (x, z, -y)
// 即 GSM 极轴(z)→ 场景 Y(向上);不做此映射磁轴会横躺在场景 Z 上
std::string build_geom_frame(const std::string& kind, const std::string& node_id,
                             uint64_t seq, const std::string& slot,
                             const std::vector<std::pair<int, FieldLine>>& lines) {
    json meta{{"type", "geom"}, {"kind", kind}, {"seq", seq},
              {"node", node_id}, {"slot", slot}, {"count", lines.size()}};
    std::string ms = meta.dump();
    std::string out;
    out.reserve(4 + ms.size() + lines.size() * 128);
    uint32_t mlen = (uint32_t)ms.size();
    out.append((const char*)&mlen, 4);
    out.append(ms);
    for (const auto& [cls, line] : lines) {
        uint8_t c = (uint8_t)cls;
        uint8_t r = (uint8_t)line.reason;
        uint16_t n = (uint16_t)std::min<size_t>(line.pts.size(), 0xFFFF);
        out.append((const char*)&c, 1);
        out.append((const char*)&r, 1);
        out.append((const char*)&n, 2);
        for (size_t i = 0; i < n; ++i) {
            float fx = (float)line.pts[i].x;
            float fy = (float)line.pts[i].z;
            float fz = -(float)line.pts[i].y;
            out.append((const char*)&fx, 4);
            out.append((const char*)&fy, 4);
            out.append((const char*)&fz, 4);
        }
    }
    return out;
}

struct ServerApp::Impl {
    ServerConfig cfg;
    BakeBridge bridge;
    std::mutex bridge_m;
    SharedState st;
    std::condition_variable bake_cv;

    // Crow 连接
    std::mutex conn_m;
    std::unordered_set<crow::websocket::connection*> conns;

    // 仿真管线:配置确定后构造(unique_ptr —— 隐式移动赋值在 MSVC 14.51
    // 下触发崩溃,见 git log/REFACTOR_PLAN 维护约定)
    std::unique_ptr<SimPipeline> pipeline;

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
                MFL("bake", "stale_discard", Debug, "丢弃过期烘焙结果", (nlohmann::json{{"seq", job.seq}}));
            }
        }
        } catch (const std::exception& e) {
            MFL("bake", "worker_exception", Error, "烘焙线程异常", (nlohmann::json{{"error", e.what()}}));
        } catch (...) {
            LOG_ERROR("bake", "worker_unknown_exception", "烘焙线程未知异常");
        }
    }

    // 渲染绑定 → 几何帧(烘焙应用后调用;10~20ms 量级)
    void run_render_bindings(uint64_t seq) {
        json binds;
        try {
            binds = json::parse(st.render_bindings_json);
        } catch (...) {
            return;
        }
        json gdoc;
        try {
            gdoc = json::parse(st.graph_json);
        } catch (...) {
            return;
        }
        // (node,port) → 槽位 反向映射
        std::map<std::pair<std::string, std::string>, std::string> slot_of;
        for (auto& [sn, ref] : gdoc["outputs"].items())
            slot_of[{ref[0], ref[1]}] = sn;

        for (const auto& b : binds) {
            std::string type = b.value("type", "");
            std::string nid = b.value("node_id", "");
            json ins = b.value("inputs", json::object());
            if (!ins.contains("data") || !ins["data"].is_array()) continue;
            std::string src = ins["data"][0].get<std::string>();
            std::string sport = ins["data"][1].get<std::string>();
            auto it = slot_of.find({src, sport});
            if (it == slot_of.end()) continue;
            const std::string& slot = it->second;
            const Table3D* table = nullptr;
            if (slot == "B") table = &pipeline->b_table;
            else if (slot == "E") table = &pipeline->e_table;
            else if (slot == "drag") table = &pipeline->drag_table;
            if (!table || !table->has_data()) continue;
            if (type != "render_item_field_lines" && type != "render_item_efield_lines")
                continue;

            TraceConfig tcfg;
            json prm = b.value("params", json::object());
            if (prm.contains("dsmax")) tcfg.dsmax = prm["dsmax"].get<double>();
            if (prm.contains("err")) tcfg.err = prm["err"].get<double>();
            tcfg.rlim = std::max(15.0, pipeline->max_range * 0.98);
            // 场表域(点阵范围):迹线越界即终止、种子按域过滤、rlim 封顶
            // —— 点阵外 sample() 钳制出常数场,会画出长直伪线
            // (纯偶极视图外侧"乱"的根因:tiny 点阵 ±10~15 Re vs rlim 88)
            tcfg.txmin = table->xs.front(); tcfg.txmax = table->xs.back();
            tcfg.tymin = table->ys.front(); tcfg.tymax = table->ys.back();
            tcfg.tzmin = table->zs.front(); tcfg.tzmax = table->zs.back();
            double dom_half = std::min({-tcfg.txmin, tcfg.txmax,
                                        -tcfg.tymin, tcfg.tymax,
                                        -tcfg.tzmin, tcfg.tzmax});
            tcfg.rlim = std::min(tcfg.rlim, dom_half * 0.98);

            SeedConfig sc;
            sc.dom_xmin = table->xs.front(); sc.dom_xmax = table->xs.back();
            sc.dom_ymin = table->ys.front(); sc.dom_ymax = table->ys.back();
            sc.dom_zmin = table->zs.front(); sc.dom_zmax = table->zs.back();
            SeedSet seeds = build_seeds(sc);
            std::vector<std::pair<int, FieldLine>> lines;
            auto trace_all = [&](const std::vector<Vec3>& v, int cls) {
                for (const auto& s : v) {
                    FieldLine l;
                    trace_line(*table, s, tcfg, l);
                    if (l.pts.size() >= 2) lines.push_back({cls, std::move(l)});
                }
            };
            trace_all(seeds.closed, 0);
            trace_all(seeds.open, 1);
            trace_all(seeds.solarwind, 2);

            std::string kind =
                type == "render_item_field_lines" ? "field_lines" : "efield_lines";
            std::string frame = build_geom_frame(kind, nid, seq, slot, lines);
            {
                // 缓存:几何帧是烘焙事件驱动的一次性帧,新连接需补发
                std::lock_guard<std::mutex> g(st.m);
                st.geom_cache[nid] = frame;
            }
            broadcast_bin(frame);
            MFL("render", "geom_frame", Info, "几何帧已广播",
                (nlohmann::json{{"kind", kind}, {"node", nid},
                                {"slot", slot}, {"lines", lines.size()},
                                {"seq", seq}}));
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

            // 0) 应用执行计划(图/节点参数变更后;空计划 → 默认后备计划)
            {
                bool dirty = false;
                std::string plan_json;
                EmitterConfig em_cfg;
                {
                    std::lock_guard<std::mutex> g(st.m);
                    dirty = st.plan_dirty;
                    if (dirty) {
                        plan_json = st.particle_plan_json;
                        st.plan_dirty = false;
                        em_cfg = st.emitter;
                    }
                }
                if (dirty) {
                    Plan plan;
                    std::string perr;
                    bool ok = false;
                    try {
                        auto doc = json::parse(plan_json);
                        ok = plancomp::plan_from_json(doc, plan, perr);
                    } catch (const std::exception& e) {
                        perr = e.what();
                    }
                    if (!ok || plan.ops.empty()) {
                        if (!ok)
                            MFL("plan", "parse_failed", Warn, "粒子计划解析失败,回退后备计划",
                                (nlohmann::json{{"error", perr}}));
                        plan = plancomp::make_default_plan(em_cfg, cfg.steps_per_frame,
                                                           IntegratorConfig{});
                    } else {
                        // 图内发射器节点参数不含粒子类型列表(v1)→ 沿用服务器默认
                        for (auto& op : plan.ops) {
                            if (op.kind == OpKind::Emitter && op.emitter.cfg.types.empty())
                                op.emitter.cfg.types = em_cfg.types;
                        }
                    }
                    if (pipeline->set_plan(plan, perr)) {
                        bool slow = plan.slow_path;
                        bool changed = false;
                        {
                            std::lock_guard<std::mutex> g(st.m);
                            changed = (st.plan_slow_path != slow);
                            st.plan_slow_path = slow;
                        }
                        if (changed) {
                            json m{{"type", "plan_status"}, {"slow_path", slow}};
                            broadcast_text(m.dump());
                        }
                        // 计划变更 → 全量重生:发射器/作用半径可能已换,
                        // 旧位置粒子(如 r=90)会被新 max_range 判死,
                        // 只重生死亡粒子救不回整批
                        pipeline->respawn_all();
                        MFL("plan", "applied", Info, "执行计划已应用",
                            (nlohmann::json{{"ops", plan.ops.size()},
                                            {"slow_path", slow}}));
                    } else {
                        MFL("plan", "rejected", Error, "执行计划校验失败",
                            (nlohmann::json{{"error", perr}}));
                    }
                }
            }

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
                    for (auto& [slot, field] : *done) pipeline->install_baked(field, err);
                    uint64_t applied_seq = st.completed_seq;
                    broadcast_progress(applied_seq, "done");
                    MFL("bake", "bake_applied", Info, "烘焙结果已应用", (nlohmann::json{{"seq", applied_seq}, {"slots", done->size()}}));
                    // 渲染绑定:场线/电场线几何帧(烘焙后一次性广播)
                    run_render_bindings(applied_seq);
                }
                if (failed) {
                    broadcast_progress(fseq, "error", ferr);
                    MFL("bake", "bake_failed", Error, "烘焙失败", (nlohmann::json{{"seq", fseq}, {"error", ferr}}));
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
                    if (pipeline->particles.count != (size_t)st.particle_count) {
                        pipeline->particles.resize((size_t)st.particle_count);
                        respawn = true;
                    }
                    if (rebuild_emitter && !pipeline->has_emitter_op) {
                        pipeline->emitter = Emitter(st.emitter);
                        respawn = true;
                    }
                }
                if (respawn) pipeline->respawn();
            }

            // 3) 物理步进(首次烘焙完成前不积分:空表步进无物理意义)
            if (pipeline->b_table.has_data()) pipeline->step_frame();

            // 4) 广播(网络帧率)——仿真线程零 Python(红线)
            if (frame_count % interval == 0) {
                std::vector<uint8_t> body;
                pipeline->encode(body);
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
            MFL("sim", "loop_exception", Error, "仿真线程异常", (nlohmann::json{{"error", e.what()}}));
        } catch (...) {
            LOG_ERROR("sim", "loop_unknown_exception", "仿真线程未知异常");
        }
    }

    // 插件目录指纹(新文件/修改/删除都会改变)
    uint64_t plugin_stamp() {
        uint64_t h = 0;
        for (const auto& dir : {cfg.root + "/nodes", cfg.root + "/user_nodes"}) {
            std::error_code ec;
            std::filesystem::directory_iterator it(dir, ec);
            if (ec) continue;
            for (auto& e : it) {
                if (e.path().extension() != ".py") continue;
                auto t = std::filesystem::last_write_time(e.path(), ec);
                h ^= (uint64_t)t.time_since_epoch().count() * 2654435761ull +
                     (uint64_t)(ec ? 0 : e.file_size());
            }
        }
        return h;
    }

    // 热加载监听:插件目录变化 → 重扫注册表 → 广播新节点面板
    void hotreload_watcher() {
        uint64_t last = plugin_stamp();
        while (st.running) {
            std::this_thread::sleep_for(std::chrono::seconds(2));
            uint64_t cur = plugin_stamp();
            if (cur == last) continue;
            last = cur;
            std::string err, desc;
            bool ok = false;
            {
                std::lock_guard<std::mutex> g(bridge_m);
                if (bridge.rescan(err)) ok = bridge.describe_types(desc, err);
            }
            if (ok) {
                json m{{"type", "registry"}, {"types", json::parse(desc)}};
                broadcast_text(m.dump());
                LOG_INFO("hotreload", "registry_refreshed", "插件目录变化,注册表已刷新");
            } else {
                MFL("hotreload", "rescan_failed", Warn, "插件重扫失败", (nlohmann::json{{"error", err}}));
            }
        }
    }

    int run() {
        LOG_INFO("server", "startup", "mf_server: 动态节点仿真服务器");

        // Python 引擎
        std::string err;
        if (!bridge.init(cfg.root, err)) {
            MFL("server", "engine_init_failed", Fatal, "引擎初始化失败", (nlohmann::json{{"error", err}}));
            return 1;
        }
        LOG_INFO("server", "engine_ready", "Python 引擎就绪");

        // 初始图
        st.graph_json = cfg.graph_path.empty() ? default_graph_json()
                                               : read_file(cfg.graph_path);
        {
            std::lock_guard<std::mutex> g(bridge_m);
            if (!bridge.load_graph(st.graph_json, err)) {
                MFL("server", "graph_load_failed", Fatal, "初始图加载失败", (nlohmann::json{{"error", err}}));
                return 1;
            }
            st.graph_version = bridge.graph_version();
            // 引擎权威快照(含 output_slot 自动推导的输出声明)
            bridge.graph_json(st.graph_json, err);
            bridge.declared_outputs(st.slots, err);
            bridge.render_bindings(st.render_bindings_json, err);
            std::string plan_json;
            if (bridge.particle_plan(plan_json, err)) {
                st.particle_plan_json = std::move(plan_json);
                st.plan_dirty = true;
            } else {
                MFL("plan", "compile_failed", Warn, "初始粒子计划编译失败,使用后备计划",
                    (nlohmann::json{{"error", err}}));
            }
        }
        MFL("server", "graph_loaded", Info, "初始图加载完成", (nlohmann::json{{"slots", st.slots}, {"version", st.graph_version}}));

        // 主线程释放 GIL(必须,见 BakeBridge::release_main_thread 注释)
        if (!bridge.release_main_thread())
            LOG_WARN("server", "gil_release_failed", "主线程 GIL 释放失败");

        // 管线(配置确定后构造;unique_ptr 见 Impl 成员注释)
        st.particle_count = cfg.particle_count;
        PipelineConfig pc;
        pc.particle_count = cfg.particle_count;
        pc.steps_per_frame = cfg.steps_per_frame;
        pc.emitter = st.emitter;
        pc.integrator.dt = 0.01;
        pc.integrator.max_range = 90.0;
        pipeline = std::make_unique<SimPipeline>(pc);

        // 线程
        std::thread baker([this] { bake_worker(); });
        std::thread sim([this] { sim_loop(); });
        std::thread watcher([this] { hotreload_watcher(); });

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
                // 几何帧重放(场线/电场线:烘焙完成后才产出,新连接补发)
                std::vector<std::string> cached;
                {
                    std::lock_guard<std::mutex> g2(st.m);
                    for (const auto& [k, v] : st.geom_cache) cached.push_back(v);
                }
                for (const auto& f : cached) conn.send_binary(f);
                if (!cached.empty())
                    MFL("render", "geom_replay", Debug, "几何帧已补发",
                        (nlohmann::json{{"frames", cached.size()}}));
                LOG_INFO("ws", "connected", "WebSocket 连接建立");
            })
            .onclose([this](crow::websocket::connection& conn, const std::string&) {
                std::lock_guard<std::mutex> g(conn_m);
                conns.erase(&conn);
                LOG_INFO("ws", "disconnected", "WebSocket 连接关闭");
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
                        std::string authoritative;
                        std::string rb_json;
                        std::string plan_json;
                        bool plan_ok = false;
                        {
                            std::lock_guard<std::mutex> g(bridge_m);
                            ok = bridge.load_graph(gjson, err);
                            if (ok) {
                                ver = bridge.graph_version();
                                // 引擎权威快照 + 推导槽位(output_slot 节点)
                                ok = bridge.graph_json(authoritative, err) &&
                                     bridge.declared_outputs(slots, err) &&
                                     bridge.render_bindings(rb_json, err);
                                // 粒子域执行计划(编译失败不拒绝图:回退旧计划)
                                if (ok) plan_ok = bridge.particle_plan(plan_json, err);
                            }
                        }
                        if (ok) {
                            {
                                std::lock_guard<std::mutex> g(st.m);
                                st.graph_json = authoritative;
                                st.slots = slots;
                                st.graph_version = ver;
                                st.render_bindings_json = rb_json;
                                st.geom_cache.clear();  // 图变了,旧几何帧作废(新烘焙重产)
                                if (plan_ok) {
                                    st.particle_plan_json = plan_json;
                                    st.plan_dirty = true;
                                }
                            }
                            if (!plan_ok)
                                MFL("plan", "compile_failed", Warn, "图上传后粒子计划编译失败",
                                    (nlohmann::json{{"error", err}}));
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
                            ok = bridge.set_param_value(msg["node"], msg["name"],
                                                        msg["value"].dump(), err);
                            if (ok) ver = bridge.graph_version();
                        }
                        if (ok) {
                            // 粒子域节点参数(如积分器 dt)→ 重编译执行计划
                            std::string plan_json;
                            bool plan_ok = false;
                            {
                                std::lock_guard<std::mutex> g(bridge_m);
                                plan_ok = bridge.particle_plan(plan_json, err);
                            }
                            {
                                std::lock_guard<std::mutex> g(st.m);
                                st.graph_version = ver;
                                if (plan_ok) {
                                    st.particle_plan_json = plan_json;
                                    st.plan_dirty = true;
                                }
                            }
                            if (!plan_ok)
                                MFL("plan", "compile_failed", Warn, "节点参数变更后粒子计划编译失败",
                                    (nlohmann::json{{"error", err}}));
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
                    MFL("ws", "message_error", Warn, "WS 消息处理失败", (nlohmann::json{{"error", e.what()}}));
                }
            });

        CROW_ROUTE(app, "/api/nodes")([this]() {
            std::string out, err;
            {
                std::lock_guard<std::mutex> g(bridge_m);
                if (!bridge.describe_types(out, err))
                    return crow::response(500, err);
            }
            return crow::response(out);
        });
        CROW_ROUTE(app, "/api/graph")([this]() {
            std::lock_guard<std::mutex> g(st.m);
            return crow::response(st.graph_json);
        });

        CROW_ROUTE(app, "/api/log").methods("POST"_method)
        ([this](const crow::request& req) {
            // 前端日志汇聚进同一条流(UI 错误与服务器状态可关联)
            try {
                auto body = nlohmann::json::parse(req.body, nullptr, false);
                if (body.is_null()) return crow::response(400);
                mflog::Logger::instance().log(
                    mflog::level_from_name(body.value("level", "info")),
                    "ui." + body.value("scope", "anon"),
                    body.value("event", "log"),
                    body.value("msg", ""),
                    body.value("attr", nlohmann::json::object()));
            } catch (...) {
                return crow::response(400);
            }
            return crow::response(R"({"ok":true})");
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

        MFL("server", "listening", Info, "服务启动", (nlohmann::json{{"host", cfg.host}, {"port", cfg.port}, {"ws", "ws://.../ws"}}));
        app.bindaddr(cfg.host).port(cfg.port).run();

        // 关闭
        {
            std::lock_guard<std::mutex> g(st.m);
            st.running = false;
        }
        bake_cv.notify_all();
        if (baker.joinable()) baker.join();
        if (sim.joinable()) sim.join();
        if (watcher.joinable()) watcher.join();
        return 0;
    }
};

int ServerApp::run(const ServerConfig& cfg) {
    Impl impl;
    impl.cfg = cfg;
    // 发射器默认
    impl.st.emitter.mode = 0;
    impl.st.emitter.v_base = 400.0;
    // 发射半径与默认点阵(coarse,x≤+25)一致:粒子在域内生成、
    // 采样真实场(域外会钳到边界值,物理失真)
    impl.st.emitter.max_range = 24.0;
    impl.st.emitter.types = {{1.0, 0.1, 1.0, 1.0, 0xff3333},
                             {-1.0, 0.1, 1.0, 1.0, 0x3333ff},
                             {1.0, 1.0, 1.0, 1.0, 0xff8800}};
    return impl.run();
}
