// 简化面板的「引导模式」(#44)—— 现场演示时只露出预先确定的节点/参数。
//
// 用户要求:在简化面板的参数调节框外面套一层引导式交互,可手动开关、**默认开启**;
// 开启时**只展示**预先确定(现场演示要用)的节点参数,或其中部分参数。
//
// 为什么单独一个文件:与 splitter.js 同样属于可整体回滚的实验/附加件 ——
//   回滚 = 删掉 index.html 里的 <script src="/guided.js"></script>。
// 实现方式:**包裹** window.simpleUI.build(不改 simple_ui.js 一行):
//   1) 原始 build 渲染完整 Dock;
//   2) 本层按 ui/demo_focus.json 隐藏非重点节点、并给空组收尾;
//   3) 参数行是"展开时才惰性生成"的 → 用 MutationObserver 在生成后按白名单隐藏。
// 白名单来源:先取当前图的 demo 字段(预设可自带),否则 /ui/demo_focus.json。
(function () {
    "use strict";
    const KEY = "mf.guided";
    let on = localStorage.getItem(KEY) !== "0";      // 默认开启
    let spec = null;                                  // {title, nodes:[{type,id,params}]}
    let graphDemo = null;                             // 当前图自带的 demo 覆盖

    function injectStyle() {
        if (document.getElementById("mf-guided-style")) return;
        const s = document.createElement("style");
        s.id = "mf-guided-style";
        s.textContent = `
            #mf-guided-btn.on { background: #1d4f7c; color: #cfe3ff; }
            .mf-guided-note {
                margin: 2px 4px 8px; padding: 4px 7px; border-radius: 4px;
                background: rgba(45, 106, 159, 0.18); border: 1px solid #1d4f7c;
                color: #9ec7ef; font-size: 0.72rem; line-height: 1.4;
            }
            .mf-guided-note b { color: #cfe3ff; }
        `;
        document.head.appendChild(s);
    }

    // ---- 白名单判定 ----
    function entryFor(node) {
        if (!spec) return null;
        const id = node.id || "";
        const type = (node._spec && node._spec.type) || "";
        const name = (node._spec && node._spec.name) || "";
        for (const e of (spec.nodes || [])) {
            if (e.id && e.id === id) return e;
            if (e.type && e.type === type) return e;
            if (e.name && e.name === name) return e;
        }
        return null;
    }
    function paramsOf(entry) {
        if (!entry || !entry.params || entry.params.includes("*")) return null;  // null = 全部
        return entry.params;
    }

    // 从参数行读它的参数名(编辑器生成的 label 以参数名开头:"输入 · dst" / "dst · 说明")
    function rowParamName(row) {
        const lab = row.querySelector("label");
        if (!lab) return "";
        let t = (lab.textContent || "").trim();
        if (t.startsWith("输入 · ")) t = t.slice(4);
        return t.split(" · ")[0].trim();
    }

    function filterRows(body, keep) {
        if (!keep) return;
        for (const row of body.querySelectorAll(".prop-row")) {
            const n = rowParamName(row);
            if (!n) continue;
            row.style.display = keep.includes(n) ? "" : "none";
        }
    }

    function apply() {
        const box = document.getElementById("dock-body");
        const head = document.getElementById("dock-head");
        if (!box) return;

        // 开关按钮(插到 Dock 头部)
        if (head && !document.getElementById("mf-guided-btn")) {
            const b = document.createElement("button");
            b.id = "mf-guided-btn";
            b.title = "引导模式:只显示现场演示重点参数(默认开启)";
            b.textContent = "🎯";
            b.onclick = () => setOn(!on);
            head.insertBefore(b, head.firstChild ? head.firstChild.nextSibling : null);
        }
        const btn = document.getElementById("mf-guided-btn");
        if (btn) btn.classList.toggle("on", on);

        // 之前留下的隐藏/提示先清掉(引导关掉时恢复原样)
        box.querySelectorAll(".mf-guided-note").forEach(e => e.remove());
        box.querySelectorAll(".dock-node").forEach(e => { e.style.display = ""; });
        box.querySelectorAll(".dock-group").forEach(e => { e.style.display = ""; });
        box.querySelectorAll(".dock-node-body .prop-row").forEach(e => { e.style.display = ""; });
        if (!on) return;

        const nodes = (window.editor && window.editor.graph)
            ? window.editor.graph._nodes.filter(n => !n._isGhost && n._spec) : [];
        if (!spec || !nodes.length) return;

        let shown = 0;
        for (const item of box.querySelectorAll(".dock-node")) {
            const idEl = item.querySelector(".dock-id");
            const id = idEl ? idEl.textContent.trim() : "";
            const node = nodes.find(n => String(n.id) === id ||
                                         (n.properties && n.properties.spec_id === id)) ||
                         nodes.find(n => (n._spec.name || "") ===
                             (item.querySelector(".dock-name") || {}).textContent);
            const entry = node ? entryFor(node) : null;
            if (!entry) { item.style.display = "none"; continue; }
            shown++;
            const body = item.querySelector(".dock-node-body");
            const keep = paramsOf(entry);
            if (body && body.childElementCount) filterRows(body, keep);
            if (keep && body) body.dataset.mfKeep = keep.join("|");
            if (entry.note && !item.querySelector(".mf-guided-hint")) {
                const h = document.createElement("div");
                h.className = "mf-guided-note mf-guided-hint";
                h.innerHTML = "<b>重点</b> · " + entry.note;
                const bodyEl = item.querySelector(".dock-node-body");
                if (bodyEl) bodyEl.parentElement.insertBefore(h, bodyEl);
            }
            // 重点节点默认展开,演示时一眼看到
            const rowBtn = item.querySelector(".dock-node-head");
            const bodyEl = item.querySelector(".dock-node-body");
            if (rowBtn && bodyEl && !bodyEl.classList.contains("open")) rowBtn.click();
        }
        // 空分组收起
        for (const g of box.querySelectorAll(".dock-group")) {
            const any = [...g.querySelectorAll(".dock-node")]
                .some(n => n.style.display !== "none");
            if (!any) g.style.display = "none";
        }
        // 顶部说明
        const note = document.createElement("div");
        note.className = "mf-guided-note";
        note.innerHTML = "🎯 <b>" + (spec.title || "引导模式") + "</b> · 只显示重点参数(" +
            shown + " 个节点);点 🎯 关闭可看全部。清单:<code>ui/demo_focus.json</code>";
        box.insertBefore(note, box.firstChild);
    }

    function setOn(v) {
        on = !!v;
        localStorage.setItem(KEY, on ? "1" : "0");
        apply();
    }

    // 监听参数行的惰性生成(展开节点时才创建)→ 生成后立刻按白名单过滤
    function observe() {
        const box = document.getElementById("dock-body");
        if (!box || box.dataset.mfGuidedObs) return;
        box.dataset.mfGuidedObs = "1";
        new MutationObserver(() => { if (on) apply(); })
            .observe(box, { childList: true, subtree: true });
    }

    async function loadSpec() {
        try {
            const r = await fetch("/ui/demo_focus.json", { cache: "no-store" });
            if (r.ok) spec = await r.json();
        } catch (e) { /* 没有清单文件 → 引导模式不隐藏任何东西 */ }
        if (!spec) spec = { title: "引导模式", nodes: [] };
    }

    function wrap() {
        if (!window.simpleUI || window.simpleUI.__guided) return false;
        const orig = window.simpleUI.build;
        window.simpleUI.build = function () {
            const r = orig.apply(this, arguments);
            try { observe(); apply(); } catch (e) { console.warn("[guided]", e); }
            return r;
        };
        window.simpleUI.__guided = true;
        // 预设自带 demo 字段时优先(切换预设即换重点)
        window.addEventListener("mf-graph-loaded", (e) => {
            const g = (e && e.detail) || null;
            graphDemo = g && g.demo ? g.demo : null;
            if (graphDemo) spec = graphDemo;
            apply();
        });
        return true;
    }

    async function init() {
        injectStyle();
        await loadSpec();
        if (!wrap()) setTimeout(wrap, 300);
        observe();
        apply();
    }
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else { init(); }
    window.addEventListener("load", () => setTimeout(() => { wrap(); apply(); }, 400));
    // 暴露给控制台/自动化测试
    window.guidedMode = { isOn: () => on, setOn, apply, get spec() { return spec; } };
})();
