// 节点编辑器:注册表驱动的 LiteGraph 画布 + 属性面板 + 图 JSON 双向映射。
window.editor = (function () {
    "use strict";

    // 端口类型 → 连线颜色(LiteGraph 以"类型=颜色"实现类型化连线)
    const TYPE_COLORS = {
        "scalar": "#9bd4ff", "int": "#9bd4ff", "bool": "#9bd4ff",
        "enum": "#9bd4ff", "string": "#9bd4ff",
        "vector_field": "#ff9b6a", "scalar_field": "#ffd36a",
        "particle_buffer": "#7bef7b", "field_table": "#6ad4ff", "geometry": "#e79bff",
        "any": "#e6e6ff",
    };

    let registry = [];          // /api/nodes 描述数组
    const specByType = {};

    const graph = new LGraph();
    const canvasEl = document.getElementById("editor-canvas");
    // 画布背板尺寸 = 元素实际尺寸(否则默认 300×150 被 CSS 拉伸 → 节点巨大)
    if (canvasEl.clientWidth > 0 && canvasEl.clientHeight > 0) {
        canvasEl.width = canvasEl.clientWidth;
        canvasEl.height = canvasEl.clientHeight;
    }
    const canvas = new LGraphCanvas(canvasEl, graph);
    canvas.background_image = "";
    window.addEventListener("resize", () => {
        canvasEl.width = canvasEl.clientWidth;
        canvasEl.height = canvasEl.clientHeight;
        if (typeof canvas.resize === "function") canvas.resize();
        canvas.setDirty(true, true);
    });

    // ---------- 节点类型注册 ----------
    // 渲染域节点专属色(右栏渲染管线视觉区分)
    const RENDER_NODE_COLOR = "#4a3a6a";

    function makeNodeClass(spec) {
        function T(title) {
            // v0.4 LiteGraph 创建实例时不会调用基类构造器,必须显式初始化:
            // 否则 this.flags/inputs/outputs/properties 均为 undefined,
            // 绘制循环读 node.flags.collapsed 每帧抛错、节点永不渲染。
            LGraphNode.call(this, title || "");
            this.properties = {};
            for (const [pname, port] of Object.entries(spec.inputs)) {
                this.addInput(pname, TYPE_COLORS[port.ptype] || "#888");
                this.properties["in:" + pname] = port.default;
            }
            for (const [oname, otype] of Object.entries(spec.outputs)) {
                this.addOutput(oname, TYPE_COLORS[otype] || "#888");
            }
            for (const [k, p] of Object.entries(spec.params)) {
                this.properties[k] = p.default;
            }
            this.properties.spec_type = spec.type;
            this._spec = spec;
            if (spec.domain === "render") {
                this.color = RENDER_NODE_COLOR;
                this.bgcolor = "#241d33";
            }
        }
        T.title = spec.name || spec.type;
        T.desc = spec.category;
        return T;
    }

    function initRegistry(types) {
        registry = types;
        for (const spec of types) {
            specByType[spec.type] = spec;
            LiteGraph.registerNodeType(spec.type, makeNodeClass(spec));
        }
    }

    // ---------- 图 JSON ↔ LiteGraph ----------
    function exportGraph() {
        const nodes = [];
        const idMap = {};
        for (const n of graph._nodes) {
            // 优先保留原 JSON id(loadGraph 记录);新建节点用 "n"+数字
            const jsonId = n.properties.json_id || "n" + n.id;
            idMap[n.id] = jsonId;
            const params = {};
            const inputDefaults = {};
            for (const [k, v] of Object.entries(n.properties)) {
                if (k === "spec_type" || k === "json_id") continue;
                if (k.startsWith("in:")) inputDefaults[k.slice(3)] = v;
                else params[k] = v;
            }
            nodes.push({
                id: jsonId, type: n.properties.spec_type,
                params, input_defaults: inputDefaults,
                pos: [Math.round(n.pos[0]), Math.round(n.pos[1])],
            });
        }
        const edges = [];
        // v0.4 的 graph.links 是对象(按链接 id 键控),用 Object.values 迭代
        for (const link of Object.values(graph.links || {})) {
            const from = graph._nodes.find(x => x.id === link.origin_id);
            const to = graph._nodes.find(x => x.id === link.target_id);
            if (!from || !to) continue;
            edges.push({
                from: [idMap[from.id], from.outputs[link.origin_slot].name],
                to: [idMap[to.id], to.inputs[link.target_slot].name],
            });
        }
        let outputs = {};
        try { outputs = JSON.parse(document.getElementById("outputs-json").value || "{}"); }
        catch (e) { window.toast("输出槽位 JSON 无效: " + e.message); }
        return { version: 1, lattice: { preset: "coarse" }, nodes, edges, outputs };
    }

    function loadGraph(doc) {
        try {
            graph.clear();
            const idToNode = {};
            for (const nd of doc.nodes) {
                const cls = LiteGraph.registered_node_types[nd.type];
                if (!cls) { console.warn("未知节点类型:", nd.type); continue; }
                const node = new cls();
                // 参数与输入默认值
                const props = Object.assign({}, nd.params || {});
                for (const [k, v] of Object.entries(nd.input_defaults || {})) props["in:" + k] = v;
                props.spec_type = nd.type;
                props.json_id = nd.id;  // 保留原图 id,导出时沿用(输出槽引用稳定)
                node.properties = props;
                node.pos = nd.pos || [0, 0];
                graph.add(node);
                idToNode[nd.id] = node;
            }
            for (const e of doc.edges || []) {
                const from = idToNode[e.from[0]];
                const to = idToNode[e.to[0]];
                if (!from || !to) continue;
                const oi = from.outputs.findIndex(o => o.name === e.from[1]);
                const ii = to.inputs.findIndex(i => i.name === e.to[1]);
                if (oi >= 0 && ii >= 0) from.connect(oi, to, ii);
            }
            document.getElementById("outputs-json").value =
                JSON.stringify(doc.outputs || {}, null, 2);
            // 全部节点缺位置时(如内置默认图)自动做层次化排布
            if (doc.nodes.length &&
                doc.nodes.every(nd => !nd.pos ||
                    (nd.pos[0] === 0 && nd.pos[1] === 0))) {
                autoLayout();
            }
            canvas.setDirty(true, true);
        } catch (err) {
            window.toast("loadGraph 错误: " + err.message + "\n" + (err.stack || ""));
            console.error(err);
        }
    }

    // ---------- 属性面板 ----------
    let selectedNode = null;

    function widget(spec, key, value, onChange) {
        const row = document.createElement("div");
        row.className = "prop-row";
        const label = document.createElement("label");
        label.textContent = key;
        row.appendChild(label);

        const valSpan = document.createElement("span");
        valSpan.className = "val";

        if (spec.ptype === "bool") {
            const cb = document.createElement("input");
            cb.type = "checkbox";
            cb.checked = !!value;
            cb.onchange = () => onChange(cb.checked);
            row.appendChild(cb);
        } else if (spec.ptype === "enum" && spec.choices) {
            const sel = document.createElement("select");
            for (const c of spec.choices) {
                const o = document.createElement("option");
                o.value = c; o.textContent = c;
                if (c === value) o.selected = true;
                sel.appendChild(o);
            }
            sel.onchange = () => onChange(sel.value);
            row.appendChild(sel);
        } else if ((spec.ptype === "scalar" || spec.ptype === "int") &&
                   spec.min !== null && spec.min !== undefined &&
                   spec.max !== null && spec.max !== undefined) {
            const slider = document.createElement("input");
            slider.type = "range";
            slider.min = spec.min; slider.max = spec.max;
            slider.step = spec.ptype === "int" ? 1 : (spec.max - spec.min) / 200;
            slider.value = value;
            valSpan.textContent = value;
            row.appendChild(valSpan);
            slider.oninput = () => { valSpan.textContent = Number(slider.value); };
            slider.onchange = () => onChange(Number(slider.value));
            row.appendChild(slider);
        } else if (spec.ptype === "string") {
            const t = document.createElement("input");
            t.type = "text"; t.value = value;
            t.onchange = () => onChange(t.value);
            row.appendChild(t);
        } else {
            const num = document.createElement("input");
            num.type = "number";
            num.step = spec.ptype === "int" ? 1 : "any";
            num.value = value;
            num.onchange = () => onChange(Number(num.value));
            row.appendChild(num);
        }
        return row;
    }

    function renderProps(node) {
        const body = document.getElementById("props-body");
        body.innerHTML = "";
        document.getElementById("props-node").textContent =
            node ? `${node._spec.name || node.properties.spec_type} [${node.id}]` : "";
        if (!node) {
            body.innerHTML = '<div class="hint">点击画布中的节点编辑其参数。</div>';
            return;
        }
        const spec = node._spec;

        // 未连线的输入端口(默认值 = 参数)
        for (const [pname, port] of Object.entries(spec.inputs)) {
            const input = node.inputs.find(i => i.name === pname);
            if (input && input.link != null) continue;  // 已连线:由上游驱动
            body.appendChild(widget(
                port, "输入 · " + pname,
                node.properties["in:" + pname] ?? port.default,
                v => {
                    node.properties["in:" + pname] = v;
                    window.protocol.sendParam(node.properties.spec_type, node, pname, v);
                }));
        }
        // params
        for (const [k, p] of Object.entries(spec.params)) {
            body.appendChild(widget(p, k, node.properties[k] ?? p.default,
                v => {
                    node.properties[k] = v;
                    window.protocol.sendParam(node.properties.spec_type, node, k, v);
                }));
        }

        // ---- 渲染节点:内联代码编辑器 + 参数下发 ----
        const codePanel = document.getElementById("code-editor");
        if (spec.domain === "render" &&
            spec.type !== "render_pipeline_start") {
            codePanel.classList.remove("hidden");
            const codeEl = document.getElementById("code-text");
            codeEl.value = node.properties.code || renderItemTemplate(spec);
            document.getElementById("code-node").textContent =
                `${node.properties.json_id || "n" + node.id} [${spec.type}]`;
            // 参数下发到渲染宿主(颜色/可见性/尺寸等)
            pushRenderParams(node);
        } else {
            codePanel.classList.add("hidden");
        }
    }

    // 内联渲染项代码模板
    function renderItemTemplate(spec) {
        return `// ${spec.name}(内联渲染项插件)
// 可用:registerRenderItem / THREE / host
registerRenderItem({
    id: "${spec.type}",          // 引擎会强制使用节点 id
    layer: 1,
    subscribes: [],              // 例: ["geometry:field_lines"]
    setup(scene, three) {
        this.three = three;
        this.group = new three.Group();
        scene.add(this.group);
        // 在此创建几何/材质...
    },
    onData(frame, meta) {
        // 数据帧到达时更新
    },
    onParam(params) {
        // 节点参数(颜色/可见性/...)变更
    },
    dispose() {
        this.group.parent && this.group.parent.remove(this.group);
    },
});
`;
    }

    // 渲染节点参数 → 渲染宿主(按节点 json id 路由)
    function pushRenderParams(node) {
        const itemId = node.properties.json_id || "n" + node.id;
        const params = {};
        for (const [k, v] of Object.entries(node.properties)) {
            if (k === "spec_type" || k === "json_id" || k.startsWith("in:")) continue;
            params[k] = v;
        }
        if (window.renderHost) window.renderHost.applyParams(itemId, params);
    }

    // 内联代码应用
    function applyInlineCode() {
        if (!selectedNode) return;
        const code = document.getElementById("code-text").value;
        const itemId = selectedNode.properties.json_id || "n" + selectedNode.id;
        try {
            window.renderRegistry.compileInline(itemId, code);
            selectedNode.properties.code = code;
            pushRenderParams(selectedNode);
            window.toast("✅ 内联渲染项已应用(随图 JSON 持久化)");
        } catch (e) {
            window.toast("❌ 内联代码编译失败: " + e.message);
        }
    }

    function resetInlineCode() {
        if (!selectedNode) return;
        document.getElementById("code-text").value =
            selectedNode.properties.code ||
            renderItemTemplate(selectedNode._spec);
    }

    canvas.onNodeSelected = (node) => { selectedNode = node; renderProps(node); };
    canvas.onNodeDeselected = () => { selectedNode = null; renderProps(null); };

    // ---------- 节点面板(v0.4 LiteGraph 无内置 showSearchTypes) ----------
    let paletteVisible = false;

    function renderPalette(filter) {
        const list = document.getElementById("palette-list");
        list.innerHTML = "";
        const kw = (filter || "").trim().toLowerCase();
        for (const spec of registry) {
            const hay = (spec.name + " " + spec.type + " " + spec.category).toLowerCase();
            if (kw && !hay.includes(kw)) continue;
            const item = document.createElement("button");
            item.className = "palette-item";
            item.textContent = `${spec.icon || "⬡"} ${spec.name} · ${spec.category}`;
            item.onclick = () => {
                hidePalette();
                const cls = LiteGraph.registered_node_types[spec.type];
                if (!cls) return;
                const node = new cls();
                const cx = canvas.ds.offset[0] + canvas.ds.scale * (canvas.canvas.width / 2);
                const cy = canvas.ds.offset[1] + canvas.ds.scale * (canvas.canvas.height / 2);
                node.pos = [cx - 70, cy - 20];
                graph.add(node);
                canvas.setDirty(true, true);
                window.toast(`已添加节点: ${spec.name}`);
            };
            list.appendChild(item);
        }
    }

    function showPalette() {
        paletteVisible = true;
        document.getElementById("palette").classList.remove("hidden");
        document.getElementById("palette-filter").value = "";
        renderPalette("");
        document.getElementById("palette-filter").focus();
    }
    function hidePalette() {
        paletteVisible = false;
        document.getElementById("palette").classList.add("hidden");
    }

    // ---------- 层次化自动排布(与引擎同算法) ----------
    function autoLayout() {
        const gapX = 240, gapY = 110;
        const nodes = graph._nodes;
        if (!nodes.length) return;
        const domainOf = n => n._spec?.domain || "field";
        const renderNodes = nodes.filter(n => domainOf(n) === "render");
        const dataNodes = nodes.filter(n => domainOf(n) !== "render");

        const adj = {};
        nodes.forEach(n => { adj[n.id] = []; });
        for (const link of Object.values(graph.links || {})) {
            adj[link.origin_id].push(link.target_id);
        }

        // ---- 数据域:拓扑深度定列 ----
        const indeg = {};
        dataNodes.forEach(n => { indeg[n.id] = 0; });
        for (const link of Object.values(graph.links || {})) {
            if (dataNodes.some(n => n.id === link.origin_id) &&
                dataNodes.some(n => n.id === link.target_id)) {
                indeg[link.target_id]++;
            }
        }
        const depth = {};
        const queue = dataNodes.filter(n => indeg[n.id] === 0);
        queue.forEach(n => { depth[n.id] = 0; });
        while (queue.length) {
            const n = queue.shift();
            for (const m of adj[n.id]) {
                if (!(m in indeg)) continue;
                depth[m] = Math.max(depth[m] ?? -1, depth[n.id] + 1);
                if (--indeg[m] === 0) queue.push(nodes.find(x => x.id === m));
            }
        }
        dataNodes.forEach(n => { depth[n.id] = depth[n.id] ?? 0; });
        // 汇节点(无下游)统一钉到最右列:终端对齐
        const sinks = dataNodes.filter(n => !adj[n.id].some(m => m in indeg));
        if (sinks.length) {
            const maxd = Math.max(...Object.values(depth));
            sinks.forEach(n => { depth[n.id] = maxd; });
        }
        const cols = {};
        dataNodes.forEach(n => { (cols[depth[n.id]] ||= []).push(n); });
        for (const d in cols) {
            cols[d].sort((a, b) => {
                const ups = x => Object.values(graph.links || {})
                    .filter(l => l.target_id === x.id && depth[l.origin_id] !== undefined);
                const bary = x => {
                    const u = ups(x);
                    return u.length
                        ? u.reduce((s, l) => s + depth[l.origin_id], 0) / u.length
                        : -1;
                };
                return bary(a) - bary(b);
            });
        }
        const connected = new Set();
        for (const l of Object.values(graph.links || {})) {
            connected.add(l.origin_id); connected.add(l.target_id);
        }
        const orphans = dataNodes.filter(n => !connected.has(n.id));
        const maxCol = Math.max(1, ...Object.values(cols).map(c => c.length));
        let x = 0;
        for (const d of Object.keys(cols).sort((a, b) => a - b)) {
            const col = cols[d];
            const y0 = 60 + ((maxCol - col.length) / 2) * gapY;
            col.forEach((n, i) => { n.pos = [x, y0 + i * gapY]; });
            x += gapX;
        }
        orphans.forEach((n, i) => { n.pos = [x, 60 + i * gapY]; });
        if (orphans.length) x += gapX;

        // ---- 渲染域:右侧单列垂直链(起始节点在链顶) ----
        const chain = [];
        const seen = new Set();
        const starts = renderNodes.filter(
            n => (n._spec?.type || n.properties.spec_type) === "render_pipeline_start");
        const q = starts.length ? [...starts] : (renderNodes.length ? [renderNodes[0]] : []);
        while (q.length) {
            const n = q.shift();
            if (seen.has(n.id)) continue;
            seen.add(n.id);
            chain.push(n);
            for (const m of adj[n.id]) {
                if (renderNodes.some(r => r.id === m) && !seen.has(m)) q.push(
                    renderNodes.find(r => r.id === m));
            }
        }
        renderNodes.forEach(n => { if (!seen.has(n.id)) chain.push(n); });
        chain.forEach((n, i) => { n.pos = [x, 60 + i * gapY]; });

        canvas.setDirty(true, true);
        window.toast("已自动排布(场左→粒子中→渲染右,渲染域垂直链)");
    }

    // ---------- 事件绑定 ----------
    document.getElementById("btn-add-node").onclick = showPalette;
    document.getElementById("btn-layout").onclick = autoLayout;
    document.getElementById("btn-code-apply").onclick = applyInlineCode;
    document.getElementById("btn-code-reset").onclick = resetInlineCode;
    document.getElementById("palette-filter").addEventListener("input",
        (e) => renderPalette(e.target.value));
    document.getElementById("btn-upload").onclick = () => window.protocol.uploadGraph(exportGraph());
    document.getElementById("btn-reset").onclick = () => window.protocol.resetToServer();
    document.getElementById("btn-respawn").onclick = () => window.protocol.respawn();

    return { initRegistry, loadGraph, exportGraph, canvas, graph };
})();
