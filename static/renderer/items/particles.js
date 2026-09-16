// 内置渲染项:粒子(21B/粒子帧)。
registerRenderItem({
    id: "particles",
    pickable: true,          // #43:参与可视化选择(点击拾取)
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
        this.raycaster = new three.Raycaster();
        this.raycaster.params.Line = { threshold: 0.1 };
        this._sel = new Set();
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
            const id = view.getInt32(off, true);      // #43 拾取需要 id(原项没读)
            const status = view.getUint8(off + 16);
            const color = view.getUint32(off + 17, true);
            off += 21;
            if (status !== 0) continue;
            const hex = "#" + color.toString(16).padStart(6, "0");
            const m = this.meshFor(hex);

        if (m.count < this.MAX) {
                // #43 实例→id 映射(拾取用)+ 选中放大;必须写在真正写入处,
                // 与 m.count 同步(此前放在 m 定义之前 → TDZ/id 未定义 → 粒子全消失)
                const sel = this._sel && this._sel.has(id);          // 锁定(点击)
                const hov = this._hoverId === id;                    // 悬停(光标索引)
                if (!m.userData.ids) m.userData.ids = [];
                m.userData.ids[m.count] = id;
                this.dummy.position.set(px, py, pz);
                const sc = sel ? 2.6 : (hov ? 1.8 : 1);
                this.dummy.scale.set(sc, sc, sc);
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

    // ---- #43 可视化选择 ----
    onHover(id) { this._hoverId = (id === undefined ? null : id); },

    onSelect(sel) {
        const ids = (sel && sel.kind === "particle") ? sel.ids : [];
        this._sel = new Set(ids || []);
    },

    // 屏幕坐标(clientX/Y)→ 命中粒子 id(用相机射线打 InstancedMesh)
    pick(clientX, clientY) {
        const host = window.renderHost;
        const cam = host && host.camera;
        const dom = host && host.renderer3d && host.renderer3d.domElement;
        if (!cam || !dom || !this.raycaster) return null;
        const r = dom.getBoundingClientRect();
        const ndc = new this.three.Vector2(
            ((clientX - r.left) / r.width) * 2 - 1,
            -((clientY - r.top) / r.height) * 2 + 1);
        this.raycaster.setFromCamera(ndc, cam);
        const hits = this.raycaster.intersectObjects(Object.values(this.meshes), false);
        for (const h of hits) {
            const ids = h.object && h.object.userData && h.object.userData.ids;
            if (ids && h.instanceId !== undefined && ids[h.instanceId] !== undefined) {
                return { itemId: this.id, kind: "particle",
                         ids: [ids[h.instanceId]] };
            }
        }
        // 容差回退:粒子在屏幕上只有几像素,纯射线几乎点不中 →
        // 投影所有实例,取屏幕距离最近且落在容差内的那个(默认 16 px)
        if (!this._pickTmp) {
            this._pickTmp = new this.three.Vector3();
            this._pickMat = new this.three.Matrix4();
        }
        let bestId = null, bestD = this.pickTolerance || 16;
        for (const mesh of Object.values(this.meshes)) {
            const ids = mesh.userData.ids || [];
            for (let k = 0; k < mesh.count; k++) {
                mesh.getMatrixAt(k, this._pickMat);
                this._pickTmp.setFromMatrixPosition(this._pickMat).project(cam);
                const sx = r.left + (this._pickTmp.x + 1) * 0.5 * r.width;
                const sy = r.top + (-this._pickTmp.y + 1) * 0.5 * r.height;
                const d = Math.hypot(sx - clientX, sy - clientY);
                if (d < bestD && ids[k] !== undefined) { bestD = d; bestId = ids[k]; }
            }
        }
        return bestId !== null
            ? { itemId: this.id, kind: "particle", ids: [bestId] }
            : null;
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
