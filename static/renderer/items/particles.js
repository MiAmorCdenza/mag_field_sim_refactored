// 内置渲染项:粒子(21B/粒子帧)。
registerRenderItem({
    id: "particles",
    layer: 2,
    subscribes: ["particles"],

    setup(scene, three) {
        this.three = three;
        this.group = new three.Group();
        this.geo = new three.SphereGeometry(0.07, 8, 8);
        this.meshes = {};     // 颜色hex → InstancedMesh
        this.MAX = 20000;
        this.size = 0.07;
        this.dummy = new three.Object3D();
        scene.add(this.group);
    },

    // 解析 21B 帧并更新实例(与旧 renderer.js 同逻辑)
    onData(frame) {
        const buf = frame instanceof ArrayBuffer ? frame : frame.buffer;
        const view = new DataView(buf);
        const hlen = view.getUint32(0, true);
        const header = JSON.parse(new TextDecoder().decode(
            new Uint8Array(buf, 4, hlen)));
        const n = header.n;
        // 每帧重置计数:否则 count 只增不减,矩阵区残留旧帧数据
        // (旧帧尾巴渲染为幽灵粒子,并导致计数虚高)
        Object.values(this.meshes).forEach(m => { m.count = 0; });
        let off = 4 + hlen;
        for (let i = 0; i < n; i++) {
            const px = view.getFloat32(off + 4, true);
            const py = view.getFloat32(off + 8, true);
            const pz = view.getFloat32(off + 12, true);
            const status = view.getUint8(off + 16);
            const color = view.getUint32(off + 17, true);
            off += 21;
            if (status !== 0) continue;
            const hex = "#" + color.toString(16).padStart(6, "0");
            const m = this.meshFor(hex);
            if (m.count < this.MAX) {
                this.dummy.position.set(px, py, pz);
                this.dummy.scale.set(1, 1, 1);
                this.dummy.updateMatrix();
                m.setMatrixAt(m.count, this.dummy.matrix);
                m.count++;
            }
        }
        Object.values(this.meshes).forEach(m => {
            m.instanceMatrix.needsUpdate = true;
        });
    },

    meshFor(hex) {
        if (!this.meshes[hex]) {
            const m = new this.three.InstancedMesh(
                this.geo, new this.three.MeshBasicMaterial({ color: hex }),
                this.MAX);
            m.instanceMatrix.setUsage(this.three.DynamicDrawUsage);
            this.dummy.scale.set(0, 0, 0);
            this.dummy.updateMatrix();
            for (let i = 0; i < this.MAX; i++) m.setMatrixAt(i, this.dummy.matrix);
            m.instanceMatrix.needsUpdate = true;
            m.count = 0;
            this.group.add(m);
            this.meshes[hex] = m;
        }
        return this.meshes[hex];
    },

    onParam(params) {
        if (params.size !== undefined && params.size !== this.size) {
            this.size = params.size;
            // 尺寸改变:重建共享几何(所有实例共用)
            this.geo.dispose();
            this.geo = new this.three.SphereGeometry(this.size, 8, 8);
            Object.values(this.meshes).forEach(m => { m.geometry = this.geo; });
        }
    },

    dispose() {
        Object.values(this.meshes).forEach(m => {
            m.geometry.dispose();
            m.material.dispose();
        });
        this.group.parent && this.group.parent.remove(this.group);
    },
});
