// 引导页(#33):打开网页先看到仿真标题 + 预设卡片 + 「自定义」入口。
//
// 预设**自动发现**:服务器扫 graphs/preset_*.json 返回列表(见 /api/presets),
// 前端用 CSS grid 自动排列 —— 工程里加一个预设文件就多一张卡片,不用改代码。
// 卡片来源:文件里的 meta 块(preset.name/desc/sort/custom),缺省用文件名。
window.launcher = (function () {
    "use strict";

    const LAST_KEY = "mf_last_preset";
    let presets = [];
    let opened = false;

    function el(id) { return document.getElementById(id); }

    async function fetchPresets() {
        try {
            presets = await fetch("/api/presets").then(r => r.json());
        } catch (e) {
            presets = [];
            window.uiLog && window.uiLog("warn", "presets_fetch", String(e));
        }
        return presets;
    }

    function card(p) {
        const b = document.createElement("button");
        b.className = "preset-card" + (p.custom ? " custom" : "");
        b.dataset.id = p.id;
        const last = localStorage.getItem(LAST_KEY);
        if (last && last === p.id) b.classList.add("last");
        b.innerHTML =
            `<div class="pc-title">${p.name}` +
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

    async function load(p) {
        try {
            const doc = await fetch(`/api/preset?id=${encodeURIComponent(p.id)}`)
                .then(r => r.json());
            localStorage.setItem(LAST_KEY, p.id);
            window.editor.loadGraph(doc);          // 画布
            window.protocol.uploadGraph(doc);      // 服务器(烘焙 + 重建计划)
            hide();
            window.toast(`已载入预设:${p.name}`);
            window.uiLog("info", "preset_load", `载入预设 ${p.id}`,
                         { nodes: (doc.nodes || []).length });
        } catch (e) {
            window.toast("预设载入失败: " + e);
        }
    }

    function render() {
        const box = el("launcher-cards");
        if (!box) return;
        box.innerHTML = "";
        for (const p of presets) box.appendChild(card(p));
        const hint = el("launcher-hint");
        if (hint) {
            hint.textContent = presets.length
                ? `共 ${presets.length} 个预设 · 加预设只需在 graphs/ 放一个 preset_*.json`
                : "未发现预设文件(graphs/preset_*.json)";
        }
    }

    async function show() {
        opened = true;
        el("launcher").classList.remove("hidden");
        await fetchPresets();
        render();
    }
    function hide() {
        opened = false;
        el("launcher").classList.add("hidden");
    }
    function toggle() { opened ? hide() : show(); }

    // 首屏即显示;点「跳过」保留服务器当前的图(重新打开页面不想换图时用)
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
    return { show, hide, toggle, load, presets: () => presets };
})();
