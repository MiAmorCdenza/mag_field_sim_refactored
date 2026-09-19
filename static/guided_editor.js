// 参数白名单编辑器(#47)—— 在简化面板里直接改"引导模式"白名单。
//
// 用户需求:"在简化面板中新增功能:可编辑参数白名单,方便我手动修改"。
// 做法:不在 JSON 里手改 —— 直接**从当前图列出所有节点**,勾选"这个节点显示 / 显示它哪几个参数"。
//
// 自包含附加件:回滚 = 删掉 index.html 里的 <script src="/guided_editor.js"></script>。
// 数据流:
//   勾选 → {title, nodes:[{type, params:[...]}]}
//     → localStorage["mf.guided.spec"](本机覆盖,刷新仍在)
//     → window.__GUIDED.setSpec(...) + simpleUI.build()(立即生效)
//   想随预设分发:点「复制 JSON」→ 贴进 graphs/preset_xxx.json 的 "demo" 字段
//
// 注解:为什么不直接写预设文件?保存接口目前只收整张图(exportGraph 不含 demo),
// 直接写会把讲解顺序丢掉。等接口支持"保留/合并 demo"后再开这个按钮(计划里已记录)。
(function () {
    "use strict";

    function el(id) { return document.getElementById(id); }
    function guided() { return window.__GUIDED || null; }

    function injectStyle() {
        if (el("mf-ge-style")) return;
        const s = document.createElement("style");
        s.id = "mf-ge-style";
        s.textContent = `
            #mf-ge-btn.on { background: #1d4f7c; color: #cfe3ff; }
            #mf-ge-mask { position: fixed; inset: 0; z-index: 70; display: none;
                          background: rgba(0,0,0,.45); align-items: center; justify-content: center; }
            #mf-ge-mask.open { display: flex; }
            #mf-ge-box { width: 560px; max-height: 80vh; display: flex; flex-direction: column;
                         background: #0f141b; border: 1px solid var(--border); border-radius: 6px;
                         color: var(--text); font-size: .8rem; }
            #mf-ge-head { padding: 10px 14px; border-bottom: 1px solid var(--border); }
            #mf-ge-head b { color: var(--accent); }
            #mf-ge-bar { display: flex; gap: 6px; padding: 8px 14px; flex-wrap: wrap;
                         border-bottom: 1px solid var(--border); }
            #mf-ge-list { flex: 1; overflow-y: auto; padding: 8px 14px; }
            #mf-ge-list .ge-node { border-bottom: 1px dashed var(--border); padding: 6px 0; }
            #mf-ge-list .ge-node > label { display: flex; align-items: center; gap: 6px; }
            #mf-ge-list .ge-params { margin: 4px 0 0 22px; display: flex; flex-wrap: wrap; gap: 4px 12px; }
            #mf-ge-list .ge-params label { color: var(--dim); }
            #mf-ge-list .ge-params label.on { color: var(--accent); }
            #mf-ge-foot { padding: 10px 14px; border-top: 1px solid var(--border);
                          display: flex; gap: 8px; align-items: center; }
            #mf-ge-msg { flex: 1; font-size: .74rem; color: var(--dim); }
            .mf-ge-hint { color: var(--dim); font-size: .72rem; }
        `;
        document.head.appendChild(s);
    }

    // 当前图里可调的东西:每个节点的 type + 该节点 schema 里的 inputs/params
    function graphNodeList() {
        const g = window.editor && window.editor.graph;
        if (!g || !g._nodes) return [];
        return g._nodes.filter(n => !n._isGhost && n._spec).map(n => {
            const spec = n._spec;
            const names = [];
            for (const k of Object.keys(spec.inputs || {})) {
                const inp = (n.inputs || []).find(i => i.name === k);
                if (inp && inp.link != null) continue;     // 已接线:值由上游决定
                names.push(k);
            }
            for (const k of Object.keys(spec.params || {})) names.push(k);
            return { node: n, type: spec.type, name: spec.name || spec.type,
                     id: n.id, title: n.title || "", keys: names };
        });
    }

    function curSpec() {
        const G = guided();
        return (G && G.raw) ? G.raw() : { title: "参数白名单", nodes: [] };
    }

    function buildList() {
        const box = el("mf-ge-list");
        box.innerHTML = "";
        const spec = curSpec();
        const entryFor = (t) => (spec.nodes || []).find(e => e.type === t);
        const list = graphNodeList();
        if (!list.length) {
            box.innerHTML = '<div class="mf-ge-hint">当前图没有节点(先在画布/预设里建图)</div>';
            return;
        }
        for (const it of list) {
            const e = entryFor(it.type);
            const on = !!e;
            const all = !e || !e.params || e.params.indexOf("*") >= 0;
            const wrap = document.createElement("div");
            wrap.className = "ge-node";
            const lab = document.createElement("label");
            const cb = document.createElement("input");
            cb.type = "checkbox";
            cb.checked = on;
            cb.dataset.type = it.type;
            cb.className = "ge-on";
            lab.appendChild(cb);
            const nm = document.createElement("span");
            nm.innerHTML = "<b>" + it.name + "</b> <span class='mf-ge-hint'>" +
                           it.type + (it.id ? " · " + it.id : "") + "(" + it.keys.length + " 项)</span>";
            lab.appendChild(nm);
            wrap.appendChild(lab);
            const ps = document.createElement("div");
            ps.className = "ge-params";
            for (const k of it.keys) {
                const l2 = document.createElement("label");
                const c2 = document.createElement("input");
                c2.type = "checkbox";
                c2.className = "ge-param";
                c2.dataset.type = it.type;
                c2.dataset.key = k;
                c2.checked = on && (all || e.params.indexOf(k) >= 0);
                c2.disabled = !on;
                l2.className = c2.checked ? "on" : "";
                l2.appendChild(c2);
                l2.appendChild(document.createTextNode(" " + k));
                ps.appendChild(l2);
            }
            wrap.appendChild(ps);
            box.appendChild(wrap);
        }
        // 节点勾选联动参数可用性
        box.querySelectorAll(".ge-on").forEach(cb => {
            cb.onchange = () => {
                box.querySelectorAll('.ge-param[data-type="' + cb.dataset.type + '"]')
                   .forEach(p => { p.disabled = !cb.checked; if (cb.checked) p.checked = true; });
                buildFromDom(false);
            };
        });
        box.querySelectorAll(".ge-param").forEach(p => {
            p.onchange = () => {
                p.parentElement.className = p.checked ? "on" : "";
                buildFromDom(false);
            };
        });
    }

    // 从 DOM 收集 → 写回 spec(apply=true 时立即生效)
    function buildFromDom(apply) {
        const nodes = [];
        const box = el("mf-ge-list");
        box.querySelectorAll(".ge-on").forEach(cb => {
            if (!cb.checked) return;
            const t = cb.dataset.type;
            const keys = [...box.querySelectorAll('.ge-param[data-type="' + t + '"]')]
                .filter(p => p.checked).map(p => p.dataset.key);
            const item = { type: t };
            if (keys.length) item.params = keys;          // 空 = 用 ["*"] 全显示
            else item.params = ["*"];
            nodes.push(item);
        });
        const spec = { title: (curSpec().title || "参数白名单"), nodes: nodes };
        const G = guided();
        if (G && G.setSpec) G.setSpec(spec, apply);
        return spec;
    }

    function apply() {
        buildFromDom(true);
        try { window.simpleUI && window.simpleUI.build(); } catch (e) { /* 面板未就绪 */ }
        setMsg("已应用(存本机 localStorage;刷新仍在)", "#7ee787");
    }
    function resetLocal() {
        try { localStorage.removeItem("mf.guided.spec"); } catch (e) { /* 忽略 */ }
        const G = guided();
        if (G && G.load) {
            G.load().then(() => { buildList(); try { window.simpleUI.build(); } catch (e) {} });
        }
        setMsg("已恢复内置清单(static/ui/demo_focus.json)", "#7ee787");
    }
    function copyJson() {
        const spec = buildFromDom(false);
        const txt = JSON.stringify(spec, null, 2);
        const done = () => setMsg("已复制 JSON —— 贴进 graphs/preset_xxx.json 的 \"demo\" 字段即可随预设分发", "#7ee787");
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(txt).then(done, () => { window.prompt("复制下面的 JSON:", txt); });
        } else {
            window.prompt("复制下面的 JSON:", txt);
        }
    }
    function setMsg(t, color) {
        const m = el("mf-ge-msg");
        if (!m) return;
        m.textContent = t || "";
        m.style.color = color || "var(--dim)";
    }

    function open() {
        ensureDialog();
        buildList();
        el("mf-ge-mask").classList.add("open");
    }
    function close() { el("mf-ge-mask").classList.remove("open"); }

    function ensureDialog() {
        if (el("mf-ge-mask")) return;
        const mask = document.createElement("div");
        mask.id = "mf-ge-mask";
        mask.innerHTML =
            '<div id="mf-ge-box">' +
            '<div id="mf-ge-head"><b>参数白名单</b> · 勾选"这个节点显示 / 显示它哪几个参数"' +
            '<div class="mf-ge-hint">不勾的节点与参数会在简化面板里隐藏(引导模式)。' +
            '「显示隐藏参数」勾上即全部恢复。</div></div>' +
            '<div id="mf-ge-bar">' +
            '<button id="mf-ge-all">全选</button>' +
            '<button id="mf-ge-none">全不选</button>' +
            '<button id="mf-ge-reset">恢复内置清单</button>' +
            '<button id="mf-ge-copy">复制 JSON</button>' +
            '</div>' +
            '<div id="mf-ge-list"></div>' +
            '<div id="mf-ge-foot"><span id="mf-ge-msg"></span>' +
            '<button id="mf-ge-apply" class="primary">应用</button>' +
            '<button id="mf-ge-close">关闭</button></div></div>';
        document.body.appendChild(mask);
        mask.addEventListener("click", e => { if (e.target === mask) close(); });
        el("mf-ge-close").onclick = close;
        el("mf-ge-apply").onclick = apply;
        el("mf-ge-reset").onclick = resetLocal;
        el("mf-ge-copy").onclick = copyJson;
        el("mf-ge-all").onclick = () => {
            el("mf-ge-list").querySelectorAll("input[type=checkbox]").forEach(c => {
                c.checked = true; c.disabled = false;
                if (c.parentElement && c.classList.contains("ge-param")) c.parentElement.className = "on";
            });
            buildFromDom(true);
        };
        el("mf-ge-none").onclick = () => {
            el("mf-ge-list").querySelectorAll(".ge-on").forEach(c => { c.checked = false; });
            el("mf-ge-list").querySelectorAll(".ge-param").forEach(c => { c.checked = false; });
            buildFromDom(true);
        };
        buildList();
    }

    function ensureButton() {
        const head = el("dock-head");
        if (!head || el("mf-ge-btn")) return;
        injectStyle();
        const b = document.createElement("button");
        b.id = "mf-ge-btn";
        b.textContent = "⚙";
        b.title = "编辑参数白名单(引导模式显示哪些节点/参数)";
        b.onclick = open;
        head.appendChild(b);
    }

    function init() { injectStyle(); ensureButton(); }
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else { init(); }
    window.addEventListener("load", () => setTimeout(init, 500));
    window.guidedEditor = { open, close, apply, resetLocal, copyJson, buildFromDom };
})();
