// 渲染项插件示例:俯仰角锥(与 nodes/render_item_pitch_cone.py 配对)
//
// 契约(#32):
//   - 节点规格声明 inputs={"data": Port("source_spec")} + channels=["source_preview"]
//   - **接线决定订阅**:data 接到「单粒子注入.spec」才订阅该通道;拔线即停
//   - onData(payload):本插件消费的载荷 = {pos, dir|null, bdir|null, vmag,
//     b_nt, r_g_re, gyro_s, pitch, phase, note}(场景坐标,GSM→Three 已换算)
//   - 宿主按 layer 分层挂载;onParam 收到节点参数;dispose 释放资源
//
// 画法:以 b̂ 为轴、pitch 为半顶角画一个漏斗(若干参考环 + 母线),
// 直观显示 v 与 B 的夹角;有 v̂ 时再补一条中心速度线。
registerRenderItem({
    id: "pitch_cone",
    layer: 3,
    subscribes: ["source_preview"],   // 无接线信息时的默认订阅

    setup(scene, three) {
        this.three = three;
        this.group = new three.Group();
        this.group.visible = false;
        this.rings = [];
        this.spokes = [];
        this.axis = null;
        this.params = {};
        scene.add(this.group);
    },

    _clear() {
        for (const o of [...this.rings, ...this.spokes]) {
            o.geometry.dispose();
            o.material.dispose();
            this.group.remove(o);
        }
        this.rings = [];
        this.spokes = [];
        if (this.axis) { this.group.remove(this.axis); this.axis = null; }
    },

    // 以 axis(单位矢量)为轴、半顶角 half(弧度)画漏斗
    _build(origin, axis, half) {
        this._clear();
        const three = this.three;
        const R = Math.max(0.1, this.params.radius !== undefined ? this.params.radius : 1.6);
        const nRings = Math.max(1, this.params.rings !== undefined ? this.params.rings : 3);
        const color = new three.Color(this.params.color || "#ffcc66");
        const opacity = this.params.opacity !== undefined ? this.params.opacity : 0.35;

        // 正交基(轴, e1, e2)
        const up = Math.abs(axis.y) > 0.9 ? new three.Vector3(1, 0, 0)
                                          : new three.Vector3(0, 1, 0);
        const e1 = new three.Vector3().crossVectors(axis, up).normalize();
        const e2 = new three.Vector3().crossVectors(axis, e1).normalize();
        const tan = Math.tan(Math.max(0.01, Math.min(Math.PI / 2 - 0.01, half)));

        for (let r = 1; r <= nRings; r++) {
            const L = R * r / nRings;                 // 沿轴的深度
            const rad = L * tan;                      // 该深度处的锥半径
            const pts = [];
            for (let i = 0; i <= 48; i++) {
                const th = (i / 48) * Math.PI * 2;
                pts.push(new three.Vector3()
                    .copy(origin)
                    .addScaledVector(axis, L)
                    .addScaledVector(e1, rad * Math.cos(th))
                    .addScaledVector(e2, rad * Math.sin(th)));
            }
            const geo = new three.BufferGeometry().setFromPoints(pts);
            const mat = new three.LineBasicMaterial({
                color, transparent: true,
                opacity: opacity + 0.25 * (r / nRings) });
            const ring = new three.Line(geo, mat);
            this.group.add(ring);
            this.rings.push(ring);
        }
        // 母线(4 条)
        const tipRad = R * tan;
        for (let k = 0; k < 4; k++) {
            const th = (k / 4) * Math.PI * 2;
            const end = new three.Vector3()
                .copy(origin)
                .addScaledVector(axis, R)
                .addScaledVector(e1, tipRad * Math.cos(th))
                .addScaledVector(e2, tipRad * Math.sin(th));
            const geo = new three.BufferGeometry().setFromPoints([origin.clone(), end]);
            const mat = new three.LineBasicMaterial({
                color, transparent: true, opacity: Math.min(0.9, opacity + 0.25) });
            const spoke = new three.Line(geo, mat);
            this.group.add(spoke);
            this.spokes.push(spoke);
        }
    },

    onData(p) {
        if (!p || !p.pos || !p.bdir || typeof p.pitch !== "number") {
            this.group.visible = false;
            return;
        }
        const three = this.three;
        const origin = new three.Vector3(p.pos[0], p.pos[1], p.pos[2]);
        const axis = new three.Vector3(p.bdir[0], p.bdir[1], p.bdir[2]).normalize();
        const half = (p.pitch * Math.PI) / 180;   // 半顶角 = 俯仰角
        this._build(origin, axis, half);

        // 中心速度线(沿 v̂,若服务器给了方向)
        if (p.dir) {
            const v = new three.Vector3(p.dir[0], p.dir[1], p.dir[2]).normalize();
            const L = Math.max(0.8, Math.min(6.0, (p.vmag || 400) / 250));
            const geo = new three.BufferGeometry().setFromPoints(
                [origin.clone(), origin.clone().addScaledVector(v, L)]);
            const mat = new three.LineBasicMaterial({ color: 0x66ffcc });
            const line = new three.Line(geo, mat);
            this.group.add(line);
            this.spokes.push(line);
        }
        this.group.visible = this.params.visible !== false;
    },

    onParam(params) {
        this.params = Object.assign({}, this.params, params);
        if (params.visible === false) this.group.visible = false;
    },

    dispose() {
        this._clear();
        this.group.parent && this.group.parent.remove(this.group);
    },
});
