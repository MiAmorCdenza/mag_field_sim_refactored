// WS 协议层:服务器连接、图/参数/粒子控制、烘焙进度、二进制帧分发。
window.protocol = (function () {
    "use strict";

    // WS 在注册表就绪后连接(见 boot):否则 init_config 的 loadGraph
    // 会因节点类型未注册而整图跳过(竞态,曾导致空图 + 无渲染项)
    let ws = null;

    let serverGraph = null;
    let serverParticleCount = 0;   // 服务器全局粒子数(图内覆盖失效时恢复)
    const debounceTimers = {};

    // 实时统计(LiteGraph 自带覆盖层显示的是它自己的执行循环时间,本项目
    // 不跑 graph.runStep → 恒为 0;这里统计真实帧流供 HUD 使用。
    const simStats = { t: 0, n: 0, fps: 0, frames: 0, plan: null, src: null };
    window.simStats = simStats;
    let statWindowStart = performance.now();
    let statWindowFrames = 0;

    function noteFrame(header) {
        simStats.frames++;
        statWindowFrames++;
        if (header && typeof header.n === "number") simStats.n = header.n;
        if (header && typeof header.t === "number") simStats.t = header.t;
        const now = performance.now();
        if (now - statWindowStart >= 500) {
            simStats.fps = statWindowFrames * 1000 / (now - statWindowStart);
            statWindowStart = now;
            statWindowFrames = 0;
        }
    }

    // HUD 用定时器刷新:画布覆盖层只在重绘时更新(会假死),DOM 层才是实时的
    setInterval(() => {
        const el = document.getElementById("sim-hud");
        if (!el) return;
        const s = simStats;
        const g = window.editor && window.editor.graph;
        const plan = s.plan || {};
        const bits = [`t = ${(s.t || 0).toFixed(2)} s`,
                      `n = ${s.n | 0}`,
                      `${(s.fps || 0).toFixed(1)} fps`];
        if (g) {
            const real = g._nodes.filter(n => !n._isGhost).length;   // 虚影不计入
            const gh = g._nodes.length - real;
            bits.push(`N ${real}${gh ? "(+" + gh + " 隐式)" : ""}` +
                      `  E ${Object.keys(g.links || {}).length}`);
        }
        if (plan.count) {
            bits.push(plan.slow_path ? `计划粒子 ${plan.count} (slow_path)`
                                     : `计划粒子 ${plan.count}`);
        }
        if (plan.degenerate_injection) {
            bits.push("⚠ 注入生效:粒子全重合(count>1 无效)");
        }
        const nw = (s.warnings || []).length;
        if (nw) bits.push(`⚠ 计划告警 ${nw} 条(见画布红框节点)`);
        const pop = s.population;
        if (pop && pop.count > 0) {
            bits.push(`种群 ${pop.count} 种${pop.count > 1 ? "(图级声明)" : ""}`);
        }
        el.innerHTML = bits.map((b, i) =>
            `<span class="${i === 0 ? "" : "dim"}">${b}</span>`).join("\n");
    }, 250);

    function wsSend(obj) {
        if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
    }

    // ---- 小工具 ----
    window.toast = function (msg) {
        const el = document.getElementById("toast");
        el.textContent = msg;
        el.style.display = "block";
        clearTimeout(window.toast._t);
        window.toast._t = setTimeout(() => { el.style.display = "none"; }, 3000);
    };

    function setStatus(text, ok) {
        const el = document.getElementById("conn-status");
        el.textContent = text;
        el.className = "badge" + (ok ? " ok" : "");
    }
    function setVersion(v) { document.getElementById("graph-ver").textContent = "图 v" + v; }
    function setParticles(n) {
        document.getElementById("ptc-badge").textContent = "粒子 " + n;
        document.getElementById("ptc-input").value = n;
    }

    // ---- 前端日志:console 镜像 + warn 以上批量 POST /api/log 进同一条流 ----
    const logQueue = [];
    let logFlushTimer = null;

    window.uiLog = function (level, event, msg, attr) {
        attr = attr || {};
        const rank = { trace: 0, debug: 1, info: 2, warn: 3, error: 4, fatal: 5 }[level] ?? 2;
        const fn = rank >= 4 ? "error" : rank === 3 ? "warn" : "log";
        try { console[fn](`[ui.${event}] ${msg}`, attr); } catch (e) { /* ignore */ }
        if (rank >= 3) {
            logQueue.push({ level, scope: "ui", event, msg, attr });
            if (!logFlushTimer) logFlushTimer = setTimeout(flushUiLogs, 1500);
        }
    };

    function flushUiLogs() {
        logFlushTimer = null;
        const batch = logQueue.splice(0, logQueue.length);
        if (!batch.length) return;
        batch.forEach(e => {
            fetch("/api/log", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(e),
                keepalive: true,
            }).catch(() => {});
        });
    }

    // ---- 全局错误可见化(调试) ----
    window.onerror = function (msg, src, line, col) {
        try {
            window.toast("JS 错误: " + msg + " @" + (src || "").split("/").pop() + ":" + line);
            window.uiLog("error", "js_error", msg, { src: src, line: line, col: col });
            document.title = "ERR: " + msg;
        } catch (e) { /* ignore */ }
    };

    // ---- 启动:拉取节点注册表 → 再连 WS(避免 init_config 竞态)----
    async function boot() {
        try {
            const types = await fetch("/api/nodes").then(r => r.json());
            window.editor.initRegistry(types);
            console.log("[registry] 节点类型:", types.length);
        } catch (e) {
            window.toast("节点注册表加载失败: " + e);
        }
        connect();
    }

    // ---- 接收 ----
    function connect() {
        ws = new WebSocket(`ws://${location.host}/ws`);
        ws.binaryType = "arraybuffer";
        ws.onopen = () => setStatus("已连接", true);
        ws.onclose = () => setStatus("断开", false);
        ws.onerror = () => setStatus("错误", false);

        ws.onmessage = (e) => {
            if (typeof e.data === "string") {
                handleText(JSON.parse(e.data));
            } else if (e.data instanceof ArrayBuffer) {
                // 二进制帧 → 渲染宿主分发(按帧头 type/kind 路由到订阅渲染项)
                try {
                    const view = new DataView(e.data);
                    const hlen = view.getUint32(0, true);
                    const header = JSON.parse(new TextDecoder().decode(
                        new Uint8Array(e.data, 4, hlen)));
                    // 渲染项订阅约定:粒子帧 = "particles";
                    // 几何帧 = "geometry:" + header.kind(field_lines/efield_lines/…)
                    const kind = header.type === "s" ? "particles"
                        : "geometry:" + (header.kind || header.type || "unknown");
                    if (header.type === "s") noteFrame(header);
                    window.renderHost && window.renderHost.dispatch(kind, e.data, header);
                } catch (err) {
                    window.uiLog && window.uiLog("error", "frame_parse", String(err));
                }
            }
        };
    }

    function handleText(m) {
        if (m.type === "init_config") {
            serverGraph = m.graph;
            window.editor.loadGraph(m.graph);
            setVersion(m.version);
            setParticles(m.particles);
            serverParticleCount = m.particles || 0;
            // 无渲染域节点 → 3D 视口静默空屏(仿真仍正常,只是没人订阅输出)
            const hasRender = (m.graph.nodes || []).some(
                n => String(n.type || "").startsWith("render_"));
            if (!hasRender) {
                window.uiLog("warn", "no_render_node",
                    "当前图没有渲染域节点:拖入「渲染管线起始」+ 渲染项才能显示输出");
            }
        } else if (m.type === "bake_progress") {
            const bar = document.getElementById("bake-progress");
            const fill = document.getElementById("bake-bar");
            const text = document.getElementById("bake-text");
            bar.classList.remove("hidden");
            if (m.state === "queued") {
                fill.style.width = "5%"; text.textContent = "⏳ 排队中…";
            } else if (m.state === "computing") {
                fill.style.width = "40%"; text.textContent = "⏳ 烘焙中…";
            } else if (m.state === "done") {
                fill.style.width = "100%"; text.textContent = "✅ 烘焙完成";
                setTimeout(() => bar.classList.add("hidden"), 1200);
            } else if (m.state === "error") {
                fill.style.width = "100%";
                text.textContent = "❌ " + (m.note || "未知错误");
                setTimeout(() => bar.classList.add("hidden"), 2500);
            }
        } else if (m.type === "graph.error") {
            window.toast("图错误: " + m.message);
        } else if (m.type === "registry") {
            window.editor.initRegistry(m.types);
            window.toast("🔌 插件热更新:节点面板已刷新");
        } else if (m.type === "plan_status") {
            simStats.plan = m;
            if (m.slow_path) window.toast("⚠ 粒子计划含未知算子:慢路径(slow_path)");
            // 计划诊断(编译期 + 运行期):静默失败必须让用户看见
            // (实测踩过:删掉积分器的 b 数据线 → 无磁场、无任何提示)
            const warns = m.warnings || [];
            simStats.warnings = warns;
            if (warns.length) {
                const first = warns[0].msg || warns[0].code;
                window.toast(`⚠ 计划告警 ${warns.length} 条:${first}`);
                window.uiLog("warn", "plan_warning", first, { count: warns.length });
            }
            window.editor && window.editor.onPlanWarnings &&
                window.editor.onPlanWarnings(warns);
            // 隐式解析结果 → 画布摆出虚影节点 + 虚线(#31)
            simStats.implicit = m.implicit || [];
            window.editor && window.editor.onPlanImplicit &&
                window.editor.onPlanImplicit(simStats.implicit);
            // 注入节点生效且 count>1:所有粒子初条件相同 → 精确重合(看起来仍
            // 是 1 个粒子)。必须显式告警,否则"改了 count 没变化"极易误判。
            if (m.degenerate_injection) {
                window.toast("⚠ 注入节点仍在生效:count=" + m.count +
                    " 时所有粒子初条件完全相同(完全重合)。要撒多粒子请删除" +
                    "「单粒子注入」节点后点「应用图服务器」");
            }
            // 图内粒子数覆盖(发射器 count / 单粒子注入):同步界面徽标
            if (typeof m.count === "number") {
                if (m.count > 0) {
                    setParticles(m.count);
                } else if (serverParticleCount > 0) {
                    setParticles(serverParticleCount);
                }
            }
        } else if (m.type === "population") {
            // 服务器聚合出的**真实**种群(图级):画布接线只是表达
            simStats.population = m;
            window.editor && window.editor.onPopulation &&
                window.editor.onPopulation(m);
        } else if (m.type === "source_preview") {
            // L2 服务器预览:GSM → 渲染坐标在此统一重映射(与帧协议一致),
            // 渲染项只认场景坐标;物理量原样透传给属性面板读数。
            simStats.src = m;
            const g2s = (v) => (v ? [v[0], v[2], -v[1]] : null);
            const payload = {
                pos: g2s(m.pos),
                dir: (m.vel_mode === 1 || m.has_b) ? g2s(m.dir) : null,
                bdir: m.has_b ? g2s(m.bdir) : null,
                vmag: m.vmag,
                b_nt: m.b_nt,
                r_g_re: m.r_g_re,
                gyro_s: m.gyro_s,
                pitch: m.pitch,        // 俯仰角(度):插件可据此画角锥
                phase: m.phase,
                note: m.note || "",
            };
            window.renderHost && window.renderHost.dispatch("source_preview", payload);
            simStats.srcPayload = payload;   // 重选节点时重放(见 replaySourcePreview)
            window.editor && window.editor.onSourcePreview &&
                window.editor.onSourcePreview(m);
        }
    }

    // ---- 发送 ----
    function uploadGraph(doc) {
        const ids = new Set(doc.nodes.map(n => n.id));
        for (const [slot, ref] of Object.entries(doc.outputs || {})) {
            if (!ids.has(ref[0])) {
                window.toast(`输出槽「${slot}」引用了不存在的节点 ${ref[0]}`);
                return;
            }
        }
        wsSend({ type: "graph.upload", graph: doc });
        if (window.editor && window.editor.markGraphApplied) {
            window.editor.markGraphApplied();   // 已上传 → 清「未应用修改」提示
        }
        window.uiLog("info", "graph_upload", "图已上传,服务器开始烘焙",
            { nodes: doc.nodes.length, edges: doc.edges.length });
        window.toast("图已上传,服务器开始烘焙");
    }

    function sendParam(specType, node, name, value) {
        // 与 exportGraph 一致:优先原图 id(json_id),否则 n+数字
        const jsonId = node.properties.json_id || "n" + node.id;
        const key = jsonId + ":" + name;
        clearTimeout(debounceTimers[key]);
        debounceTimers[key] = setTimeout(() => {
            wsSend({ type: "node.param", node: jsonId, name, value });
        }, 250);
    }

    function respawn() { wsSend({ type: "respawn" }); }
    function resetToServer() { if (serverGraph) window.editor.loadGraph(serverGraph); }

    // 重放最后一次服务器预览(重选注入节点时用:服务器不会为"选中"再发一次)
    function replaySourcePreview() {
        if (!simStats.srcPayload) return false;
        window.renderHost && window.renderHost.dispatch("source_preview", simStats.srcPayload);
        return true;
    }

    document.getElementById("ptc-input").addEventListener("change", (e) => {
        const n = Math.max(1, parseInt(e.target.value) || 100);
        wsSend({ type: "set_particle_count", value: n });
    });

    boot();
    return { uploadGraph, sendParam, respawn, resetToServer, replaySourcePreview };
})();
