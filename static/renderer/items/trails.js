// 内置渲染项:粒子拖尾(REFACTOR_PLAN 债务 D9)。
//
// 零额外带宽:轨迹完全由客户端从"已经收到的粒子帧"推导 ——
// 每帧 21B/粒子照旧,服务器与协议都不变;代价仅为客户端内存/CPU
// (粒子数 × 拖尾长度 × 顶点,可按 trail_length 参数调节或关闭)。
//
// 实现(新写,不搬 legacy 的 per-color 大缓冲方案):
// - 每粒子槽位一个 Float32Array 环形缓冲(槽位 = 帧内序号,跨帧稳定)
// - 单一 THREE.LineSegments + vertexColors:全色一次 draw call
// - 拓扑静态(预建索引),退化线段 = 未满槽位重复最老点(零长,GPU 丢弃)
// - 重生检测:槽位内粒子 id 变化 → 清空重画(不出现跨屏直线);
//   死亡粒子(status!=0)冻结轨迹,不回填新点
registerRenderItem({
    id: "particle_trails",
    layer: 2,
    subscribes: ["particles"],

    setup(scene, three) {
        this.three = three;
        this.group = new three.Group();
        this.trailLen = 30;      // 每粒子轨迹点数(节点参数)
        this.maxSlots = 0;       // 槽位上限(按帧内粒子数生长)
        this.slots = [];         // slot -> {buf, idx, cnt, id}
        this.posAttr = null;
        this.colAttr = null;
        this.geo = null;
        this.line = null;
        this.params = {};
        scene.add(this.group);
    },

    // 重建几何(槽位上限/拖尾长度变化时)
    rebuild(maxSlots, trailLen) {
        this.maxSlots = maxSlots;
        this.trailLen = Math.max(2, trailLen | 0);
        const L = this.trailLen;
        const nVerts = maxSlots * L;

        // 顶点:位置 + 顶点色(每粒子槽位 L 个点)
        const pos = new Float32Array(nVerts * 3);
        const col = new Float32Array(nVerts * 3);
        // 静态索引:每槽位 (L-1) 条线段
        const idx = new Uint32Array(maxSlots * (L - 1) * 2);
        let o = 0;
        for (let s = 0; s < maxSlots; ++s) {
            const base = s * L;
            for (let j = 0; j < L - 1; ++j) {
                idx[o++] = base + j;
                idx[o++] = base + j + 1;
            }
        }
        const geo = new this.three.BufferGeometry();
        geo.setIndex(new this.three.BufferAttribute(idx, 1));
        geo.setAttribute("position", new this.three.BufferAttribute(pos, 3));
        geo.setAttribute("color", new this.three.BufferAttribute(col, 3));
        const mat = new this.three.LineBasicMaterial({
            vertexColors: true,
            transparent: true,
            opacity: this.params.opacity !== undefined ? this.params.opacity : 0.55,
        });
        const line = new this.three.LineSegments(geo, mat);
        line.frustumCulled = false;

        // 替换场景中的旧对象
        if (this.line) {
            this.line.geometry.dispose();
            this.line.material.dispose();
            this.group.remove(this.line);
        }
        this.posAttr = geo.getAttribute("position");
        this.colAttr = geo.getAttribute("color");
        this.geo = geo;
        this.line = line;
        this.group.add(line);
        this.onParam(this.params);
    },

    onData(frame) {
        const buf = frame instanceof ArrayBuffer ? frame : frame.buffer;
        const view = new DataView(buf);
        const hlen = view.getUint32(0, true);
        const header = JSON.parse(new TextDecoder().decode(
            new Uint8Array(buf, 4, hlen)));
        const n = header.n;
        if (n <= 0) return;

        if (n > this.maxSlots) this.rebuild(n, this.trailLen);
        const L = this.trailLen;
        const pos = this.posAttr.array;
        const col = this.colAttr.array;

        let off = 4 + hlen;
        for (let i = 0; i < n; i++) {
            const id = view.getInt32(off, true);
            const px = view.getFloat32(off + 4, true);
            const py = view.getFloat32(off + 8, true);
            const pz = view.getFloat32(off + 12, true);
            const status = view.getUint8(off + 16);
            const color = view.getUint32(off + 17, true);
            off += 21;

            let slot = this.slots[i];
            if (!slot) {
                slot = { buf: new Float32Array(L * 3), idx: 0, cnt: 0, id: null };
                this.slots[i] = slot;
            }
            // 重生/换粒子:清空轨迹(避免跨屏直线)
            if (slot.id !== id) {
                slot.id = id;
                slot.idx = 0;
                slot.cnt = 0;
                for (let j = 0; j < L; ++j) {
                    slot.buf[j * 3] = px;
                    slot.buf[j * 3 + 1] = py;
                    slot.buf[j * 3 + 2] = pz;
                }
            }
            // 存活:追加历史点;死亡:冻结(不回填)
            if (status === 0) {
                const w = slot.idx * 3;
                slot.buf[w] = px;
                slot.buf[w + 1] = py;
                slot.buf[w + 2] = pz;
                slot.idx = (slot.idx + 1) % L;
                if (slot.cnt < L) slot.cnt++;
            }

            // 时间序写入 GPU 缓冲(最新点 = idx-1);未满部分重复最老点
            const r = (slot.idx - 1 + L) % L;  // 最新写入位置
            const g0 = i * L;
            const fr = (color >> 16 & 255) / 255;
            const fg = (color >> 8 & 255) / 255;
            const fb = (color & 255) / 255;
            for (let j = 0; j < L; ++j) {
                const src = ((r - j) % L + L) % L;  // 从新到老
                const gi = g0 + j;
                pos[gi * 3] = slot.buf[src * 3];
                pos[gi * 3 + 1] = slot.buf[src * 3 + 1];
                pos[gi * 3 + 2] = slot.buf[src * 3 + 2];
                col[gi * 3] = fr;
                col[gi * 3 + 1] = fg;
                col[gi * 3 + 2] = fb;
            }
        }
        this.posAttr.needsUpdate = true;
        this.colAttr.needsUpdate = true;
    },

    onParam(params) {
        this.params = Object.assign({}, this.params, params);
        if (this.line) {
            this.line.visible = this.params.visible !== false;
            this.line.material.opacity =
                this.params.opacity !== undefined ? this.params.opacity : 0.55;
            if (this.params.trail_length !== undefined &&
                (this.params.trail_length | 0) !== this.trailLen) {
                this.rebuild(this.maxSlots || 1, this.params.trail_length | 0);
            }
        }
    },

    dispose() {
        if (this.line) {
            this.line.geometry.dispose();
            this.line.material.dispose();
        }
        this.group.parent && this.group.parent.remove(this.group);
    },
});
