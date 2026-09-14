// 内置渲染项:电场线(geometry:efield_lines 帧)。
//
// 着色模式(color_mode 参数):
//   class  —— 默认暖黄(电场线不做拓扑分类,只有一类种子)
//   bmag   —— 逐点**场强**着色(帧 v2 每点带 f32 |E|,归一化单位;
//             meta.smin/smax + log 映射,顶点色)
//   reason —— 按**终止原因**着色(0 落地 / 1 出域 / 2 绕圈 / 3 点数上限 / 4 场近零)
// 节点参数 color 非空 → 全部线统一该色(覆盖以上模式)。
const E_FIELD_LINE_DEFAULT_COLOR = 0xffd166;
const E_FIELD_LINE_REASON_COLORS = [0x4da6ff, 0xff9f43, 0xc792ea, 0x8899aa, 0xff5555];
const E_FIELD_LINE_REASON_NAMES = ["落地(R=R₀)", "出域(表域边界)", "绕圈(径向反转>4)",
                                   "点数上限", "场近零"];
const E_VIRIDIS = [[0.267, 0.005, 0.329], [0.255, 0.267, 0.529],
                   [0.165, 0.471, 0.558], [0.133, 0.659, 0.518],
                   [0.478, 0.821, 0.318], [0.993, 0.906, 0.144]];

function eviridis(t) {
    t = Math.max(0, Math.min(1, t));
    const x = t * (E_VIRIDIS.length - 1);
    const i = Math.min(E_VIRIDIS.length - 2, Math.floor(x));
    const f = x - i;
    const a = E_VIRIDIS[i], b = E_VIRIDIS[i + 1];
    return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
}

