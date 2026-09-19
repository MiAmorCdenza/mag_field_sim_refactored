// 内置渲染项:磁场线(geometry:field_lines 帧)。
//
// 着色模式(color_mode 参数,三选一):
//   class  —— 种子**拓扑类别**(默认;帧里每线 u8 class)
//             0 闭合线(赤道 L 壳种子) 蓝 #4da6ff
//             1 开放线(极盖种子)       红 #ff6b6b
//             2 太阳风线(上游平面种子) 绿 #6be06b
//   bmag   —— 逐点**场强**着色(帧 v2 每点带 f32 |B|,单位 nT;meta.smin/smax
//             给全域范围,取 log 映射;顶点色,不用光照)
//   reason —— 按**终止原因**着色(帧里每线 u8 reason)
//             0 落地 / 1 出域 / 2 绕圈 / 3 点数上限 / 4 场近零
// 节点参数 color 非空 → 全部线统一该色(覆盖以上三种模式)。
//
// 帧格式 v2:[u32 meta_len][JSON meta{v,unit,smin,smax,count}]
//          [每线:u8 class u8 reason u16 n (f32 x,y,z, f32 |B|)×n]
// 坐标为 Three 约定 (x,z,-y);v1(12 B/点、无场强)仍可解析(降级为 class)。
const FIELD_LINE_CLASS_COLORS = [0x4da6ff, 0xff6b6b, 0x6be06b];
const FIELD_LINE_REASON_COLORS = [0x4da6ff, 0xff9f43, 0xc792ea, 0x8899aa, 0xff5555];
const FIELD_LINE_REASON_NAMES = ["落地(R=R₀)", "出域(表域边界)", "绕圈(径向反转>4)",
                                 "点数上限", "场近零"];
// viridis 近似(6 锚点线性插值)
const VIRIDIS = [[0.267, 0.005, 0.329], [0.255, 0.267, 0.529],
                 [0.165, 0.471, 0.558], [0.133, 0.659, 0.518],
                 [0.478, 0.821, 0.318], [0.993, 0.906, 0.144]];

function viridis(t) {
    t = Math.max(0, Math.min(1, t));
    const x = t * (VIRIDIS.length - 1);
    const i = Math.min(VIRIDIS.length - 2, Math.floor(x));
    const f = x - i;
    const a = VIRIDIS[i], b = VIRIDIS[i + 1];
    return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
}

function cssRgb(c) {
    return `rgb(${Math.round(c[0] * 255)},${Math.round(c[1] * 255)},${Math.round(c[2] * 255)})`;
}

