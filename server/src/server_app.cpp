// WebSocket 服务层实现。
#include "server_app.h"

#include <chrono>
#include <condition_variable>
#include <filesystem>
#include <fstream>
#include <algorithm>
#include <cctype>
#include <cstring>
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
    int plan_notice_count = -1;      // 计划广播过的图内粒子数(0=无覆盖)
    bool plan_degenerate = false;    // 注入 + count>1(粒子全重合,已告警)
    std::string plan_warnings_json;  // 上次广播的告警集合(变化判定用)
    json plan_warnings = json::array();
    std::string plan_status_json;    // 最近 plan_status(新连接重放:告警可见性)
    std::string plan_implicit_json;  // 上次广播的隐式解析集合(变化判定用)
    json plan_implicit = json::array();  // 隐式解析结果(画布虚线节点)
    json render_warnings = json::array();  // 渲染绑定解析告警(图上传时算) 
    std::map<std::string, std::string> geom_cache;  // 渲染节点 id → 最近几何帧(新连接重放)
    std::string source_preview_json;                // 最近 L2 初条件预览(新连接重放)
    std::string population_json;                    // 最近解析种群(新连接重放)
    EmitterConfig emitter;
    std::string bake_error;
    bool bake_failed = false;
    uint64_t bake_failed_seq = 0;
    bool running = true;
    // #43 暂停:只冻结物理步进(烘焙、图编辑、respawn 照常)。暂停态可被新连接重放
    bool paused = false;
    std::string sim_state_json;
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
    {"id": "pop", "type": "particle_population", "params": {"order": 20, "rows": [
        {"preset": "electron", "name": "电子", "q": -1.0, "mass": 0.0005446623093681911,
         "v_mult": 1.0, "weight": 1.0, "color": "#5599ff", "enabled": true},
        {"preset": "proton", "name": "质子", "q": 1.0, "mass": 1.0,
         "v_mult": 1.0, "weight": 1.0, "color": "#ff5555", "enabled": true},
        {"preset": "alpha", "name": "α粒子", "q": 2.0, "mass": 4.0,
         "v_mult": 1.0, "weight": 1.0, "color": "#ffaa33", "enabled": true}
      ]}},
    {"id": "pe", "type": "particle_emitter",
     "params": {"order": 10, "mode": 0, "v_base": 400.0, "max_range": 24.0}},
    {"id": "bi", "type": "boris_integrator",
     "params": {"order": 30, "dt": 0.01, "substeps": 5, "max_range": 24.0}},
    {"id": "enc", "type": "output_encoder", "params": {"order": 40}},
    {"id": "rp", "type": "render_pipeline_start"},
    {"id": "rfl", "type": "render_item_field_lines", "params": {"layer": 1}},
    {"id": "rel", "type": "render_item_efield_lines", "params": {"layer": 1}},
    {"id": "rpt", "type": "render_item_particles", "params": {"layer": 2}},
    {"id": "rtrl", "type": "render_item_particle_trails", "params": {"layer": 2}}
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
    {"from": ["pop", "types"], "to": ["pe", "types"]},
    {"from": ["ob", "out"], "to": ["bi", "b"]},
    {"from": ["oe", "out"], "to": ["bi", "e"]},
    {"from": ["od", "out"], "to": ["bi", "drag"]},
    {"from": ["ob", "out"], "to": ["rfl", "data"]},
    {"from": ["oe", "out"], "to": ["rel", "data"]},
    {"from": ["enc", "particles"], "to": ["rpt", "data"]},
    {"from": ["enc", "particles"], "to": ["rtrl", "data"]}
  ],
  "outputs": {}
})JSON";
}

}  // namespace