registerRenderItem({
    id: "efield_lines",
    layer: 1,
    subscribes: ["geometry:efield_lines"],

    setup(scene, three) {
        this.three = three;
        this.group = new three.Group();
        this.lines = [];
        this.params = {};
        this.meta = null;
        scene.add(this.group);
    },

    onData(frame) {
        const buf = frame instanceof ArrayBuffer ? frame : frame.buffer;
        const view = new DataView(buf);
        const hlen = view.getUint32(0, true);
        const meta = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 4, hlen)));
        this.meta = meta;
        const stride = (meta.v >= 2) ? 16 : 12;
        const count = meta.count;
        this.clear();
        const reasonCount = {};
        const lmin = Math.log10(Math.max(meta.smin !== undefined ? meta.smin : 1e-30, 1e-30));
        const span = Math.max(Math.log10(Math.max(meta.smax !== undefined ? meta.smax : 1, 1e-30)) - lmin, 1e-9);
        const mode = this.params.color_mode || "class";

        let off = 4 + hlen;
        for (let i = 0; i < count; i++) {
            const reason = view.getUint8(off + 1);
            const n = view.getUint16(off + 2, true);
            off += 4;
            const pts = [];
            const cols = [];
            const mags = (stride === 16) ? new Float32Array(n) : null;
            for (let j = 0; j < n; j++) {
                pts.push(new this.three.Vector3(
                    view.getFloat32(off, true),
                    view.getFloat32(off + 4, true),
                    view.getFloat32(off + 8, true)));
                if (stride === 16) {
                    const v = view.getFloat32(off + 12, true);
                    mags[j] = v;
                    const c = eviridis((Math.log10(Math.max(v, 1e-30)) - lmin) / span);
                    cols.push(c[0], c[1], c[2]);
                }
                off += stride;
            }
            if (pts.length < 2) continue;
            reasonCount[reason] = (reasonCount[reason] || 0) + 1;

            const geo = new this.three.BufferGeometry().setFromPoints(pts);
            if (mags) geo.userData.bmag = mags;
            const op = this.params.opacity !== undefined ? this.params.opacity : 0.55;
            let mat;
            if (this.params.color) {
                mat = new this.three.LineBasicMaterial({
                    color: this.params.color, transparent: true, opacity: op });
            } else if (mode === "bmag" && cols.length) {
                geo.setAttribute("color", new this.three.Float32BufferAttribute(cols, 3));
                mat = new this.three.LineBasicMaterial({
                    vertexColors: true, transparent: true, opacity: op });
            } else {
                const c = (mode === "reason")
                    ? E_FIELD_LINE_REASON_COLORS[reason % 5]
                    : E_FIELD_LINE_DEFAULT_COLOR;
                mat = new this.three.LineBasicMaterial({
                    color: c, transparent: true, opacity: op });
            }
            const line = new this.three.Line(geo, mat);
            line.userData.reason = reason;
            this.group.add(line);
            this.lines.push(line);
        }
        this.reasonCount = reasonCount;
        this.updateLegend();
    },

    recolor() {
        const mode = this.params.color_mode || "class";
        const lmin = Math.log10(Math.max(this.meta && this.meta.smin !== undefined ? this.meta.smin : 1e-30, 1e-30));
        const span = Math.max(Math.log10(Math.max(this.meta && this.meta.smax !== undefined ? this.meta.smax : 1, 1e-30)) - lmin, 1e-9);
        for (const l of this.lines) {
            const reason = (l.userData && l.userData.reason) | 0;
            if (this.params.color) {
                l.material.vertexColors = false;
                l.material.color.set(this.params.color);
                l.material.needsUpdate = true;
                continue;
            }
            if (mode === "bmag") {
                const src = l.geometry.userData.bmag;
                const cols = new Float32Array(l.geometry.attributes.position.count * 3);
                if (src) {
                    for (let k = 0; k < src.length; k++) {
                        const c = eviridis((Math.log10(Math.max(src[k], 1e-30)) - lmin) / span);
                        cols[k * 3] = c[0]; cols[k * 3 + 1] = c[1]; cols[k * 3 + 2] = c[2];
                    }
                }
                l.geometry.setAttribute("color", new this.three.Float32BufferAttribute(cols, 3));
                l.material.vertexColors = true;
                l.material.color.set(0xffffff);
                l.material.needsUpdate = true;
                continue;
            }
            l.material.vertexColors = false;
            l.material.color.set(mode === "reason"
                ? E_FIELD_LINE_REASON_COLORS[reason % 5]
                : E_FIELD_LINE_DEFAULT_COLOR);
            l.material.needsUpdate = true;
        }
        this.updateLegend();
    },

    updateLegend() {
        const el = document.getElementById("line-legend");
        if (!el || !this.lines.length) { if (el && !this.lines.length) el.style.display = "none"; return; }
        const mode = this.params.color || this.params.color_mode || "class";
        const hex = c => "#" + c.toString(16).padStart(6, "0");
        if (this.params.color) {
            el.innerHTML = `<b>电场线</b>\n<span class="row"><span class="sw" style="background:${this.params.color}"></span>${this.lines.length} 条 · 统一色</span>`;
        } else if (mode === "bmag" && this.meta) {
            const stops = [];
            for (let i = 0; i <= 12; i++) stops.push(`rgb(${eviridis(i / 12).map(v => Math.round(v * 255)).join(",")})`);
            el.innerHTML = `<b>|E| (${this.meta.unit || ""}, log)</b>\n` +
                `<span class="bar" style="background:linear-gradient(90deg,${stops.join(",")})"></span>` +
                `<span>${Number(this.meta.smin).toPrecision(3)} … ${Number(this.meta.smax).toPrecision(3)}</span>\n${this.lines.length} 条电场线`;
        } else if (mode === "reason") {
            const rc = this.reasonCount || {};
            const rows = Object.keys(rc).sort().map(r =>
                `<span class="row"><span class="sw" style="background:${hex(E_FIELD_LINE_REASON_COLORS[r % 5])}"></span>${E_FIELD_LINE_REASON_NAMES[r % 5]} × ${rc[r]}</span>`);
            el.innerHTML = `<b>终止原因</b>\n` + rows.join("\n");
        } else {
            el.innerHTML = `<b>电场线</b>\n<span class="row"><span class="sw" style="background:${hex(E_FIELD_LINE_DEFAULT_COLOR)}"></span>${this.lines.length} 条</span>`;
        }
        el.style.display = "block";
    },

    onParam(params) {
        this.params = Object.assign({}, this.params, params);
        if (params.visible !== undefined) this.group.visible = !!params.visible;
        if (params.opacity !== undefined) {
            for (const l of this.lines) l.material.opacity = params.opacity;
        }
        if ("color" in params || "color_mode" in params) this.recolor();
    },

    clear() {
        this.lines.forEach(l => { l.geometry.dispose(); l.material.dispose(); });
        this.lines = [];
        while (this.group.children.length) this.group.remove(this.group.children[0]);
    },

    dispose() {
        this.clear();
        const el = document.getElementById("line-legend");
        if (el) el.style.display = "none";
        this.group.parent && this.group.parent.remove(this.group);
    },
});
