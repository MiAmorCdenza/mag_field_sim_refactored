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
    // LiteGraph 默认在左下角画 graph.globaltime/iteration/fps —— 那是它自己
    // runStep 执行循环的统计,本项目从不调用 → 恒为 0,极易误判"仿真卡死"。
    // 实时统计改在 DOM 覆盖层 #sim-hud(protocol.js 定时刷新),此处静默。
    canvas.renderInfo = function () {};
    window.addEventListener("resize", () => {
        canvasEl.width = canvasEl.clientWidth;
        canvasEl.height = canvasEl.clientHeight;
        if (typeof canvas.resize === "function") canvas.resize();
        canvas.setDirty(true, true);
    });

    // ---------- 节点类型注册 ----------
    // 渲染域节点专属色(右栏渲染管线视觉区分)
    const RENDER_NODE_COLOR = "#4a3a6a";
    // 粒子域节点专属色(中列粒子管线视觉区分)
    const PARTICLE_NODE_COLOR = "#3a5a4a";

    function makeNodeClass(spec) {
        function T(title) {
            // v0.4 LiteGraph 创建实例时不会调用基类构造器,必须显式初始化:
            // 否则 this.flags/inputs/outputs/properties 均为 undefined,
            // 绘制循环读 node.flags.collapsed 每帧抛错、节点永不渲染。
            // 标题必须在这里给定:LGraphNode 构造器对空标题回退为字符串
            // "Unnamed",而 registerNodeType 只写类级 T.title(画布读的是
            // 实例 this.title)→ 之前所有节点都显示 "Unnamed"。
            LGraphNode.call(this, title || spec.name || spec.type);
            this.properties = {};
            // any 端口必须用 LiteGraph 通配类型 "*"(空串亦可):
            // v0.4 的 isValidConnection 对非空类型严格相等,若 any 用颜色
            // 字符串,vector_field→any / any→vector_field 连线会被 connect
            // 静默拒绝 → 图往返丢边 → 服务器侧"输出槽未连接场源"
            const wireType = t => (t === "any" ? "*" : TYPE_COLORS[t] || "#888");
            for (const [pname, port] of Object.entries(spec.inputs)) {
                this.addInput(pname, wireType(port.ptype));
                this.properties["in:" + pname] = port.default;
            }
            for (const [oname, otype] of Object.entries(spec.outputs)) {
                this.addOutput(oname, wireType(otype));
            }
            for (const [k, p] of Object.entries(spec.params)) {
                this.properties[k] = p.default;
            }
            this.properties.spec_type = spec.type;
            this._spec = spec;
            if (spec.domain === "render") {
                this.color = RENDER_NODE_COLOR;
                this.bgcolor = "#241d33";
            } else if (spec.domain === "particle") {
                this.color = PARTICLE_NODE_COLOR;
                this.bgcolor = "#1d2b24";
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
            const entry = {
                id: jsonId, type: n.properties.spec_type,
                params, input_defaults: inputDefaults,
                pos: [Math.round(n.pos[0]), Math.round(n.pos[1])],
            };
            // 实例级标题只在用户改过时导出(否则载入时按插件名派生)
            if (n.title && n._spec && n.title !== n._spec.name) {
                entry.title = n.title;
            }
            nodes.push(entry);
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
                // 标题:JSON 显式 title 优先,否则用插件名(默认图/预设都不带 title)
                node.title = nd.title || (node._spec && node._spec.name) || nd.type;
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
            // 渲染域节点 → 渲染项实例(模板 id = 类型去 render_item_ 前缀)
            const renderIds = new Set();
            for (const [ndId, node] of Object.entries(idToNode)) {
                if (node._spec?.domain !== "render") continue;
                const jsonId = node.properties.json_id || ndId;
                renderIds.add(jsonId);
                const templateId = node._spec.type.replace(/^render_item_/, "");
                const params = {};
                for (const [k, v] of Object.entries(node.properties)) {
                    if (k === "spec_type" || k === "json_id" || k.startsWith("in:")) continue;
                    params[k] = v;
                }
                if (node._spec.type === "render_pipeline_start") {
                    // 全局渲染参数(背景/帧率上限):不实例化渲染项,直接应用
                    pushRenderNodeParams(node);
                    continue;
                }
                // 参数默认值补全(layer/opacity 等由规格给出),再实例化
                for (const [k, pspec] of Object.entries(node._spec.params)) {
                    if (!(k in params) && pspec.default !== undefined) {
                        params[k] = pspec.default;
                    }
                }
                window.renderRegistry && window.renderRegistry.instantiate(
                    jsonId, templateId, params);
            }
            // 清理图中已不存在的渲染项实例
            if (window.renderHost) {
                for (const id of [...window.renderHost.items.keys()]) {
                    if (!renderIds.has(id)) window.renderHost.unregisterItem(id);
                }
            }
            // 全部节点缺位置时(如内置默认图)自动做层次化排布
            if (doc.nodes.length &&
                doc.nodes.every(nd => !nd.pos ||
                    (nd.pos[0] === 0 && nd.pos[1] === 0))) {
                autoLayout();
            }
            // 图内含单粒子注入节点 → 载入即预览一次
            for (const ndId of Object.keys(idToNode)) {
                const n = idToNode[ndId];
                if (n._spec && n._spec.type === "particle_injection") {
                    previewInjection(n);
                    break;
                }
            }
            markSpeciesNodes();   // 标注未接线(不参与生成)的物种/种群节点
            canvas.setDirty(true, true);
            setGraphDirty(false);   // 载入(服务器图/上传成功)后视为已同步
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

    // ---------- 行表编辑器(种群物种表;ptype="rows")----------
    // 行 = 一个物种记录;支持:启用勾选 / 预设下拉(自动回填物理量)/
    // 名称 / q / mass / v_mult / weight / 颜色 / 上移下移 / 删除 / 追加。
    // 行序 = 抽取优先级(单粒子注入取第一个启用行)。
    const SPECIES_PRESETS = {
        electron: { name: "电子", q: -1.0, mass: 1 / 1836, v_mult: 1.0,
                    color: "#5599ff" },
        proton: { name: "质子", q: 1.0, mass: 1.0, v_mult: 1.0,
                  color: "#ff5555" },
        alpha: { name: "α粒子", q: 2.0, mass: 4.0, v_mult: 1.0,
                 color: "#ffaa33" },
    };

    function rowsWidget(spec, value, onChange) {
        const rows = Array.isArray(value) ? value.map(r => Object.assign({}, r))
                                          : [];
        const box = document.createElement("div");
        box.className = "rows-editor";
        const commit = () => onChange(rows.map(r => Object.assign({}, r)));

        const head = document.createElement("div");
        head.className = "rows-head";
        head.innerHTML = "<span>启用</span><span>预设</span><span>名称</span>" +
            "<span>q</span><span>m</span><span>v×</span><span>w</span><span>色</span><span></span>";
        box.appendChild(head);

        rows.forEach((r, i) => {
            const line = document.createElement("div");
            line.className = "rows-line";

            const en = document.createElement("input");
            en.type = "checkbox";
            en.checked = r.enabled !== false;
            en.onchange = () => { rows[i].enabled = en.checked; commit(); };

            const pre = document.createElement("select");
            for (const k of ["custom", "electron", "proton", "alpha"]) {
                const o = document.createElement("option");
                o.value = k; o.textContent = k;
                if ((r.preset || "custom") === k) o.selected = true;
                pre.appendChild(o);
            }
            pre.onchange = () => {
                rows[i].preset = pre.value;
                const p = SPECIES_PRESETS[pre.value];
                if (p) Object.assign(rows[i], p);      // 预设自动回填
                commit();
                renderProps(selectedNode);             // 重建面板显示新值
            };

            const name = document.createElement("input");
            name.type = "text"; name.value = r.name || "";
            name.onchange = () => {
                rows[i].name = name.value;
                if (rows[i].preset !== "custom" && !SPECIES_PRESETS[rows[i].preset]) {
                    rows[i].preset = "custom";
                }
                commit();
            };

            const num = (key, step) => {
                const el = document.createElement("input");
                el.type = "number"; el.step = step || "any";
                el.value = r[key] !== undefined ? r[key] : 0;
                el.onchange = () => {
                    rows[i][key] = Number(el.value);
                    if (key !== "weight") rows[i].preset = "custom";
                    commit();
                };
                return el;
            };

            const col = document.createElement("input");
            col.type = "color";
            col.value = r.color || "#ff5555";
            col.onchange = () => { rows[i].color = col.value; commit(); };

            const up = document.createElement("button");
            up.textContent = "↑"; up.className = "mini";
            up.disabled = i === 0;
            up.onclick = () => {
                [rows[i - 1], rows[i]] = [rows[i], rows[i - 1]];
                commit(); renderProps(selectedNode);
            };
            const dn = document.createElement("button");
            dn.textContent = "↓"; dn.className = "mini";
            dn.disabled = i === rows.length - 1;
            dn.onclick = () => {
                [rows[i + 1], rows[i]] = [rows[i], rows[i + 1]];
                commit(); renderProps(selectedNode);
            };
            const del = document.createElement("button");
            del.textContent = "✕"; del.className = "mini danger";
            del.onclick = () => {
                rows.splice(i, 1);
                commit(); renderProps(selectedNode);
            };

            line.append(en, pre, name, num("q"), num("mass"), num("v_mult"),
                        num("weight", 0.1), col, up, dn, del);
            if (r.enabled === false) line.classList.add("off");
            box.appendChild(line);
        });

        const add = document.createElement("button");
        add.textContent = "＋ 添加一行";
        add.className = "mini";
        add.onclick = () => {
            rows.push({ preset: "custom", name: "自定义粒子", q: 1.0,
                        mass: 1.0, v_mult: 1.0, weight: 1.0,
                        color: "#ff5555", enabled: true });
            commit(); renderProps(selectedNode);
        };
        box.appendChild(add);

        const sum = rows.filter(r => r.enabled !== false)
                        .reduce((a, r) => a + (Number(r.weight) || 0), 0);
        const info = document.createElement("div");
        info.className = "hint";
        info.textContent = `启用 ${rows.filter(r => r.enabled !== false).length}` +
            ` / 共 ${rows.length} 行,权重合计 ${sum.toFixed(2)}` +
            "(生成占比 = 该行权重 / 合计)";
        box.appendChild(info);
        return box;
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
            if (p.ptype === "rows") {
                // 行表用专用编辑器(不是单值控件)
                const wrap = document.createElement("div");
                wrap.className = "prop-row";
                const lab = document.createElement("label");
                lab.textContent = k + (p.desc ? " · " + p.desc : "");
                wrap.appendChild(lab);
                wrap.appendChild(rowsWidget(
                    p, node.properties[k] ?? p.default, v => {
                        node.properties[k] = v;
                        window.protocol.sendParam(node.properties.spec_type,
                                                  node, k, v);
                        previewInjection(node, true);
                    }));
                body.appendChild(wrap);
                continue;
            }
            body.appendChild(widget(p, k, node.properties[k] ?? p.default,
                v => {
                    node.properties[k] = v;
                    window.protocol.sendParam(node.properties.spec_type, node, k, v);
                    // 渲染域节点:参数(颜色/层/不透明度…)即时下发到渲染宿主。
                    // 之前在 onChange 里不推,只有"重新选中节点"时才推一次 →
                    // 改 color_mode 看不到反应,必须等下一次几何帧
                    if (spec.domain === "render") {
                        pushRenderNodeParams(node);
                    }
                    // 单粒子注入:参数变化即时刷新 3D 预览(L1 本地估算,
                    // 服务器 L2 预览随后到达并按含 B 的结果细化)
                    previewInjection(node, true);
                    // 粒子物种:预设下拉 → 立即回填其它字段
                    // (与引擎 on_param 同表;面板重建后停止本循环)
                    if (spec.type === "particle_species" && k === "preset" &&
                        spec.presets && spec.presets[v]) {
                        Object.assign(node.properties, spec.presets[v]);
                        renderProps(node);
                        return;
                    }
                }));
        }

        // ---- 物种读数:species 节点 / 发射器都显示**服务器解析出的真实种群** ----
        if (spec.type === "particle_species" || spec.type === "particle_emitter" ||
            spec.type === "particle_injection") {
            const box = document.createElement("div");
            box.className = "hint";
            box.id = "pop-readout";
            box.style.whiteSpace = "pre-wrap";
            body.appendChild(box);
            renderPopulationReadout();
        }

        // ---- 单粒子注入:初条件读数(局部 B / 回旋半径 / 回旋周期) ----
        // 数值来自服务器 L2 预览(与积分器同一套常数),拖滑杆时实时刷新。
        if (spec.type === "particle_injection") {
            const box = document.createElement("div");
            box.className = "hint";
            box.id = "inj-readout";
            box.style.whiteSpace = "pre-wrap";
            box.textContent = "初条件读数:等待服务器预览…";
            body.appendChild(box);
            renderInjectionReadout(window.simStats && window.simStats.src);
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
            // 参数下发到渲染宿主(颜色/层/可见性/尺寸等)
            pushRenderNodeParams(node);
        } else if (spec.type === "render_pipeline_start") {
            codePanel.classList.add("hidden");
            pushRenderNodeParams(node);   // 全局参数(背景/帧率上限)
        } else {
            codePanel.classList.add("hidden");
        }
        // 选中注入节点即预览(选中其它节点则清除预览)
        previewInjection(node);
    }

    // ---------- 单粒子初条件预览(L1:本地计算 → 渲染宿主) ----------
    // 与帧协议同一坐标约定:GSM(x,y,z) → Three(x,z,-y)
    const gsm2scene = (x, y, z) => [x, z, -y];

    function injectionPosGSM(p) {
        const deg = Math.PI / 180;
        if ((p.pos_mode || "rll") === "xyz") {
            return [Number(p.x) || 0, Number(p.y) || 0, Number(p.z) || 0];
        }
        const r = Number(p.r) || 6.6;
        const lat = (Number(p.lat) || 0) * deg;
        const lon = (Number(p.lon) || 0) * deg;
        return [r * Math.cos(lat) * Math.cos(lon),
                r * Math.cos(lat) * Math.sin(lon),
                r * Math.sin(lat)];
    }

    // ---------- 计划告警:画布红框 + 角标 ----------
    // 服务器把编译期诊断(无 B 表/无编码器/槽位未解析…)随 plan_status 广播;
    // 这里把相关节点标红并写出原因 —— 静默失败(实测:删 b 线后粒子直线飞、
    // 无任何提示)必须在画布上可见。
    let lastWarnNodes = new Set();
    function onPlanWarnings(warnings) {
        warnings = warnings || [];
        // 清掉上一轮标注
        for (const id of lastWarnNodes) {
            const n = graph.getNodeById(id);
            if (n) { n.boxcolor = null; n.onDrawForeground = null; }
        }
        const byNode = {};
        for (const w of warnings) {
            if (!w.node) continue;
            (byNode[w.node] = byNode[w.node] || []).push(w);
        }
        lastWarnNodes = new Set(Object.keys(byNode));
        for (const [nid, ws] of Object.entries(byNode)) {
            const n = graph.getNodeById(nid);
            if (!n) continue;
            n.boxcolor = "#f85149";
            const text = "⚠ " + (ws[0].code || "告警");
            n.onDrawForeground = function (ctx) {
                if (!this.flags || this.flags.collapsed) return;
                ctx.save();
                ctx.font = "10px sans-serif";
                ctx.fillStyle = "#f85149";
                ctx.fillText(text, 6, this.size[1] - 6);
                ctx.restore();
            };
        }
        canvas.setDirty(true, true);
    }

    // ---------- 物种:真实种群读数 + 画布标注 ----------
    // 事实(#30 之后):**接线决定归属** —— 发射器 types 接谁,就只有谁的物种
    // 参与生成;未接线的物种/种群节点被忽略(仅当 types 完全没接线时,服务器
    // 才按图级兜底聚合并告警 species_not_wired)。界面上:(a) 显示服务器解析
    // 出的真实种群;(b) 标注未接线节点(橙色 = 不参与生成)。

    // 从发射器 types 输入出发,返回被接线覆盖的节点(单跳:types 直接接的那个)
    function wiredSpeciesNodes() {
        const emitter = graph._nodes.find(n => n._spec &&
            n._spec.type === "particle_emitter");
        if (!emitter) return [];
        const slot = emitter.inputs.findIndex(i => i.name === "types");
        if (slot < 0 || emitter.inputs[slot].link == null) return [];
        const link = graph.links[emitter.inputs[slot].link];
        const node = link ? graph.getNodeById(link.origin_id) : null;
        return node ? [node] : [];
    }

    // 标注:未接线的物种/种群节点(橙色 = 不参与生成)
    function markSpeciesNodes() {
        const wired = wiredSpeciesNodes();
        const inWired = new Set(wired.map(n => n.id));
        const species = graph._nodes.filter(n => n._spec &&
            (n._spec.type === "particle_species" ||
             n._spec.type === "particle_population"));
        const hasWire = wired.length > 0;
        for (const n of species) {
            const unconnected = !inWired.has(n.id);
            n.boxcolor = unconnected ? "#f0883e" : null;
            n.onDrawForeground = unconnected ? function (ctx) {
                if (!this.flags || this.flags.collapsed) return;
                ctx.save();
                ctx.font = "10px sans-serif";
                ctx.fillStyle = "#f0883e";
                ctx.fillText(hasWire ? "未接线:不参与生成"
                                     : "未接线(服务器按图级兜底)", 6,
                             this.size[1] - 6);
                ctx.restore();
            } : null;
        }
    }

    // 属性面板读数(选中 species 节点或发射器时显示)
    function renderPopulationReadout() {
        const box = document.getElementById("pop-readout");
        if (!box) return;
        const pop = window.simStats && window.simStats.population;
        if (!pop || !pop.species || !pop.species.length) {
            box.textContent = "真实种群:等待服务器解析…(物种为图级声明)";
            return;
        }
        const rows = pop.species.map(s =>
            `${s.color} ${s.name}  w=${s.weight}  ${(s.share * 100).toFixed(1)}%` +
            `  q=${s.q} m=${s.mass}`);
        box.textContent = `真实种群(服务器聚合,共 ${pop.count} 种,` +
            `权重合计 ${pop.total_weight}):\n` + rows.join("\n") +
            (pop.count > 1 ? "\n⚠ 图级声明:未接线的 particle_species 节点同样参与生成"
                           : "");
    }

    function onPopulation() {
        markSpeciesNodes();
        renderPopulationReadout();
    }

    // 单粒子初条件读数面板(与 3D 预览同源:服务器 L2 预览消息)
    function renderInjectionReadout(src) {
        const box = document.getElementById("inj-readout");
        if (!box) return;
        if (!src || typeof src.b_nt !== "number") {
            box.textContent = "初条件读数:等待服务器预览…";
            return;
        }
        const f = (v, d) => (typeof v === "number" && isFinite(v) ? v.toFixed(d) : "—");
        const pitch = src.pitch;
        let trap;
        if (src.vel_mode === 1) trap = "vxyz 模式:方向直接给定";
        else if (pitch >= 60 && pitch <= 120) trap = "磁镜捕获(沿场线反弹)";
        else if (pitch <= 20 || pitch >= 160) trap = "近沿场线:损失锥方向(会沉降)";
        else trap = "捕获,镜点纬度中等";
        const rg_km = src.r_g_re * 6371;
        const lines = [
            `B = ${f(src.b_nt, 1)} nT${src.has_b ? "" : "(无局部 B,方向回退 z 轴)"}`,
            `v = ${f(src.vmag, 1)} km/s   pitch = ${f(pitch, 1)}°   相位 = ${f(src.phase, 1)}°`,
            `R_g = ${src.r_g_re.toExponential(2)} Re = ${f(rg_km, 1)} km`,
            `回旋周期 = ${f(src.gyro_s, 3)} s   (${trap})`,
        ];
        if (src.r_g_re > 0 && src.r_g_re < 0.05) {
            lines.push("提示:R_g ≪ 场景尺度 → 螺旋不可见。" +
                       "在偶极子后加 mul 节点缩放 B(w=0.01 → R_g ×100)即可看见回旋。");
        }
        if (src.note) lines.push("⚠ " + src.note);
        box.textContent = lines.join("\n");
    }

    // local=true:拖参数时的即时本地估算(r=位置立刻动;服务器 ~250ms 后细化)
    // local=false(默认):选中/载图 → 重放服务器 L2 预览(含局部 B 与 b̂)
    function previewInjection(node, local) {
        if (!window.renderHost || !window.renderHost.dispatch) return;
        const spec = node && node._spec;
        if (!spec || spec.type !== "particle_injection") {
            window.renderHost.dispatch("source_preview", null);
            return;
        }
        if (!local && window.protocol && window.protocol.replaySourcePreview &&
            window.protocol.replaySourcePreview()) return;
        const p = node.properties || {};
        const g = injectionPosGSM(p);
        let dir = null;
        let vmag = Number(p.v) || 400;
        if ((p.vel_mode || "vpitch") === "vxyz") {
            const vx = Number(p.vx) || 0, vy = Number(p.vy) || 0, vz = Number(p.vz) || 0;
            const n = Math.hypot(vx, vy, vz);
            if (n > 1e-9) dir = gsm2scene(vx, vy, vz).map(c => c / n);
            vmag = n;
        }
        window.renderHost.dispatch("source_preview", {
            pos: gsm2scene(g[0], g[1], g[2]),
            dir, vmag,
            // vpitch 的速度方向依赖局部 B → 由 L2 服务器预览帧提供
            note: dir ? "" : "vpitch:方向依赖局部 B(待 L2 服务器预览)",
        });
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
            // 空 color = "用渲染项自身的默认色"(场线按拓扑分类着色),
            // 不能把空串推下去覆盖分类色
            if (k === "color" && v === "") continue;
            params[k] = v;
        }
        if (window.renderHost) window.renderHost.applyParams(itemId, params);
    }

    // 渲染节点参数下发统一入口:全局参数节点走 applyGlobal,其余走渲染项
    function pushRenderNodeParams(node) {
        if (!window.renderHost) return;
        if (node._spec && node._spec.type === "render_pipeline_start") {
            const p = {};
            for (const [k, v] of Object.entries(node.properties)) {
                if (k === "spec_type" || k === "json_id" || k.startsWith("in:")) continue;
                p[k] = v;
            }
            // 参数未显式给过 → 用规格默认值(背景/帧率上限)
            for (const [k, spec] of Object.entries(node._spec.params)) {
                if (!(k in p) && spec.default !== undefined) p[k] = spec.default;
            }
            window.renderHost.applyGlobal(p);
            return;
        }
        pushRenderParams(node);
    }

    // 内联代码应用
    function applyInlineCode() {
        if (!selectedNode) return;
        const code = document.getElementById("code-text").value;
        const templateId = selectedNode._spec.type.replace(/^render_item_/, "");
        try {
            window.renderRegistry.compileInline(templateId, code);
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
        const particleNodes = nodes.filter(n => domainOf(n) === "particle");
        const dataNodes = nodes.filter(
            n => domainOf(n) !== "render" && domainOf(n) !== "particle");

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

        // ---- 粒子域:中列垂直链(发射器→积分器→编码器,与引擎同算法) ----
        const pchain = [];
        const pseen = new Set();
        const pstarts = particleNodes.filter(n =>
            !Object.values(graph.links || {}).some(
                l => l.target_id === n.id &&
                     particleNodes.some(p => p.id === l.origin_id)));
        const pq = pstarts.length
            ? [...pstarts]
            : (particleNodes.length ? [particleNodes[0]] : []);
        while (pq.length) {
            const n = pq.shift();
            if (pseen.has(n.id)) continue;
            pseen.add(n.id);
            pchain.push(n);
            for (const m of adj[n.id]) {
                if (particleNodes.some(p => p.id === m) && !pseen.has(m)) pq.push(
                    particleNodes.find(p => p.id === m));
            }
        }
        particleNodes.forEach(n => { if (!pseen.has(n.id)) pchain.push(n); });
        if (pchain.length) {
            pchain.forEach((n, i) => { n.pos = [x, 60 + i * gapY]; });
            x += gapX;
        }

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

    // ---------- 图编辑未应用提示 ----------
    // 画布上的**结构**修改(增删节点/改连线)只在本地点上生效,必须点
    // 「应用图到服务器」才会上传并重烘焙;参数修改则即时下发(node.param)。
    // 之前没有任何提示,实测踩坑:删了「单粒子注入」节点、把 count 调大,
    // 服务器图里注入节点仍在 → mode 3 让所有粒子初条件相同 → 看起来还是 1 个。
    let graphDirty = false;
    function setGraphDirty(v) {
        if (graphDirty === v) return;
        graphDirty = v;
        const btn = document.getElementById("btn-upload");
        const badge = document.getElementById("dirty-badge");
        if (btn) {
            btn.classList.toggle("dirty", v);
            btn.textContent = v ? "⬆ 应用图到服务器 ●" : "⬆ 应用图到服务器";
        }
        if (badge) badge.style.display = v ? "" : "none";
    }
    function isGraphDirty() { return graphDirty; }

    // 节点增删 + 连线变化 → 置脏(载图期间由 loadGraph 末尾清掉)
    graph.onNodeAdded = () => setGraphDirty(true);
    graph.onNodeRemoved = (node) => {
        setGraphDirty(true);
        // 删掉注入节点 → 本地预览标记也要跟着消失(否则会残留一个"假"标记)
        if (node && node._spec && node._spec.type === "particle_injection" &&
            window.renderHost) {
            window.renderHost.dispatch("source_preview", null);
        }
        if (selectedNode === node) { selectedNode = null; renderProps(null); }
    };
    const _prevConnChange = LGraphNode.prototype.onConnectionsChange;
    LGraphNode.prototype.onConnectionsChange = function (...args) {
        if (typeof _prevConnChange === "function") _prevConnChange.apply(this, args);
        setGraphDirty(true);
    };

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

    // 服务器 L2 预览到达(protocol.js 调用):若正在看注入节点,刷新读数面板
    function onSourcePreview(src) {
        if (selectedNode && selectedNode._spec &&
            selectedNode._spec.type === "particle_injection") {
            renderInjectionReadout(src);
        }
    }

    return { initRegistry, loadGraph, exportGraph, canvas, graph, onSourcePreview,
             onPopulation, markSpeciesNodes, onPlanWarnings,
             markGraphApplied: () => setGraphDirty(false),
             isGraphDirty: () => graphDirty };
})();
