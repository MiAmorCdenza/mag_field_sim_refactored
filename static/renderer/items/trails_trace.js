// 粒子轨迹渲染项(累积式)—— "不消失的尾迹"(#48)
//
// 与 items/trails.js(固定长度环形缓冲)**并列的独立插件**,原文件一行不改:
//   · trails.js        : 尾部模式 —— 永远只保留最近 trail_length 个点(旧的被覆盖)
//   · trails_trace.js  : 累积模式 —— 一路记录;写满上限后**冻结但保留**(不清空、不回卷)
//
// 数据来源与拖尾完全一致:订阅 ["particles"] 粒子帧(零额外带宽),从帧里解析
// [id:i32][x/y/z:f32][status:u8][color:u32] (21 B/粒子)。
//
// 关键实现(按方案 A):
//   1) 可增长记录:每粒子累计点数;容量按需翻倍到 max_points 后**只读不再写**
//   2) 增量绘制:用共享**追加式顶点竞技场**(LineSegments,每新增一点追加一段),
//      只更新新增片段的 updateRange —— 不用每帧重写整条线
//   3) 预算守卫:总段数 ≤ BUDGET(20 万);`max_traced_particles` 限制"只前 K 个粒子累积",
//      其余粒子不记录;触顶/超出时**只提示一次**,避免静默降级
//   4) 生命周期:真的移动了才记点(暂停自动冻结)、重生(id 变)清掉该粒子并重开轨迹、
//      改参数重建**不丢**已记录轨迹、粒子数变少不影响已画部分
registerRenderItem({
    id: "particle_trace",
    layer: 2,
    subscribes: ["particles"],

    setup(scene, three) {
        this.three = three;
        const BUDGET = 200000;                     // 全局段预算(1 段 = 2 顶点)
        this.budget = BUDGET;
        this.pos = new Float32Array(BUDGET * 2 * 3);
        this.col = new Float32Array(BUDGET * 2 * 3);
        this.posAttr = new three.BufferAttribute(this.pos, 3);
        this.colAttr = new three.BufferAttribute(this.col, 3);
        this.posAttr.setUsage(three.DynamicDrawUsage);
        this.colAttr.setUsage(three.DynamicDrawUsage);
        this.geo = new three.BufferGeometry();
        this.geo.setAttribute("position", this.posAttr);
        this.geo.setAttribute("color", this.colAttr);
        this.geo.setDrawRange(0, 0);
        this.mat = new three.LineBasicMaterial({
            vertexColors: true, transparent: true,
            opacity: (this.params && this.params.opacity !== undefined)
                     ? this.params.opacity : 0.9,
        });
        this.line = new three.LineSegments(this.geo, this.mat);
        this.line.frustumCulled = false;           // 轨迹会跑出初始包围盒
        scene.add(this.line);

        this.slots = new Map();                    // 粒子 id → {n, px, py, pz, rgb}
        this.used = 0;                             // 已写段数
        this.traced = new Set();                   // 已纳入累积的粒子 id(只前 K 个)
        this.warned = {};
    },

    onParam(p) {
        if (p && p.opacity !== undefined && this.mat) this.mat.opacity = p.opacity;
    },

    warnOnce(key, msg) {
        if (this.warned[key]) return;
        this.warned[key] = true;
        if (window.uiLog) window.uiLog("warn", "particle_trace", msg, {});
        console.warn("[particle_trace]", msg);
    },

    maxPoints() {
        const v = this.params && this.params.max_points;
        return (typeof v === "number" && v > 0) ? Math.min(v, this.budget) : 20000;
    },
    maxTraced() {
        const v = this.params && this.params.max_traced_particles;
        return (typeof v === "number" && v > 0) ? v : 8;
    },

    onData(a, b) {
        // 宿主可能传 ArrayBuffer 或 {buffer}(两种都兼容)
        const buf = (a instanceof ArrayBuffer) ? a
                  : (b instanceof ArrayBuffer) ? b
                  : (a && a.buffer) ? a.buffer : null;
        if (!buf || buf.byteLength < 8) return;
        const view = new DataView(buf);
        const hlen = view.getUint32(0, true);
        const header = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 4, hlen)));
        const n = header.n | 0;
        const L = this.maxPoints();
        const K = this.maxTraced();
        let off = 4 + hlen;

        for (let i = 0; i < n; i++) {
            const id = view.getInt32(off, true);
            const px = view.getFloat32(off + 4, true);
            const py = view.getFloat32(off + 8, true);
            const pz = view.getFloat32(off + 12, true);
            const status = view.getUint8(off + 16);
            const color = view.getUint32(off + 17, true);
            off += 21;
            if (status !== 0) continue;            // 死亡:不再记点(已画部分保留)

            // 只对前 K 个(按帧序)粒子做累积,其余不记录
            let s = this.slots.get(id);
            if (!s) {
                if (this.traced.size >= K) {
                    this.warnOnce("k", "累积轨迹仅对前 " + K +
                                  " 个粒子生效(其余粒子不记录;可调 max_traced_particles)");
                    continue;
                }
                this.traced.add(id);
                s = { n: 0, px: 0, py: 0, pz: 0,
                      rgb: [(color >> 16 & 255) / 255, (color >> 8 & 255) / 255,
                            (color & 255) / 255] };
                this.slots.set(id, s);
            }
            if (s.n === 0) {                       // 第一个点:只记不画
                s.px = px; s.py = py; s.pz = pz; s.n = 1;
                continue;
            }
            // 真的移动了才记(暂停时位置不变 → 自动冻结)
            const moved = Math.abs(px - s.px) + Math.abs(py - s.py) + Math.abs(pz - s.pz) > 1e-6;
            if (!moved) continue;
            if (s.n >= L) {                        // 单粒子写满:冻结但保留
                this.warnOnce("cap", "轨迹已达 max_points=" + L + " → 停止记录但保留轨迹");
                continue;
            }
            if (this.used >= this.budget) {        // 全局预算触顶:全部冻结(保留)
                this.warnOnce("budget", "轨迹总预算已满 → 停止记录但保留轨迹");
                continue;
            }
            // 追加一段:上一个点 → 当前点
            const u = this.used;
            const p = this.pos, c = this.col;
            const o1 = u * 6, o2 = o1 + 3;
            p[o1] = s.px; p[o1 + 1] = s.py; p[o1 + 2] = s.pz;
            p[o2] = px;   p[o2 + 1] = py;   p[o2 + 2] = pz;
            for (let k = 0; k < 3; k++) {
                c[o1 + k] = s.rgb[k];
                c[o2 + k] = s.rgb[k];
            }
            this.used++;
            s.px = px; s.py = py; s.pz = pz; s.n++;

            // 只更新新增片段,不重写整条线
            this.posAttr.updateRange = { offset: o1, count: 6 };
            this.colAttr.updateRange = { offset: o1, count: 6 };
        }
        if (this.used > 0) {
            this.geo.setDrawRange(0, this.used * 2);
            this.posAttr.needsUpdate = true;
            this.colAttr.needsUpdate = true;
        }
    },

    // 重生/换粒子(id 变)→ 清掉该粒子并重开轨迹(旧段留在竞技场里,不再增长)
    resetParticle(id) {
        if (this.slots.has(id)) { this.slots.delete(id); this.traced.delete(id); }
    },

    // 手动清空(预设切换/重置粒子时可调)
    clear() {
        this.slots.clear();
        this.traced.clear();
        this.used = 0;
        this.geo.setDrawRange(0, 0);
        this.posAttr.needsUpdate = true;
        this.colAttr.needsUpdate = true;
    },

    dispose() {
        if (this.line && this.line.parent) this.line.parent.remove(this.line);
        if (this.geo) this.geo.dispose();
        if (this.mat) this.mat.dispose();
    },
});