// 几何帧序列化:[u32 meta_len][JSON meta][每线:u8 class u8 reason u16 n f32xyz×n]
// 坐标重映射与粒子帧一致(Three.js 约定):(x, y, z) → (x, z, -y)
// 即 GSM 极轴(z)→ 场景 Y(向上);不做此映射磁轴会横躺在场景 Z 上
// 几何帧 v2(每点带场强,供前端按 |B| 着色):
//   [u32 meta_len][JSON meta][每线: u8 class u8 reason u16 n (f32 x,y,z, f32 |F|)×n]
// 坐标已重映射 GSM → Three (x,y,z)→(x,z,-y);|F| 为**渲染单位**
// (B 表 ×31200 → nT;E 表原样 → 归一化单位,由 meta.unit 说明)。
// v1(12 B/点,无场强)已不再产出,前端按 meta.v 兼容解析。
std::string build_geom_frame(const std::string& kind, const std::string& node_id,
                             uint64_t seq, const std::string& slot,
                             const std::vector<std::pair<int, FieldLine>>& lines,
                             double scalar_scale, const std::string& unit) {
    double smin = 1e300, smax = -1e300;
    for (const auto& [cls, line] : lines) {
        for (float v : line.bmag) {
            double s = (double)v * scalar_scale;
            if (s < smin) smin = s;
            if (s > smax) smax = s;
        }
    }
    if (smin > smax) { smin = 0.0; smax = 1.0; }
    json meta{{"type", "geom"}, {"kind", kind}, {"seq", seq},
              {"node", node_id}, {"slot", slot}, {"count", lines.size()},
              {"v", 2}, {"unit", unit},
              {"smin", smin}, {"smax", smax}};
    std::string ms = meta.dump();
    std::string out;
    out.reserve(4 + ms.size() + lines.size() * 256);
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
            float fv = (i < line.bmag.size()) ? (float)(line.bmag[i] * scalar_scale)
                                              : 0.0f;
            out.append((const char*)&fx, 4);
            out.append((const char*)&fy, 4);
            out.append((const char*)&fz, 4);
            out.append((const char*)&fv, 4);
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

    // L2 单粒子初条件预览:计划应用后 / 烘焙应用后广播(含局部 B 与由同一套
    // 数学给出的速度方向)。标量按积分器单位换算,前端只做坐标重映射。
    void broadcast_source_preview() {
        if (!pipeline || !pipeline->has_injection()) {
            std::lock_guard<std::mutex> g(st.m);
            st.source_preview_json.clear();   // 图内已无注入节点 → 作废缓存
            return;
        }
        SourcePreview sp = pipeline->source_preview();
        if (!sp.valid) return;
        json j{{"type", "source_preview"},
               {"pos", {sp.pos.x, sp.pos.y, sp.pos.z}},
               {"dir", {sp.v_dir.x, sp.v_dir.y, sp.v_dir.z}},
               {"bdir", {sp.b_dir.x, sp.b_dir.y, sp.b_dir.z}},
               {"vmag", sp.v_kms},
               {"b_nt", sp.b_nt},
               {"r_g_re", sp.r_g_re},
               {"gyro_s", sp.gyro_s},
               {"pitch", sp.pitch_deg},
               {"phase", sp.phase_deg},
               {"q_over_m", sp.q_over_m},
               {"has_b", sp.has_b},
               {"pos_mode", sp.pos_mode},
               {"vel_mode", sp.vel_mode},
               {"note", sp.note}};
        std::string payload;
        {
            std::lock_guard<std::mutex> g(st.m);
            st.source_preview_json = j.dump();
            payload = st.source_preview_json;
        }
        broadcast_text(payload);
    }

    // 解析后的种群广播(UI 读数):画布上的链/接线只是表达,实际生效的是
    // 服务器聚合出的这个列表 —— 未接线的物种节点同样参与生成,必须在界面上
    // 说清楚,否则"我接了一个物种,怎么还有别的粒子"无法自查。
    void broadcast_population() {
        if (!pipeline) return;
        json arr = json::array();
        for (const auto& e : pipeline->population()) {
            char hex[8];
            std::snprintf(hex, sizeof(hex), "#%06x", (unsigned)(e.color & 0xffffff));
            arr.push_back({{"name", e.name},
                           {"q", e.q}, {"mass", e.mass}, {"v_mult", e.v_mult},
                           {"weight", e.weight}, {"share", e.share},
                           {"color", hex}});
        }
        json j{{"type", "population"},
               {"species", arr},
               {"count", (int)pipeline->population().size()},
               {"total_weight", pipeline->population_weight()},
               {"injection", pipeline->has_injection()}};
        std::string payload;
        {
            std::lock_guard<std::mutex> g(st.m);
            st.population_json = j.dump();
            payload = st.population_json;
        }
        broadcast_text(payload);
    }

    // 槽位名 → 声明它的节点 id(UI 显示"粒子场源",#41)
    // ⚠ 调用方**必须已持有 st.m**:本函数不再自己加锁 —— 两处调用点都在 st.m
    //    临界区里,若在此再次 lock_guard → std::mutex 非递归 → **死锁**,
    //    仿真线程卡死、烘焙结果永远应用不上(实测踩过:所有模型都"算不出来")
    std::string field_source_of_locked(const std::string& slot) {
        json gdoc = json::parse(st.graph_json, nullptr, false);
        if (gdoc.is_discarded() || !gdoc.contains("outputs")) return "";
        auto& outs = gdoc["outputs"];
        if (!outs.contains(slot) || !outs[slot].is_array() || outs[slot].empty())
            return "";
        return outs[slot][0].is_string() ? outs[slot][0].get<std::string>() : "";
    }

    // 自身加锁的版本:**只能在 st.m 临界区之外调用**(计划应用处就是这种情况)
    std::string field_source_of(const std::string& slot) {
        std::lock_guard<std::mutex> g(st.m);
        return field_source_of_locked(slot);
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
            // 多场槽位(#41):按名取表(任意磁场槽位都能追溯场线)
            const Table3D* table = pipeline->table_for(slot);
            if (!table) continue;
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
            // B 表存的是归一化单位(÷31200),帧里换算回 nT;E 表原样(归一化)
            double sscale = (kind == "field_lines") ? B_NT_PER_CODE : 1.0;
            std::string sunit = (kind == "field_lines") ? "nT" : "归一化";
            std::string frame = build_geom_frame(kind, nid, seq, slot, lines,
                                                sscale, sunit);
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
                        int pcount = pipeline->plan_particle_count();  // 0 = 无覆盖
                        bool degen = pipeline->degenerate_injection();
                        // 图内粒子数覆盖:先按计划调整缓冲,再全量重生
                        if (pcount > 0 && pipeline->particles.count != (size_t)pcount)
                            pipeline->particles.resize((size_t)pcount);
                        bool changed = false;
                        {
                            std::lock_guard<std::mutex> g(st.m);
                            // 告警集合参与变化判定(否则"图没变但告警变了"不广播)
                            json wj = json::array();
                            for (const auto& w : pipeline->warnings())
                                wj.push_back({{"code", w.code}, {"node", w.node},
                                              {"port", w.port}, {"msg", w.msg}});
                            for (const auto& w : st.render_warnings)
                                wj.push_back(w);
                            std::string wjs = wj.dump();
                            // 隐式解析结果(画布用虚线摆出来):引擎真正用到但
                            // 图里没有的东西 —— 默认发射器 / 兜底物种 /
                            // 缺步进(粒子冻结)/ 缺编码器(不发帧)
                            json imp = json::array();
                            if (!pipeline->has_emitter_op)
                                imp.push_back({{"kind", "emitter"}, {"missing", false},
                                               {"msg", "图内无发射器:用服务器默认发射器"
                                                       "(全局粒子数与默认类型)"}});
                            if (!pipeline->has_step_op())
                                imp.push_back({{"kind", "step"}, {"missing", true},
                                               {"msg", "图内无积分器:粒子冻结在生成点"}});
                            if (pipeline->population().empty())
                                imp.push_back({{"kind", "species"}, {"missing", false},
                                               {"msg", "无物种声明:兜底粒子(白点 q=1 m=1)"}});
                            if (!pipeline->has_encoder())
                                imp.push_back({{"kind", "encoder"}, {"missing", true},
                                               {"msg", "图内无输出编码器:不发送粒子帧"}});
                            std::string ijs = imp.dump();
                            changed = (st.plan_slow_path != slow) ||
                                      (st.plan_notice_count != pcount) ||
                                      (st.plan_degenerate != degen) ||
                                      (st.plan_warnings_json != wjs) ||
                                      (st.plan_implicit_json != ijs);
                            st.plan_slow_path = slow;
                            st.plan_notice_count = pcount;
                            st.plan_degenerate = degen;
                            st.plan_warnings_json = wjs;
                            st.plan_warnings = wj;
                            st.plan_implicit_json = ijs;
                            st.plan_implicit = imp;
                        }
                        if (changed) {
                            json m{{"type", "plan_status"}, {"slow_path", slow},
                                   {"b_slot", pipeline->step_b_slot()},
                                   {"b_source", field_source_of(pipeline->step_b_slot())},
                                   {"count", pcount},
                                   {"degenerate_injection", degen},
                                   {"respawn", pipeline->has_respawn()},
                                   {"warnings", st.plan_warnings},
                                   {"implicit", st.plan_implicit}};
                            {
                                std::lock_guard<std::mutex> g(st.m);
                                st.plan_status_json = m.dump();
                            }
                            MFL("plan", "status_broadcast", Debug, "计划状态已广播",
                                (nlohmann::json{{"warnings", st.plan_warnings.size()},
                                                {"implicit", st.plan_implicit.size()}}));
                            broadcast_text(m.dump());
                        }
                        if (degen)
                            MFL("plan", "degenerate_injection", Warn,
                                "注入节点生效且 count>1:所有粒子初条件相同(完全重合);"
                                "要撒多粒子请删除注入节点后重新应用图",
                                (nlohmann::json{{"count", pcount}}));
                        for (const auto& w : pipeline->warnings()) {
                            if (w.code == "degenerate_injection") continue;  // 上面已单独记
                            MFL("plan", "warning", Warn, w.msg,
                                (nlohmann::json{{"code", w.code}, {"node", w.node},
                                                {"port", w.port}}));
                        }
                        // 计划变更 → 全量重生:发射器/作用半径可能已换,
                        // 旧位置粒子(如 r=90)会被新 max_range 判死,
                        // 只重生死亡粒子救不回整批
                        pipeline->respawn_all();
                        broadcast_source_preview();   // 注入参数一改即预览
                        broadcast_population();       // 种群读数(图级聚合结果)
                        MFL("plan", "applied", Info, "执行计划已应用",
                            (nlohmann::json{{"ops", plan.ops.size()},
                                            {"slow_path", slow},
                                            {"count", pcount},
                                            {"injection", pipeline->has_injection()}}));
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
                    broadcast_source_preview();   // B 表就绪 → 预览含真实局部 B
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
                    if (pipeline->particles.count != (size_t)st.particle_count &&
                        pipeline->plan_particle_count() <= 0) {   // 图内覆盖优先
                        pipeline->particles.resize((size_t)st.particle_count);
                        respawn = true;
                    }
                    if (rebuild_emitter && !pipeline->has_emitter_op) {
                        pipeline->emitter = Emitter(st.emitter);
                        // 重建后重新绑定 B 表:否则注入俯仰角模式失去局部 B
                        // (静默回退 z 轴,预览与生成都会偏)
                        pipeline->emitter.set_field(pipeline->table_for("B"));
                        pipeline->reapply_species();  // 物种声明优先于 legacy 默认类型
                        respawn = true;
                    }
                }
                if (respawn) pipeline->respawn();
            }

            // 3) 物理步进(首次烘焙完成前不积分:空表步进无物理意义)
            // #43 暂停:冻结物理步进(烘焙/图编辑/respawn 均不受影响)
            bool paused_now = false;
            {
                std::lock_guard<std::mutex> g(st.m);
                paused_now = st.paused;
            }
            if (!paused_now && pipeline->b_table().has_data()) pipeline->step_frame();

            // 3b) 运行期诊断(#35):无重生且死伤过半 → population_decaying。
            //     计划状态平时只在"计划变化"时广播,这里为运行期变化补一条
            //     (只在告警状态翻转时触发,不是每帧)。
            if (pipeline->refresh_runtime_warnings()) {
                json wj = json::array();
                for (const auto& w : pipeline->warnings())
                    wj.push_back({{"code", w.code}, {"node", w.node},
                                  {"port", w.port}, {"msg", w.msg}});
                json status;
                {
                    std::lock_guard<std::mutex> g(st.m);
                    for (const auto& w : st.render_warnings) wj.push_back(w);
                    st.plan_warnings_json = wj.dump();
                    st.plan_warnings = wj;
                    status = json{{"type", "plan_status"},
                                  {"b_slot", pipeline->step_b_slot()},
                                  {"b_source", field_source_of_locked(pipeline->step_b_slot())},
                                  {"slow_path", st.plan_slow_path},
                                  {"count", st.plan_notice_count},
                                  {"degenerate_injection", st.plan_degenerate},
                                  {"respawn", pipeline->has_respawn()},
                                  {"warnings", st.plan_warnings},
                                  {"implicit", st.plan_implicit}};
                    st.plan_status_json = status.dump();
                }
                MFL("plan", "runtime_warning", Warn, "运行期计划诊断变化",
                    (nlohmann::json{{"dead_ratio", pipeline->dead_ratio()}}));
                broadcast_text(status.dump());
            }

            // 4) 广播(网络帧率)——仿真线程零 Python(红线)
            // 编码器节点现在**真正生效**:计划里没有 encode 算子就不发粒子帧
            // (以前 C++ 无条件编码,节点纯装饰,见 REFACTOR_PLAN #27)
            if (frame_count % interval == 0 && pipeline->has_encoder()) {
                std::vector<uint8_t> body;
                pipeline->encode(body);
                uint64_t ver = 0;
                {
                    std::lock_guard<std::mutex> g(st.m);
                    ver = st.graph_version;
                }
                json header{{"type", "s"}, {"n", body.size() / 21}, {"v", ver},
                            {"t", pipeline->sim_time()}};
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
                // L2 预览重放(计划/烘焙时算好,新连接补发:否则后连的页面
                // 永远看不到初条件预览 —— 它只在事件点广播)
                {
                    std::lock_guard<std::mutex> g2(st.m);
                    if (!st.source_preview_json.empty())
                        conn.send_text(st.source_preview_json);
                    if (!st.population_json.empty())
                        conn.send_text(st.population_json);
                    if (!st.plan_status_json.empty())
                        conn.send_text(st.plan_status_json);
                    if (!st.sim_state_json.empty())       // #43 暂停态也要重放
                        conn.send_text(st.sim_state_json);
                }
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
                            // 渲染绑定诊断:①场线类渲染项解析不出槽位 → 永远
                            // 不会产出几何帧;②声明了订阅通道却没接 data →
                            // 不订阅、不渲染(#32 接线决定订阅)。两者都是
                            // "画布看着对、实际没数据"的静默失败。
                            json rwarn = json::array();
                            try {
                                auto binds = json::parse(rb_json);
                                for (const auto& b : binds) {
                                    std::string t = b.value("type", "");
                                    std::string nid = b.value("node_id", "");
                                    const bool needs = b.value("needs_data", false);
                                    const bool has = b.value("has_data", false);
                                    int nch = 0;
                                    if (b.contains("channels") && b["channels"].is_array())
                                        nch = (int)b["channels"].size();
                                    if (needs && !has) {
                                        std::string what =
                                            (nch > 0) ? b["channels"][0].get<std::string>()
                                                      : std::string("数据");
                                        rwarn.push_back({
                                            {"code", "render_item_unwired"},
                                            {"node", nid},
                                            {"msg", "渲染项 " + nid + " 没有接数据源:"
                                             "不订阅「" + what + "」通道,不会显示"
                                             "(接线决定订阅)"}});
                                        continue;
                                    }
                                    if (t != "render_item_field_lines" &&
                                        t != "render_item_efield_lines") continue;
                                    // 注意:slot 可能是 JSON null → value(...) 会抛
                                    // type_error(曾整段被 catch 吞掉,告警静默丢失)
                                    std::string slot;
                                    if (b.contains("slot") && b["slot"].is_string())
                                        slot = b["slot"].get<std::string>();
                                    if (slot.empty()) {
                                        rwarn.push_back({
                                            {"code", "render_no_slot"},
                                            {"node", nid},
                                            {"msg", "渲染项 " + nid +
                                             " 的数据源没有声明输出槽位:"
                                             "不会产出几何帧(视口无场线)"}});
                                    }
                                }
                            } catch (const std::exception& e) {
                                MFL("render", "binding_parse_failed", Warn,
                                    "渲染绑定解析失败(告警未生成)",
                                    (nlohmann::json{{"error", e.what()}}));
                            }
                            {
                                std::lock_guard<std::mutex> g(st.m);
                                st.graph_json = authoritative;
                                st.slots = slots;
                                st.graph_version = ver;
                                st.render_bindings_json = rb_json;
                                st.render_warnings = rwarn;
                                st.geom_cache.clear();  // 图变了,旧几何帧作废(新烘焙重产)
                                st.source_preview_json.clear();  // 旧预览同理作废
                                st.population_json.clear();      // 种群读数随图作废
                                st.plan_status_json.clear();     // 旧计划状态随图作废
                                // 同时清掉"上次广播"标记:否则**重复上传同一张图**时
                                // 变化判定为 false → 不广播 → 缓存永远空 → 新连接
                                // 拿不到 plan_status(实测 HUD 里计划/场源整行消失)
                                st.plan_warnings_json.clear();
                                st.plan_implicit_json.clear();
                                st.plan_notice_count = -1;
                                if (pipeline) pipeline->reset_sim_time();  // 换图 → t 归零
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
                            std::string plan_json, gjson;
                            bool plan_ok = false, graph_ok = false;
                            {
                                std::lock_guard<std::mutex> g(bridge_m);
                                plan_ok = bridge.particle_plan(plan_json, err);
                                // 同步权威图 JSON:否则 node.param 只改了 Python 侧
                                // 图,而 init_config / 「重置为服务器图」仍发旧参数
                                // (实测:滑块改了 count,新连接拿到的还是旧值)
                                graph_ok = bridge.graph_json(gjson, err);
                            }
                            {
                                std::lock_guard<std::mutex> g(st.m);
                                st.graph_version = ver;
                                if (graph_ok) st.graph_json = gjson;
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
                    } else if (type == "sim.pause") {
                        // #43 暂停/继续:冻结物理,广播状态(并缓存供新连接重放)
                        bool paused = msg.value("paused", false);
                        json st_json;
                        {
                            std::lock_guard<std::mutex> g(st.m);
                            st.paused = paused;
                            st_json = json{{"type", "sim_state"},
                                           {"paused", st.paused},
                                           {"t", pipeline ? pipeline->sim_time() : 0.0},
                                           {"n", pipeline ? (int)pipeline->particles.count : 0}};
                            st.sim_state_json = st_json.dump();
                        }
                        broadcast_text(st_json.dump());
                        MFL("sim", "pause", Info, paused ? "仿真已暂停" : "仿真已继续",
                            nlohmann::json::object());
                    } else if (type == "particle.query") {
                        // #43 粒子属性查询(暂停态查看器):C++ 只给**原始快照**
                        // (位置/速度/荷质比/状态/颜色 + 局部 B),派生量交给
                        // analysis/*.py 的度量插件算 —— 新增指标不用改这里
                        std::vector<int> ids;
                        for (const auto& v : msg.value("ids", json::array())) {
                            if (v.is_number_integer()) ids.push_back(v.get<int>());
                            if (ids.size() >= 500) break;      // 上限:明细不刷屏
                        }
                        json items = json::array();
                        std::string aerr, aout;
                        bool aok = false;
                        if (pipeline && !ids.empty()) {
                            const auto& P = pipeline->particles;
                            std::unordered_map<int, size_t> idx_of;
                            idx_of.reserve(P.count * 2);
                            for (size_t i = 0; i < P.count; ++i) idx_of[P.id[i]] = i;
                            const Table3D& tab = pipeline->b_table();
                            for (int id : ids) {
                                auto it = idx_of.find(id);
                                if (it == idx_of.end()) continue;
                                const size_t i = it->second;
                                double bx = 0, by = 0, bz = 0;
                                if (tab.has_data())
                                    tab.sample(P.x[i], P.y[i], P.z[i], bx, by, bz);
                                items.push_back({
                                    {"id", id},
                                    {"pos", {P.x[i], P.y[i], P.z[i]}},
                                    {"vel", {P.vx[i], P.vy[i], P.vz[i]}},
                                    {"q", P.q[i]}, {"m", P.m[i]},
                                    {"color", P.color[i]}, {"status", (int)P.status[i]},
                                    {"b", {bx * B_NT_PER_CODE, by * B_NT_PER_CODE,
                                           bz * B_NT_PER_CODE}}});
                            }
                            json payload{{"root", cfg.root}, {"items", items}};
                            if (msg.contains("metrics")) payload["metrics"] = msg["metrics"];
                            std::lock_guard<std::mutex> g(bridge_m);
                            aok = bridge.analyze(payload.dump(), aout, aerr);
                        } else if (pipeline) {
                            // 空 ids:仅返回度量目录(前端据此成表)
                            json payload{{"root", cfg.root}, {"items", json::array()}};
                            std::lock_guard<std::mutex> g(bridge_m);
                            aok = bridge.analyze(payload.dump(), aout, aerr);
                        }
                        if (aok) {
                            json res = json::parse(aout, nullptr, false);
                            if (res.is_discarded()) res = json::object();
                            res["type"] = "particle.info";
                            conn.send_text(res.dump());
                        } else {
                            conn.send_text(json{{"type", "particle.info"},
                                                {"error", aerr}}.dump());
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

        // 预设发现(#33):扫 graphs/preset_*.json → 引导页卡片列表。
        // 预设文件可带 meta 块(取不到就用文件名);
        // 增删预设 = 增删文件,前端自动排列,无需改代码。
        CROW_ROUTE(app, "/api/presets")([this]() {
            nlohmann::json arr = nlohmann::json::array();
            std::error_code ec;
            const std::string dir = cfg.root + "/graphs";
            std::filesystem::directory_iterator it(dir, ec);
            if (ec) return crow::response(500, "graphs 目录不存在: " + dir);
            std::vector<std::filesystem::path> files;
            for (auto& e : it) {
                if (!e.is_regular_file()) continue;
                const auto name = e.path().filename().string();
                if (name.rfind("preset_", 0) != 0) continue;
                if (e.path().extension() != ".json") continue;
                files.push_back(e.path());
            }
            std::sort(files.begin(), files.end());
            for (const auto& p : files) {
                std::ifstream f(p, std::ios::binary);
                if (!f) continue;
                nlohmann::json doc = nlohmann::json::parse(f, nullptr, false);
                if (doc.is_discarded() || !doc.is_object()) continue;
                const nlohmann::json meta =
                    doc.contains("preset") && doc["preset"].is_object()
                        ? doc["preset"] : nlohmann::json::object();
                std::string stem = p.stem().string();          // preset_xxx
                std::string id = stem.rfind("preset_", 0) == 0
                                     ? stem.substr(7) : stem;
                nlohmann::json card{
                    {"id", meta.value("id", id)},
                    {"name", meta.value("name", id)},
                    {"desc", meta.value("desc", "")},
                    {"file", p.filename().string()},
                    {"custom", meta.value("custom", false)},
                    {"sort", meta.value("sort", 100)},
                    {"lattice", doc.value("lattice", nlohmann::json::object())
                                    .value("preset", "coarse")},
                    {"nodes", doc.contains("nodes") ? doc["nodes"].size() : 0},
                    {"edges", doc.contains("edges") ? doc["edges"].size() : 0},
                };
                arr.push_back(std::move(card));
            }
            std::stable_sort(arr.begin(), arr.end(),
                             [](const nlohmann::json& a, const nlohmann::json& b) {
                                 return a.value("sort", 100) < b.value("sort", 100);
                             });
            return crow::response(arr.dump());
        });

        // 取某个预设的图 JSON(引导页点卡片 → 直接喂给编辑器/服务器)
        CROW_ROUTE(app, "/api/preset")([this](const crow::request& req) {
            std::string id = req.url_params.get("id") ? req.url_params.get("id") : "";
            if (id.empty()) return crow::response(400, "缺少 id");
            // 只允许 graphs/preset_*.json,防目录穿越
            for (const char c : id) {
                if (!(std::isalnum((unsigned char)c) || c == '_' || c == '-'))
                    return crow::response(400, "非法 id");
            }
            const std::string path = cfg.root + "/graphs/preset_" + id + ".json";
            std::ifstream f(path, std::ios::binary);
            if (!f) return crow::response(404, "预设不存在: " + id);
            std::string body((std::istreambuf_iterator<char>(f)),
                             std::istreambuf_iterator<char>());
            crow::response r(body);
            r.set_header("Content-Type", "application/json");
            return r;
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
            // MIME 必须按扩展名给:实测 SVG 被当 text/html 发出去时,<img> 直接
            // 拒绝渲染(naturalWidth=0,破图占位)—— 状态码是 200,很容易误判
            // 扩展名 → MIME(SVG 必须 image/svg+xml,否则 <img> 拒绝渲染:
            // 状态码 200 但破图,实测踩过)。定义在路由内,避免 lambda 捕获问题
            const std::string ext = [&path] {
                const size_t d = path.find_last_of('.');
                std::string e = d == std::string::npos ? "" : path.substr(d);
                for (auto& c : e) c = (char)std::tolower((unsigned char)c);
                return e;
            }();
            const char* mime = "application/octet-stream";
            if (ext == ".svg") mime = "image/svg+xml";
            else if (ext == ".css") mime = "text/css";
            else if (ext == ".js") mime = "text/javascript";
            else if (ext == ".json") mime = "application/json";
            else if (ext == ".png") mime = "image/png";
            else if (ext == ".jpg" || ext == ".jpeg") mime = "image/jpeg";
            else if (ext == ".html") mime = "text/html; charset=utf-8";
            else if (ext == ".txt" || ext == ".md") mime = "text/plain; charset=utf-8";
            crow::response r(ss.str());
            r.set_header("Content-Type", mime);
            return r;
        });

        MFL("server", "listening", Info, "服务启动", (nlohmann::json{{"host", cfg.host}, {"port", cfg.port}, {"ws", "ws://.../ws"}}));
        // 主循环包一层诊断:实测遇到过"服务器静默退出(退出码 1,无崩溃记录,
        // 日志戛然而止)"—— 异常逃逸出 Crow 会让 app.run() 直接返回,而
        // main 只看到返回值。这里至少让它留下原因(是异常、还是主循环自己退出)。
        try {
            app.bindaddr(cfg.host).port(cfg.port).run();
            MFL("server", "run_returned", Warn,
                "HTTP/WS 主循环自行返回(非正常关闭路径):进程即将退出",
                nlohmann::json::object());
        } catch (const std::exception& e) {
            MFL("server", "run_exception", Fatal,
                "主循环抛出 C++ 异常,服务器退出",
                (nlohmann::json{{"what", e.what()}}));
            st.running = false;
            return 1;
        } catch (...) {
            MFL("server", "run_exception", Fatal,
                "主循环抛出未知异常,服务器退出",
                nlohmann::json::object());
            st.running = false;
            return 1;
        }

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
