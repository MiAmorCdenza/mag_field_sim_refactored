// 内置渲染项:电场线(geometry:efield_lines 帧)。
registerRenderItem({
    id: "efield_lines",
    layer: 1,
    subscribes: ["geometry:efield_lines"],

    setup(scene, three) {
        this.three = three;
        this.group = new three.Group();
        this.lines = [];
        this.params = {};
        scene.add(this.group);
    },

    onData(frame) {
        const buf = frame instanceof ArrayBuffer ? frame : frame.buffer;
        const view = new DataView(buf);
        const hlen = view.getUint32(0, true);
        const meta = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 4, hlen)));
        const count = meta.count;
        this.clear();
        let off = 4 + hlen;
        for (let i = 0; i < count; i++) {
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
            const color = this.params.color || 0xffd166;
            const geo = new this.three.BufferGeometry().setFromPoints(pts);
            const mat = new this.three.LineBasicMaterial({
                color, transparent: true,
                opacity: this.params.opacity !== undefined ? this.params.opacity : 0.55,
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
        while (this.group.children.length) this.group.remove(this.group.children[0]);
    },

    dispose() {
        this.clear();
        this.group.parent && this.group.parent.remove(this.group);
    },
});
