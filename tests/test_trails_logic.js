// 粒子拖尾逻辑回归测试(纯 Node,无需浏览器/服务器)。
//
// 覆盖 2026-09 定位到的三类拖尾 bug(用户反馈"拖尾逻辑有 BUG"):
//   ① 粒子数变少(换预设/调小粒子数)→ 旧槽位永远挂着冻结拖尾(幽灵拖尾)
//   ② 轨迹未满时按整圈读取环形缓冲 → 读到残值,拖出一条直线
//      (实测未修前:第 1 帧后就有 ~6.6 Re 的线段指向原点)
//   ③ trail_length=0 被兜成 2 → "关闭"其实画了一段
// 另覆盖:改 trail_length 后各槽位环形缓冲必须重建(否则越界写被静默丢弃 → NaN 顶点)
//
// 运行: node tests/test_trails_logic.js
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

// ---- 极简 three 桩:只实现拖尾用到的接口 ----
function makeTHREE() {
    class BufferAttribute {
        constructor(array, itemSize) { this.array = array; this.itemSize = itemSize; this.needsUpdate = false; }
    }
    class BufferGeometry {
        constructor() { this.attrs = {}; this.index = null; }
        setIndex(a) { this.index = a; }
        setAttribute(n, a) { this.attrs[n] = a; }
        getAttribute(n) { return this.attrs[n]; }
        dispose() { }
    }
    class LineBasicMaterial {
        constructor(p) { Object.assign(this, p || {}); }
        dispose() { }
    }
    class LineSegments {
        constructor(g, m) { this.geometry = g; this.material = m; this.visible = true; this.frustumCulled = true; }
    }
    class Group {
        constructor() { this.children = []; this.parent = null; }
        add(o) { this.children.push(o); o.parent = this; }
        remove(o) { const i = this.children.indexOf(o); if (i >= 0) this.children.splice(i, 1); }
    }
    return { BufferAttribute, BufferGeometry, LineBasicMaterial, LineSegments, Group };
}

// ---- 载入被测模块(registerRenderItem 打桩捕获 spec)----
const THREE = makeTHREE();
let spec = null;
const sandbox = {
    THREE,
    registerRenderItem: (s) => { spec = s; },
    console,
    TextDecoder,
    DataView, ArrayBuffer, Uint8Array, Float32Array, Uint32Array, Math, JSON,
};
const file = path.join(__dirname, "..", "static", "renderer", "items", "trails.js");
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(file, "utf8"), sandbox, { filename: file });
if (!spec) { console.error("未捕获 registerRenderItem"); process.exit(1); }

// ---- 合成粒子帧(与协议同布局:4B 头长 + JSON 头 + 21B/粒子)----
function frame(list) {
    const hb = Buffer.from(JSON.stringify({ type: "s", n: list.length, t: 0, v: 209 }));
    const buf = new ArrayBuffer(4 + hb.length + list.length * 21);
    const v = new DataView(buf);
    v.setUint32(0, hb.length, true);
    new Uint8Array(buf, 4, hb.length).set(hb);
    let off = 4 + hb.length;
    for (const p of list) {
        v.setInt32(off, p.id, true);
        v.setFloat32(off + 4, p.x, true);
        v.setFloat32(off + 8, p.y, true);
        v.setFloat32(off + 12, p.z, true);
        v.setUint8(off + 16, p.st | 0);
        v.setUint32(off + 17, p.color >>> 0, true);
        off += 21;
    }
    return buf;
}

let fails = 0;
function check(name, cond, detail) {
    if (cond) { console.log(`✓ ${name}${detail ? "  " + detail : ""}`); }
    else { console.log(`✗ ${name}  ${detail || ""}`); fails++; }
}

// 每个槽位的最大段长(>0 表示真的会画出东西)
function drawnSlots(it) {
    const L = it.trailLen, pos = it.posAttr.array;
    let drawn = 0;
    for (let s = 0; s < it.maxSlots; s++) {
        if (!it.slots[s]) continue;
        const g = s * L;
        let m = 0;
        for (let j = 0; j + 1 < L; j++) {
            const a = (g + j) * 3, b = (g + j + 1) * 3;
            m = Math.max(m, Math.hypot(pos[b] - pos[a], pos[b + 1] - pos[a + 1], pos[b + 2] - pos[a + 2]));
        }
        if (m > 1e-6) drawn++;
    }
    return drawn;
}

