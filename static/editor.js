// 节点编辑器:注册表驱动的 LiteGraph 画布 + 属性面板 + 图 JSON 双向映射。
window.editor = (function () {
    "use strict";

    // 端口类型 → 连线颜色(LiteGraph 以"类型=颜色"实现类型化连线)
    const TYPE_COLORS = {
        "scalar": "#9bd4ff", "int": "#9bd4ff", "bool": "#9bd4ff",
        "enum": "#9bd4ff", "string": "#9bd4ff",
        "vector_field": "#ff9b6a", "scalar_field": "#ffd36a",
        "particle_buffer": "#7bef7b", "field_table": "#6ad4ff", "geometry": "#e79bff",
    };

    let registry = [];          // /api/nodes 描述数组
    const specByType = {};

    const graph = new LGraph();
    const canvas = new LGraphCanvas("#editor-canvas", graph);
    canvas.background_image = "";

    // ---------- 节点类型注册 ----------
    function makeNodeClass(spec) {
        function T() {
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
            const jsonId = "n" + n.id;
            idMap[n.id] = jsonId;
            const params = {};
            const inputDefaults = {};
            for (const [k, v] of Object.entries(n.properties)) {
                if (k === "spec_type") continue;
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
        for (const link of graph.links || []) {
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
        canvas.setDirty(true, true);
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
    }

    canvas.onNodeSelected = (node) => { selectedNode = node; renderProps(node); };
    canvas.onNodeDeselected = () => { selectedNode = null; renderProps(null); };

    // ---------- 事件绑定 ----------
    document.getElementById("btn-add-node").onclick = () => canvas.showSearchTypes();
    document.getElementById("btn-upload").onclick = () => window.protocol.uploadGraph(exportGraph());
    document.getElementById("btn-reset").onclick = () => window.protocol.resetToServer();
    document.getElementById("btn-respawn").onclick = () => window.protocol.respawn();

    return { initRegistry, loadGraph, exportGraph, canvas, graph };
})();
