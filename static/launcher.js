// 引导页(#33 → #49 两级导航):打开网页先看到**功能分类**,点分类看**该类的模型**,
// 点模型进入仿真。加一个预设文件 = 多一个模型,不用改代码。
//
// 数据来源:服务器扫 graphs/preset_*.json → /api/presets。
// 第一级分类 = 预设里的 preset.group(缺省归"其他");第二级 = 组内模型卡;
// preset.order 决定组内顺序,preset.model 是第二级显示名(缺省用 name)。
//
// 对外 API 与旧版**完全一致**(show/hide/toggle/load/presets/fetchPresets),
// 因此 protocol.js / editor.js / preset_save.js / guided_editor.js 都不用改。
window.launcher = (function () {
    "use strict";

    const LAST_KEY = "mf_last_preset";
    const GROUPS_KEY = "mf_group_order";
    let presets = [];
    let opened = false;
    let view = { level: "groups", group: null };   // 当前层级
    let lastGroup = null;                          // 记住上次进的分类

    function el(id) { return document.getElementById(id); }

    async function fetchPresets() {
        try {
            presets = await fetch("/api/presets").then(r => r.json());
        } catch (e) {
            presets = [];
            window.uiLog && window.uiLog("warn", "presets_fetch", String(e));
        }
        // ⚠ /api/presets 目前只回 id/name/desc/sort/nodes/edges/lattice,不回 group/model/order
        //   (#49)→ 并行取每个预设的完整文档补齐这几个字段。待办:让 C++ 直接转发。
        if (presets.length && presets.some(p => !p.group)) {
            await Promise.all(presets.map(async (p) => {
                try {
                    const d = await fetch(`/api/preset?id=${encodeURIComponent(p.id)}`)
                        .then(r => r.json());
                    const m = (d && d.preset) || {};
                    p.group = m.group || p.group;
                    p.model = m.model || p.model;
                    p.order = (m.order !== undefined) ? m.order : p.order;
                } catch (e) { /* 单个失败不影响其它 */ }
            }));
        }
        return presets;
    }

    // ---- 分组 ----
    const GROUP_FALLBACK = "其他";
    function groupOf(p) { return (p.group && String(p.group).trim()) || GROUP_FALLBACK; }
    function groupList() {
        const map = new Map();
        for (const p of presets) {
            const g = groupOf(p);
            if (!map.has(g)) map.set(g, []);
            map.get(g).push(p);
        }
        // 分类顺序:自定义的 group_order 优先,其次是出现顺序
        let order = [];
        try { order = JSON.parse(localStorage.getItem(GROUPS_KEY) || "[]"); } catch (e) { order = []; }
        const keys = [...map.keys()];
        keys.sort((a, b) => {
            const ia = order.indexOf(a), ib = order.indexOf(b);
            if (ia >= 0 && ib >= 0) return ia - ib;
            if (ia >= 0) return -1;
            if (ib >= 0) return 1;
            if (a === GROUP_FALLBACK) return 1;
            if (b === GROUP_FALLBACK) return -1;
            return a.localeCompare(b);
        });
        return keys.map(k => ({ name: k, items: map.get(k).sort((a, b) =>
            (a.order || 100) - (b.order || 100) || String(a.name).localeCompare(String(b.name))) }));
    }

    // ---- 卡片 ----
    function card(p) {
        const b = document.createElement("button");
        b.className = "preset-card" + (p.custom ? " custom" : "");
        b.dataset.id = p.id;
        const last = localStorage.getItem(LAST_KEY);
        if (last && last === p.id) b.classList.add("last");
        b.innerHTML =
            `<div class="pc-title">${p.model || p.name}` +
            (last === p.id ? ` <span class="pc-chip">上次</span>` : "") + `</div>` +
            `<div class="pc-desc">${p.desc || ""}</div>` +
            `<div class="pc-meta">` +
            (p.custom ? `<span class="pc-chip">空白起步</span>`
                      : `<span class="pc-chip">${p.nodes} 节点 · ${p.edges} 边</span>` +
                        `<span class="pc-chip">点阵 ${p.lattice}</span>`) +
            `</div>`;
        b.onclick = () => load(p);
        return b;
    }

    function groupCard(g) {
        const b = document.createElement("button");
        b.className = "preset-card group-card";
        const last = lastGroup === g.name ? ` <span class="pc-chip">上次</span>` : "";
        b.innerHTML =
            `<div class="pc-title">${g.name}${last}</div>` +
            `<div class="pc-desc">${g.items.length} 个模型 · ` +
            g.items.slice(0, 3).map(p => p.model || p.name).join("、") +
            (g.items.length > 3 ? " …" : "") + `</div>` +
            `<div class="pc-meta"><span class="pc-chip">点击选择模型 →</span></div>`;
        b.onclick = () => { view = { level: "models", group: g.name }; lastGroup = g.name; render(); };
        return b;
    }

    function crumb() {
        let c = el("launcher-crumb");
        if (!c) {
            c = document.createElement("div");
            c.id = "launcher-crumb";
            const cards = el("launcher-cards");
            if (cards && cards.parentElement) cards.parentElement.insertBefore(c, cards);
        }
        return c;
    }

    function render() {
        const box = el("launcher-cards");
        if (!box) return;
        box.innerHTML = "";
        const groups = groupList();
        const hint = el("launcher-hint");
        const c = crumb();

        if (view.level === "models" && view.group) {
            const g = groups.find(x => x.name === view.group) || { items: [] };
            c.innerHTML =
                `<button id="launcher-back" class="crumb-btn">← 返回分类</button>` +
                `<span class="crumb-sep">/</span><span class="crumb-cur">${view.group}</span>` +
                `<span class="crumb-dim">（${g.items.length} 个模型）</span>`;
            const back = el("launcher-back");
            if (back) back.onclick = () => { view = { level: "groups", group: null }; render(); };
            for (const p of g.items) box.appendChild(card(p));
            if (hint) hint.textContent = "选择一个模型进入仿真 · 加模型只需在 graphs/ 放一个 preset_*.json";
            return;
        }

        // 第一级:功能分类 + 「全部预设」
        c.innerHTML = `<span class="crumb-cur">选择功能分类</span>` +
                      `<span class="crumb-dim">（共 ${presets.length} 个模型 / ${groups.length} 类）</span>`;
        for (const g of groups) box.appendChild(groupCard(g));
        const all = document.createElement("button");
        all.className = "preset-card group-card all";
        all.innerHTML = `<div class="pc-title">全部预设</div>` +
                        `<div class="pc-desc">不分分类,直接列出全部 ${presets.length} 个模型</div>` +
                        `<div class="pc-meta"><span class="pc-chip">熟练用户</span></div>`;
        all.onclick = () => { view = { level: "models", group: "__all__" }; render(); };
        box.appendChild(all);
        if (hint) hint.textContent = "点分类 → 选模型 → 进入仿真;加模型只需在 graphs/ 放一个 preset_*.json";
    }

    // 处理「全部预设」这个伪分类
    const _render = render;
    render = function () {
        if (view.level === "models" && view.group === "__all__") {
            const box = el("launcher-cards");
            if (box) {
                box.innerHTML = "";
                const c = crumb();
                c.innerHTML = `<button id="launcher-back" class="crumb-btn">← 返回分类</button>` +
                              `<span class="crumb-sep">/</span><span class="crumb-cur">全部预设</span>`;
                const back = el("launcher-back");
                if (back) back.onclick = () => { view = { level: "groups", group: null }; render(); };
                for (const p of presets) box.appendChild(card(p));
                return;
            }
        }
        _render();
    };

    async function load(p) {
        try {
            const doc = await fetch(`/api/preset?id=${encodeURIComponent(p.id)}`)
                .then(r => r.json());
            localStorage.setItem(LAST_KEY, p.id);
            // #49 把预设的 demo(重点参数白名单)交给引导模式;没有则清空
            window.__presetDemo = (doc && doc.demo) || null;
            window.editor.loadGraph(doc);          // 画布
            window.protocol.uploadGraph(doc);      // 服务器(烘焙 + 重建计划)
            hide();
            window.toast(`已载入预设:${p.name}`);
            window.uiLog("info", "preset_load", `载入预设 ${p.id}`,
                         { group: groupOf(p), nodes: (doc.nodes || []).length });
        } catch (e) {
            window.toast("预设载入失败: " + e);
        }
    }

    function injectStyle() {
        if (el("mf-launcher-nav-style")) return;
        const s = document.createElement("style");
        s.id = "mf-launcher-nav-style";
        s.textContent = `
            #launcher-crumb { margin: 0 0 10px; display: flex; align-items: center; gap: 8px;
                              font-size: .86rem; color: var(--dim); }
            #launcher-crumb .crumb-btn { background: #21262d; color: var(--text);
                border: 1px solid var(--border); border-radius: 4px; padding: 3px 10px;
                cursor: pointer; }
            #launcher-crumb .crumb-btn:hover { border-color: var(--accent); color: var(--accent); }
            #launcher-crumb .crumb-cur { color: var(--accent); font-weight: 700; }
            .preset-card.group-card { min-height: 96px; }
            .preset-card.group-card .pc-title { font-size: 1rem; }
            .preset-card.group-card.all { opacity: .85; }
        `;
        document.head.appendChild(s);
    }

    async function show() {
        opened = true;
        injectStyle();
        el("launcher").classList.remove("hidden");
        view = { level: "groups", group: null };     // 每次打开都从分类页开始
        await fetchPresets();
        render();
    }
    function hide() {
        opened = false;
        el("launcher").classList.add("hidden");
    }
    function toggle() { opened ? hide() : show(); }

    async function boot() {
        const skip = el("launcher-skip");
        if (skip) skip.onclick = () => hide();
        const btn = el("btn-presets");
        if (btn) btn.onclick = () => show();
        await show();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot);
    } else {
        boot();
    }
    return { show, hide, toggle, load, presets: () => presets, fetchPresets,
             // #49 供测试/外部使用
             groups: groupList, view: () => view,
             goto: (level, group) => { view = { level: level, group: group || null }; render(); } };
})();