// ---------- ① 幽灵拖尾:6000 → 1 ----------
const it = Object.assign({}, spec);
it.setup(new THREE.Group(), THREE);
it.onParam({ trail_length: 8, opacity: 0.5, visible: true });
const N = 6000;
let big = [];
for (let i = 0; i < N; i++) big.push({ id: (i + 1) * 7, x: 1 + i * 0.0007, y: 0.4, z: -0.3, st: 0, color: 0xff5555 });
for (let k = 0; k < 3; k++) { big = big.map(p => ({ ...p, x: p.x + 0.04 })); it.onData(frame(big)); }
check("6000 粒子帧:全部槽位有轨迹", drawnSlots(it) === N, `drawn=${drawnSlots(it)} maxSlots=${it.maxSlots}`);
it.onData(frame([{ id: 424242, x: 6.6, y: 0, z: 0, st: 0, color: 0x5599ff }]));
for (let k = 1; k <= 4; k++) {
    it.onData(frame([{ id: 424242, x: 6.6 + k * 0.05, y: k * 0.02, z: 0, st: 0, color: 0x5599ff }]));
}
check("收缩到 1 个粒子:只剩 1 条轨迹(无幽灵)", drawnSlots(it) === 1,
    `drawn=${drawnSlots(it)} 塌缩=${it.maxSlots - drawnSlots(it)}`);

// ---------- ② 未满轨迹不得拖出直线 ----------
const it2 = Object.assign({}, spec);
it2.setup(new THREE.Group(), THREE);
it2.onParam({ trail_length: 300, visible: true });
it2.onData(frame([{ id: 1, x: 6.6, y: 0, z: 0, st: 0, color: 0xffffff }]));
const L2 = it2.trailLen, pos2 = it2.posAttr.array;
let maxSeg = 0, zeroSeg = 0;
for (let j = 0; j + 1 < L2; j++) {
    const a = j * 3, b = (j + 1) * 3;
    const d = Math.hypot(pos2[b] - pos2[a], pos2[b + 1] - pos2[a + 1], pos2[b + 2] - pos2[a + 2]);
    if (d === 0) zeroSeg++; else maxSeg = Math.max(maxSeg, d);
}
check("第 1 帧:未满部分零长(不拖向原点/残值)", maxSeg === 0 && zeroSeg === L2 - 1,
    `segMax=${maxSeg.toFixed(4)} 零长段=${zeroSeg}/${L2 - 1}`);

// ---------- ③ trail_length=0 = 关闭(且首帧就要生效)----------
const it3 = Object.assign({}, spec);
it3.setup(new THREE.Group(), THREE);
it3.onParam({ trail_length: 0, visible: true });   // 尚无几何:onParam 无法重建
it3.onData(frame([{ id: 1, x: 3, y: 0, z: 0, st: 0, color: 0xffffff }]));
check("trail_length=0:参数首帧即落地且线隐藏", it3.trailLen === 0 && it3.line.visible === false,
    `trailLen=${it3.trailLen} visible=${it3.line.visible}`);

// ---------- ④ 改 trail_length 后槽位缓冲必须重建(不能越界写) ----------
const it4 = Object.assign({}, spec);
it4.setup(new THREE.Group(), THREE);
it4.onParam({ trail_length: 4, visible: true });
it4.onData(frame([{ id: 1, x: 1, y: 1, z: 1, st: 0, color: 0xffffff }]));
it4.onParam({ trail_length: 64 });
it4.onData(frame([{ id: 1, x: 2, y: 2, z: 2, st: 0, color: 0xffffff }]));
check("改 trail_length:槽位缓冲随之重建(无越界)", it4.slots[0].buf.length === 64 * 3,
    `bufLen=${it4.slots[0].buf.length} 期望=${64 * 3}`);
const pos4 = it4.posAttr.array;
let bad = 0;
for (let j = 0; j < 64 * 3; j++) if (!Number.isFinite(pos4[j])) bad++;
check("改 trail_length:GPU 顶点无 NaN", bad === 0, `NaN=${bad}`);

console.log(fails === 0 ? "\n拖尾逻辑回归全部通过 ✅" : `\n拖尾逻辑回归失败 ${fails} 项 ❌`);
process.exit(fails === 0 ? 0 : 1);