registerRenderItem({
    id: "field_lines",
    layer: 1,
    subscribes: ["geometry:field_lines"],

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
        const stride = (meta.v >= 2) ? 16 : 12;      // v1 兼容(无场强)
        const count = meta.count;
        this.clear();
        const reasonCount = {};
        const smin = (meta.smin !== undefined) ? meta.smin : 0;
        const smax = (meta.smax !== undefined) ? meta.smax : 1;
        const lmin = Math.log10(Math.max(smin, 1e-30));
        const lmax = Math.log10(Math.max(smax, 1e-30));
        const span = Math.max(lmax - lmin, 1e-9);
        const mode = this.params.color_mode || "class";

        let off = 4 + hlen;
        for (let i = 0; i < count; i++) {
            const cls = view.getUint8(off);
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
                    const t = (Math.log10(Math.max(v, 1e-30)) - lmin) / span;
                    const c = viridis(t);
                    cols.push(c[0], c[1], c[2]);
                }
                off += stride;
            }
            if (pts.length < 2) continue;
            reasonCount[reason] = (reasonCount[reason] || 0) + 1;

            const geo = new this.three.BufferGeometry().setFromPoints(pts);
            if (mags) geo.userData.bmag = mags;   // 换模式时重算顶点色用
            let mat;
            if (this.params.color) {                    // 手动统一色优先
                mat = new this.three.LineBasicMaterial({
                    color: this.params.color,
                    transparent: true,
                    opacity: this.params.opacity !== undefined ? this.params.opacity : 0.9,
                });
            } else if (mode === "bmag" && cols.length) { // 逐点场强
                geo.setAttribute("color",
                    new this.three.Float32BufferAttribute(cols, 3));
                mat = new this.three.LineBasicMaterial({
                    vertexColors: true, transparent: true,
                    opacity: this.params.opacity !== undefined ? this.params.opacity : 0.9,
                });
            } else {                                     // 分类 / 终止原因
                const c = (mode === "reason")
                    ? FIELD_LINE_REASON_COLORS[reason % 5]
                    : FIELD_LINE_CLASS_COLORS[cls % 3];
                mat = new this.three.LineBasicMaterial({
                    color: c, transparent: true,
                    opacity: this.params.opacity !== undefined ? this.params.opacity : 0.9,
                });
            }
            const line = new this.three.Line(geo, mat);
            line.userData.cls = cls;
            line.userData.reason = reason;
            this.group.add(line);
            this.lines.push(line);
        }
        this.reasonCount = reasonCount;
        this.updateLegend();
    },

    // 统一改色:非空用该色(覆盖模式),空串回退当前 color_mode
    recolor() {
        const mode = this.params.color_mode || "class";
        const smin = (this.meta && this.meta.smin !== undefined) ? this.meta.smin : 0;
        const smax = (this.meta && this.meta.smax !== undefined) ? this.meta.smax : 1;
        const lmin = Math.log10(Math.max(smin, 1e-30));
        const span = Math.max(Math.log10(Math.max(smax, 1e-30)) - lmin, 1e-9);
        for (const l of this.lines) {
            const cls = (l.userData && l.userData.cls) | 0;
            const reason = (l.userData && l.userData.reason) | 0;
            if (this.params.color) {
                l.material.vertexColors = false;
                l.material.color.set(this.params.color);
                continue;
            }
            if (mode === "bmag") {
                // 顶点色已在帧解析时写入;重新计算以防参数变化
                const pos = l.geometry.attributes.position;
                const cols = new Float32Array(pos.count * 3);
                const src = l.geometry.userData.bmag;
                if (src) {
                    for (let k = 0; k < pos.count; k++) {
                        const t = (Math.log10(Math.max(src[k], 1e-30)) - lmin) / span;
                        const c = viridis(t);
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
                ? FIELD_LINE_REASON_COLORS[reason % 5]
                : FIELD_LINE_CLASS_COLORS[cls % 3]);
            l.material.needsUpdate = true;
        }
        this.updateLegend();
    },

    // 色标图例(视口右上角 DOM;渲染项可直接写,见 index.html #line-legend)
    updateLegend() {
        const el = document.getElementById("line-legend");
        if (!el) return;
        const mode = this.params.color || this.params.color_mode || "class";
        if (!this.lines.length) { el.style.display = "none"; return; }
        if (this.params.color) {
            el.innerHTML = `<b>场线</b>\n<span class="row">` +
                `<span class="sw" style="background:${this.params.color}"></span>` +
                `${this.lines.length} 条 · 统一色(覆盖着色方式)</span>`;
        } else if (mode === "bmag" && this.meta) {
            const unit = this.meta.unit || "";
            const stops = [];
            for (let i = 0; i <= 12; i++) stops.push(cssRgb(viridis(i / 12)));
            el.innerHTML = `<b>|B| (${unit}, log)</b>\n` +
                `<span class="bar" style="background:linear-gradient(90deg,${stops.join(",")})"></span>` +
                `<span>${Number(this.meta.smin).toPrecision(3)} … ${Number(this.meta.smax).toPrecision(3)}</span>\n` +
                `${this.lines.length} 条场线`;
        } else if (mode === "reason") {
            const rc = this.reasonCount || {};
            const rows = Object.keys(rc).sort().map(r =>
                `<span class="row"><span class="sw" style="background:` +
                `#${FIELD_LINE_REASON_COLORS[r % 5].toString(16).padStart(6, "0")}` +
                `"></span>${FIELD_LINE_REASON_NAMES[r % 5]} × ${rc[r]}</span>`);
            el.innerHTML = `<b>终止原因</b>\n` + rows.join("\n");
        } else {
            const cls = {};
            for (const l of this.lines) {
                const c = (l.userData.cls) | 0;
                cls[c] = (cls[c] || 0) + 1;
            }
            const names = ["闭合(赤道L壳)", "开放(极盖)", "太阳风(上游)"];
            const rows = Object.keys(cls).sort().map(c =>
                `<span class="row"><span class="sw" style="background:` +
                `#${FIELD_LINE_CLASS_COLORS[c % 3].toString(16).padStart(6, "0")}` +
                `"></span>${names[c % 3]} × ${cls[c]}</span>`);
            el.innerHTML = `<b>拓扑分类</b>\n` + rows.join("\n");
        }
        el.style.display = "block";
    },

    onParam(params) {
        this.params = Object.assign({}, this.params, params);
        if (params.visible !== undefined) this.group.visible = !!params.visible;
        if (params.opacity !== undefined) {
            for (const l of this.lines) l.material.opacity = params.opacity;
        }
        // #52 用户显式选了着色方式 → 清掉"统一色":固定 color 会永久覆盖 color_mode,
        //     表现为"改成 bmag/class 画面不变"(图例那时写的是"统一色")。
        //     想让固定色生效,再往 color 里填一个颜色即可(填色优先于模式)。
        if ("color_mode" in params && params.color_mode) this.params.color = "";
        // 改色/换模式立即生效(否则要等下一次几何帧/重新烘焙)
        if ("color" in params || "color_mode" in params) this.recolor();
    },

    clear() {
        this.lines.forEach(l => { l.geometry.dispose(); l.material.dispose(); });
        this.lines = [];
        this.group.clear && this.group.clear();
        while (this.group.children.length) this.group.remove(this.group.children[0]);
    },

    dispose() {
        this.clear();
        const el = document.getElementById("line-legend");
        if (el) el.style.display = "none";
        this.group.parent && this.group.parent.remove(this.group);
    },
});
