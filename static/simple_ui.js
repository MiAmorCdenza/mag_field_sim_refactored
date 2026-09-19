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
    let iconOf = {};         // 节点类型 → 像素图名(来自 /api/nodes 的 icon_img)
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
            for (const t of types) {
                groupOf[t.type] = t.category || "其它";
                if (t.icon_img) iconOf[t.type] = t.icon_img;
            }
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

    // 像素图优先(16x16 SVG,硬边像素风);没有图才回退节点规格里的 emoji
    function iconHtml(spec) {
        const img = iconOf[spec.type];
        if (img) {
            // onerror → 回退 emoji:服务器 MIME 不对或缺图标文件时不留破图
            // (实测踩过:200 但 Content-Type=text/html → <img> 拒绝渲染)
            const emo = (spec.icon || "•").replace(/"/g, "");
            return '<span class="dock-icon"><img src="/icons/' + img + '.svg" alt=""' +
                ' data-emoji="' + emo + '" onerror="simpleUI.iconFallback(this)"></span>';
        }
        return `<span class="dock-icon">${spec.icon || "•"}</span>`;
    }

    // 图标加载失败 → 换成 emoji(内联 onerror 调用)
    function iconFallback(el) {
        const s = document.createElement("span");
        s.className = "node-emoji";
        s.textContent = el.getAttribute("data-emoji") || "•";
        el.replaceWith(s);
    }

    // ---- 引导模式(#44 重写):现场演示只显示预先确定的节点/参数 ----
    // 上一版在 guided.js 里用 MutationObserver 包裹 build():apply() 每次重插提示行
    // → 触发自己 → 无限循环 → 页面"没有响应"。这一版**直接在 build() 里过滤**:
    // 节点级(不在白名单的节点根本不渲染)+ 参数级(生成的 .prop-row 只留白名单),
    // 全程不观察 DOM,结构上不可能自触发。
    const GUIDED = (function () {
        const KEY = "mf.guided";
        let on = localStorage.getItem(KEY) !== "0";        // 默认开启
        let spec = { title: "引导模式", nodes: [] };
        const entryOf = function (node) {
            const id = node.id || "";
            const type = (node._spec && node._spec.type) || "";
            const name = (node._spec && node._spec.name) || "";
            for (const e of (spec.nodes || [])) {
                if (e.id && e.id === id) return e;
                if (e.type && e.type === type) return e;
                if (e.name && e.name === name) return e;
            }
            return null;
        };
        const paramsOf = function (e) {
            return (!e || !e.params || e.params.indexOf("*") >= 0) ? null : e.params;
        };
        return {
            get on() { return on; },
            set: function (v) {
                on = !!v;
                localStorage.setItem(KEY, on ? "1" : "0");
            },
            load: function () {
                // 优先级:本机白名单覆盖(编辑器写的)→ 当前预设的 demo 字段 → 全局清单
                var local = null;
                try { local = JSON.parse(localStorage.getItem("mf.guided.spec") || "null"); }
                catch (e) { local = null; }
                if (local && local.nodes) { spec = local; return Promise.resolve(); }
                var gdoc = window.editor && window.editor.serverDoc;
                if (gdoc && gdoc.demo && gdoc.demo.nodes) { spec = gdoc.demo; return Promise.resolve(); }
                return fetch("/ui/demo_focus.json", { cache: "no-store" })
                    .then(function (r) { return r.ok ? r.json() : null; })
                    .then(function (j) { if (j) spec = j; })
                    .catch(function () { /* 没清单 → 不过滤 */ });
            },
            // 供白名单编辑器用:设置并立即生效(默认存 localStorage,不动预设文件)
            setSpec: function (s, persist) {
                spec = s || { title: "引导模式", nodes: [] };
                if (persist !== false) {
                    try { localStorage.setItem("mf.guided.spec", JSON.stringify(spec)); }
                    catch (e) { /* 配额满就算了 */ }
                }
            },
            raw: function () { return spec; },
            title: function () { return spec.title || "引导模式"; },
            allows: function (node) { return !on || !!entryOf(node); },
            // 参数行过滤:编辑器生成的 label 以参数名开头("输入 · dst" / "dst · 说明")
            filterRows: function (node, body) {
                if (!on) return;
                const keep = paramsOf(entryOf(node));
                if (!keep) return;
                const rows = body.querySelectorAll(".prop-row");
                for (const row of rows) {
                    const lab = row.querySelector("label");
                    if (!lab) continue;
                    let t = (lab.textContent || "").trim();
                    if (t.indexOf("输入 · ") === 0) t = t.slice(4);
                    const cands = new Set();
                    t.split(" · ")[0].split(/\s+/).forEach(function (w) { if (w) cands.add(w); });
                    (t.match(/[A-Za-z_][A-Za-z0-9_]*/g) || []).forEach(function (w) { cands.add(w); });
                    // #54 标签可能是「中文名 变量名」,也可能是老的「输入 · dst」形式
                    // → 取所有候选词再比对;否则中文名一上,白名单里的变量名再也匹配不到
                    // → 参数会被**全部隐藏**(实测踩过:说明区在、参数一个不剩)。
                    let hit = false;
                    for (const k of keep) { if (cands.has(k)) { hit = true; break; } }
                    row.style.display = hit ? "" : "none";
                }
            },
        };
    })();
    window.__GUIDED = GUIDED;   // 供参数白名单编辑器读写(localStorage 覆盖)
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
            if (!GUIDED.allows(n)) continue;      // #44 引导模式:非重点节点不渲染
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
                    iconHtml(node._spec) +
                    `<span class="dock-name">${node._spec.name || node._spec.type}</span>` +
                    `<span class="dock-id">${node.id}</span>`;
                const body = document.createElement("div");
                body.className = "dock-node-body";
                // 惰性构建:展开时才生成控件(节点多也不拖慢面板)
                const fill = () => {
                    if (body.childElementCount) return;
                    try {
                        window.editor.buildParamsInto(node, body);
                        GUIDED.filterRows(node, body);   // #44 参数级过滤(白名单外的行隐藏)
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
        // #44 引导模式:加载清单 + Dock 头部开关(默认开启,状态记忆在 localStorage)
        const css = document.createElement("style");
        css.textContent = "#dock-guided.on{background:#1d4f7c;color:#cfe3ff}" +
            ".mf-guided-note{margin:2px 4px 8px;padding:3px 6px;border-radius:4px;" +
            "background:rgba(45,106,159,.18);border:1px solid #1d4f7c;color:#9ec7ef;font-size:.72rem}";
        document.head.appendChild(css);
        GUIDED.load().then(() => { try { build(); } catch (e) { /* 图未载入 */ } });
        const head = document.getElementById("dock-head");
        if (head && !document.getElementById("dock-guided")) {
            const b = document.createElement("button");
            b.id = "dock-guided";
            b.textContent = "🎯";
            b.title = "引导模式:只显示现场演示预先确定的节点与参数(默认开启)";
            b.onclick = () => {
                GUIDED.set(!GUIDED.on);
                b.classList.toggle("on", GUIDED.on);
                build();
            };
            b.classList.toggle("on", GUIDED.on);
            head.appendChild(b);
        }
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
    return { build, onGraphLoaded, setMode, toggleMode, setDockOpen, iconFallback };
})();
