// 内置渲染项:单粒子初条件预览(particle_injection 节点)。
//
// L1:编辑器本地计算 —— 参数一变即时刷新,零服务器依赖、零带宽。
//   拖滑杆 → editor.js 算出生点/速度矢量 → dispatch("source_preview", payload)
//   限制:俯仰角模式(vpitch)需要局部 B 方向,本地拿不到 → 只画生成点。
// L2:服务器在计划应用/烘焙后广播 source_preview(含局部 B 与同一套注入
//   数学给出的速度方向)→ 同一渲染项消费,额外画出 b̂ 箭头(俯仰角参照)。
//   两路载荷同构:{pos, dir|null, bdir|null, vmag, b_nt, r_g_re, gyro_s, note}
registerRenderItem({
    id: "source_preview",
    layer: 3,
    subscribes: ["source_preview"],

    setup(scene, three) {
        this.three = three;
        this.group = new three.Group();

        // 生成点标记
        this.marker = new three.Mesh(
            new three.SphereGeometry(0.16, 16, 16),
            new three.MeshBasicMaterial({ color: 0xffe066 }));
        // 外圈(区分于普通粒子)
        this.halo = new three.Mesh(
            new three.SphereGeometry(0.28, 12, 12),
            new three.MeshBasicMaterial({ color: 0xffe066, transparent: true,
                                          opacity: 0.25 }));
        // 速度矢量箭头
        this.arrow = new three.ArrowHelper(
            new three.Vector3(0, 0, 1), new three.Vector3(), 3.0,
            0x66ffcc, 0.6, 0.35);
        // 局部 B 方向(俯仰角参照;由 L2 服务器预览提供)
        this.barrow = new three.ArrowHelper(
            new three.Vector3(0, 0, 1), new three.Vector3(), 2.0,
            0x5599ff, 0.45, 0.28);

        this.group.add(this.marker);
        this.group.add(this.halo);
        this.group.add(this.arrow);
        this.group.add(this.barrow);
        this.group.visible = false;
        this.params = {};
        scene.add(this.group);
    },

    // payload: {pos:[x,y,z], dir:[dx,dy,dz]|null, bdir, vmag, note}
    // pos = 渲染坐标系(Three 约定 x, z, -y);dir/bdir 已归一化
    onData(p) {
        if (!p || !p.pos) { this.group.visible = false; return; }
        this.marker.position.set(p.pos[0], p.pos[1], p.pos[2]);
        this.halo.position.copy(this.marker.position);
        if (p.dir) {
            const v = new this.three.Vector3(p.dir[0], p.dir[1], p.dir[2]);
            if (v.lengthSq() > 1e-12) {
                this.arrow.position.copy(this.marker.position);
                this.arrow.setDirection(v.normalize());
                const L = Math.max(0.8, Math.min(6.0, (p.vmag || 400) / 250));
                this.arrow.setLength(L, L * 0.20, L * 0.12);
                this.arrow.visible = true;
            } else {
                this.arrow.visible = false;
            }
        } else {
            this.arrow.visible = false;
        }
        if (p.bdir) {
            const b = new this.three.Vector3(p.bdir[0], p.bdir[1], p.bdir[2]);
            if (b.lengthSq() > 1e-12) {
                this.barrow.position.copy(this.marker.position);
                this.barrow.setDirection(b.normalize());
                this.barrow.visible = true;
            } else {
                this.barrow.visible = false;
            }
        } else {
            this.barrow.visible = false;
        }
        this.group.visible = this.params.visible !== false;
    },

    onParam(params) {
        this.params = Object.assign({}, this.params, params);
        if (this.params.visible === false) this.group.visible = false;
        const col = this.params.color;
        if (col) {
            const c = new this.three.Color(col);
            this.marker.material.color.copy(c);
            this.halo.material.color.copy(c);
        }
        if (this.params.marker_size !== undefined) {
            const s = this.params.marker_size;
            this.marker.scale.setScalar(s);
            this.halo.scale.setScalar(s);
        }
    },

    dispose() {
        this.marker.geometry.dispose();
        this.marker.material.dispose();
        this.halo.geometry.dispose();
        this.halo.material.dispose();
        this.arrow.dispose && this.arrow.dispose();
        this.barrow.dispose && this.barrow.dispose();
        this.group.parent && this.group.parent.remove(this.group);
    },
});
