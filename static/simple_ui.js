// 简化面板(#38):左侧 Dock —— 按类别动态列出当前图里的节点,展开即可调参数。
//
// 设计意图(用户诉求):
//   - 主体留给"地磁场相关展示"(3D 视口),不需要懂节点图也能用预设
//   - 节点**动态分类**加载:类别来自节点规格的 `category`(磁场/外部模型、
//     粒子/发射…),只列**当前图里真实存在**的节点 —— 换预设即换面板
//   - Dock 可收缩隐藏;展开节点后才构建参数控件(惰性,节点多也不卡)
//   - 参数控件**复用**标准面板那一套(editor.buildParamsInto)→ 两处永远一致,
//     改动即时下发(node.param,服务器重编译计划/必要时重烘焙)
//   - 工具栏「◧ 简化 / ⊞ 标准」一键切换,选择记在 localStorage
//
// 与标准面板的关系:简化面板**不是**另一套状态,只是同一张图的另一种视图。
window.simpleUI = (function () {
    "use strict";

    const MODE_KEY = "mf_ui_mode";
    const DOCK_KEY = "mf_dock_open";
    let groupOf = {};        // 节点类型 → 类别(来自 /api/nodes)
    let expanded = {};       // "类别/节点id" → bool(记住展开状态)

    function el(id) { return document.getElementById(id); }

    // 类别显示名与顺序(未知类别排后面,自动兜底 —— 新插件不需要改这里)
    const CAT_ORDER = ["磁场", "粒子", "渲染", "组合", "输出"];
    function catKey(cat) {
        if (!cat) return "其它";
        return cat.split("/")[0];
    }
    function catRank(c) {
        const i = CAT_ORDER.indexOf(c);
        return i < 0 ? CAT_ORDER.length : i;
    }

    async function loadSpecs() {
        try {
            const types = await fetch("/api/nodes").then(r => r.json());
            groupOf = {};
            for (const t of types) groupOf[t.type] = t.category || "其它";
        } catch (e) {
            window.uiLog && window.uiLog("warn", "dock_specs", String(e));
        }
    }

    // ---- 模式切换(简化 ⇄ 标准)----
    function setMode(mode) {
        const simple = mode === "simple";
        document.body.classList.toggle("simple-mode", simple);
        localStorage.setItem(MODE_KEY, simple ? "simple" : "standard");
        const btn = el("btn-ui-mode");
        if (btn) btn.textContent = simple ? "⊞ 标准面板" : "◧ 简化面板";
        if (simple) {
            build();
            // 视口尺寸变了:让 three.js 重新适配
            window.dispatchEvent(new Event("resize"));
        } else {
            window.dispatchEvent(new Event("resize"));
        }
    }
    function toggleMode() {
        setMode(document.body.classList.contains("simple-mode")
            ? "standard" : "simple");
    }

    function setDockOpen(open) {
        document.body.classList.toggle("dock-collapsed", !open);
        localStorage.setItem(DOCK_KEY, open ? "1" : "0");
        const b = el("dock-toggle");
        if (b) b.textContent = open ? "◀" : "▶";
        window.dispatchEvent(new Event("resize"));
    }

    // ---- Dock 构建 ----
    function graphNodes() {
        const g = window.editor && window.editor.graph;
        if (!g || !g._nodes) return [];
        // 虚影节点(#31)不可编辑,不进面板
        return g._nodes.filter(n => !n._isGhost && n._spec);
    }

    function build() {
        const box = el("dock-body");
        if (!box) return;
        if (!document.body.classList.contains("simple-mode")) return;
        box.innerHTML = "";

        const nodes = graphNodes();
        if (!nodes.length) {
            box.innerHTML = '<div class="hint">当前图没有节点:点「☰ 预设」载入一个预设。</div>';
            return;
        }
        // 按类别分组(动态:类别来自节点规格;组内按节点名排序)
        const groups = new Map();
        for (const n of nodes) {
            const c = catKey(groupOf[n._spec.type] || n._spec.category);
            if (!groups.has(c)) groups.set(c, []);
            groups.get(c).push(n);
        }
        const cats = [...groups.keys()].sort((a, b) =>
            catRank(a) - catRank(b) || a.localeCompare(b));

        for (const c of cats) {
            const list = groups.get(c).sort((a, b) =>
                (a._spec.name || "").localeCompare(b._spec.name || ""));
            const sec = document.createElement("section");
            sec.className = "dock-group";
            const head = document.createElement("div");
            head.className = "dock-group-head";
            head.textContent = `${c} (${list.length})`;
            sec.appendChild(head);

            for (const node of list) {
                const key = c + "/" + node.id;
                const item = document.createElement("div");
                item.className = "dock-node";
                const row = document.createElement("button");
                row.className = "dock-node-head";
                const isOpen = !!expanded[key];
                row.innerHTML = `<span class="dock-caret">${isOpen ? "▾" : "▸"}</span>` +
                    `<span class="dock-icon">${node._spec.icon || "•"}</span>` +
                    `<span class="dock-name">${node._spec.name || node._spec.type}</span>` +
                    `<span class="dock-id">${node.id}</span>`;
                const body = document.createElement("div");
                body.className = "dock-node-body";
                // 惰性构建:展开时才生成控件(节点多也不拖慢面板)
                const fill = () => {
                    if (body.childElementCount) return;
                    try {
                        window.editor.buildParamsInto(node, body);
                    } catch (e) {
                        body.innerHTML = '<div class="hint">参数渲染失败:' + e + "</div>";
                    }
                };
                if (isOpen) { fill(); body.classList.add("open"); }
                row.onclick = () => {
                    const nowOpen = !body.classList.contains("open");
                    body.classList.toggle("open", nowOpen);
                    row.querySelector(".dock-caret").textContent = nowOpen ? "▾" : "▸";
                    expanded[key] = nowOpen;
                    if (nowOpen) fill();
                };
                item.appendChild(row);
                item.appendChild(body);
                sec.appendChild(item);
            }
            box.appendChild(sec);
        }
    }

    function init() {
        const btn = el("btn-ui-mode");
        if (btn) btn.onclick = toggleMode;
        const dt = el("dock-toggle");
        if (dt) dt.onclick = () =>
            setDockOpen(document.body.classList.contains("dock-collapsed"));
        const refresh = el("dock-refresh");
        if (refresh) refresh.onclick = build;

        loadSpecs().then(() => {
            setDockOpen(localStorage.getItem(DOCK_KEY) !== "0");
            // 首屏默认进简化面板(预设演示场景);用户切过就记住
            setMode(localStorage.getItem(MODE_KEY) || "simple");
            build();
        });
    }

    // 换图/换预设后重建(editor.loadGraph 会调用)
    function onGraphLoaded() { build(); }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
    return { build, onGraphLoaded, setMode, toggleMode, setDockOpen };
})();
