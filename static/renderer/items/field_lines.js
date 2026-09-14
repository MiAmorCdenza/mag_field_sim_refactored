// 内置渲染项:磁场线(geometry:field_lines 帧)。
//
// 着色依据 = **种子拓扑类别**(帧里每线一个 u8 class),不是 |B|/|H| 强度:
//   class 0 闭合线(赤道 L 壳种子) → 蓝 #4da6ff
//   class 1 开放线(极盖种子)       → 红 #ff6b6b
//   class 2 太阳风线(上游平面种子) → 绿 #6be06b
// 类别由服务器在追踪时按种子集打标(server_app.cpp run_render_bindings);
// 帧里还有每线的 u8 reason(终止原因)目前未用于着色。
// 节点参数 color 非空 → 全部线统一该色(覆盖分类色)。
const FIELD_LINE_CLASS_COLORS = [0x4da6ff, 0xff6b6b, 0x6be06b];

registerRenderItem({
    id: "field_lines",
    layer: 1,
    subscribes: ["geometry:field_lines"],

    setup(scene, three) {
        this.three = three;
        this.group = new three.Group();
        this.lines = [];
        this.params = {};
        scene.add(this.group);
    },

    // 帧:[u32 meta_len][JSON meta][每线:u8 class u8 reason u16 n f32xyz×n]
    onData(frame) {
        const buf = frame instanceof ArrayBuffer ? frame : frame.buffer;
        const view = new DataView(buf);
        const hlen = view.getUint32(0, true);
        const meta = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 4, hlen)));
        const count = meta.count;
        this.clear();
        let off = 4 + hlen;
        for (let i = 0; i < count; i++) {
            const cls = view.getUint8(off);
            const n = view.getUint16(off + 2, true);
            off += 4;
            const pts = [];
            for (let j = 0; j < n; j++) {
                pts.push(new this.three.Vector3(
                    view.getFloat32(off, true),
                    view.getFloat32(off + 4, true),
                    view.getFloat32(off + 8, true)));
                off += 12;
            }
            if (pts.length < 2) continue;
            const color = this.params.color || FIELD_LINE_CLASS_COLORS[cls % 3];
            const geo = new this.three.BufferGeometry().setFromPoints(pts);
            const mat = new this.three.LineBasicMaterial({
                color, transparent: true,
                opacity: this.params.opacity !== undefined ? this.params.opacity : 0.9,
            });
            const line = new this.three.Line(geo, mat);
            line.userData.cls = cls;   // 记住类别:color 清空时回退分类色
            this.group.add(line);
            this.lines.push(line);
        }
    },

    // 统一改色:color 非空用该色,空串回退到各自的分类色
    recolor() {
        for (const l of this.lines) {
            const cls = (l.userData && l.userData.cls) | 0;
            l.material.color.set(this.params.color || FIELD_LINE_CLASS_COLORS[cls % 3]);
        }
    },

    onParam(params) {
        this.params = Object.assign({}, this.params, params);
        if (params.visible !== undefined) this.group.visible = !!params.visible;
        if (params.opacity !== undefined) {
            for (const l of this.lines) l.material.opacity = params.opacity;
        }
        // 改色立即生效(否则要等下一次几何帧/重新烘焙才看得到)
        if ("color" in params) this.recolor();
    },

    clear() {
        this.lines.forEach(l => { l.geometry.dispose(); l.material.dispose(); });
        this.lines = [];
        this.group.clear && this.group.clear();
        while (this.group.children.length) this.group.remove(this.group.children[0]);
    },

    dispose() {
        this.clear();
        this.group.parent && this.group.parent.remove(this.group);
    },
});
