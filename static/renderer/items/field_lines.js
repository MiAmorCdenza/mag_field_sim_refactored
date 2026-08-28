// 内置渲染项:磁场线(geometry:field_lines 帧)。
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
        const classColors = [0x4da6ff, 0xff6b6b, 0x6be06b];  // 闭合/开放/太阳风
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
            const color = this.params.color || classColors[cls % 3];
            const geo = new this.three.BufferGeometry().setFromPoints(pts);
            const mat = new this.three.LineBasicMaterial({
                color, transparent: true,
                opacity: this.params.opacity !== undefined ? this.params.opacity : 0.9,
            });
            const line = new this.three.Line(geo, mat);
            this.group.add(line);
            this.lines.push(line);
        }
    },

    onParam(params) {
        this.params = Object.assign({}, this.params, params);
        if (params.visible !== undefined) this.group.visible = !!params.visible;
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
