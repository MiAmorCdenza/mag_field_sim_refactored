// WS 协议层:服务器连接、图/参数/粒子控制、烘焙进度、二进制帧分发。
window.protocol = (function () {
    "use strict";

    const ws = new WebSocket(`ws://${location.host}/ws`);
    ws.binaryType = "arraybuffer";

    let serverGraph = null;
    const debounceTimers = {};

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

    // ---- 启动:拉取节点注册表 ----
    async function boot() {
        try {
            const types = await fetch("/api/nodes").then(r => r.json());
            window.editor.initRegistry(types);
            console.log("[registry] 节点类型:", types.length);
        } catch (e) {
            window.toast("节点注册表加载失败: " + e);
        }
    }

    // ---- 接收 ----
    ws.onopen = () => setStatus("已连接", true);
    ws.onclose = () => setStatus("断开", false);
    ws.onerror = () => setStatus("错误", false);

    ws.onmessage = (e) => {
        if (typeof e.data === "string") {
            handleText(JSON.parse(e.data));
        } else if (e.data instanceof ArrayBuffer) {
            window.renderer.updateFrame(e.data);
        }
    };

    function handleText(m) {
        if (m.type === "init_config") {
            serverGraph = m.graph;
            window.editor.loadGraph(m.graph);
            setVersion(m.version);
            setParticles(m.particles);
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
        ws.send(JSON.stringify({ type: "graph.upload", graph: doc }));
        window.toast("图已上传,服务器开始烘焙");
    }

    function sendParam(specType, node, name, value) {
        const jsonId = "n" + node.id;
        const key = jsonId + ":" + name;
        clearTimeout(debounceTimers[key]);
        debounceTimers[key] = setTimeout(() => {
            ws.send(JSON.stringify({ type: "node.param", node: jsonId, name, value }));
        }, 250);
    }

    function respawn() { ws.send(JSON.stringify({ type: "respawn" })); }
    function resetToServer() { if (serverGraph) window.editor.loadGraph(serverGraph); }

    document.getElementById("ptc-input").addEventListener("change", (e) => {
        const n = Math.max(1, parseInt(e.target.value) || 100);
        ws.send(JSON.stringify({ type: "set_particle_count", value: n }));
    });

    boot();
    return { uploadGraph, sendParam, respawn, resetToServer };
})();
