// 渲染宿主:场景分层(L0静态/L1场几何/L2粒子/L3覆盖)、渲染循环、帧分发器。
window.renderHost = (function () {
    "use strict";
    const container = document.getElementById("viewport");

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0d1117);

    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 10000);
    camera.position.set(14, 8, 14);

    const renderer3d = new THREE.WebGLRenderer({ antialias: true });
    renderer3d.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(renderer3d.domElement);

    const controls = new THREE.OrbitControls(camera, renderer3d.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;

    // ---- 分层场景图 ----
    const layers = {};
    [0, 1, 2, 3].forEach(i => {
        const g = new THREE.Group();
        g.name = "L" + i;
        scene.add(g);
        layers[i] = g;
    });

    // ---- L0 静态场景 ----
    layers[0].add(new THREE.AmbientLight(0x404040));
    const sun = new THREE.DirectionalLight(0xffffff, 1);
    sun.position.set(5, 3, 5);
    layers[0].add(sun);

    const earth = new THREE.Mesh(
        new THREE.SphereGeometry(1.0, 32, 32),
        new THREE.MeshPhongMaterial({ color: 0x1a5276, emissive: 0x0a1a2a }));
    layers[0].add(earth);

    const scaleRadii = [2, 4, 6, 8, 10, 15, 20, 30, 40, 50, 60, 70, 80, 90];
    scaleRadii.forEach(r => {
        const pts = [];
        for (let i = 0; i <= 64; i++) {
            const th = (i / 64) * Math.PI * 2;
            pts.push(new THREE.Vector3(r * Math.cos(th), 0, r * Math.sin(th)));
        }
        const major = r % 10 === 0;
        const geo = new THREE.BufferGeometry().setFromPoints(pts);
        const mat = new THREE.LineDashedMaterial({
            color: major ? 0x666666 : 0x333333, dashSize: 0.4, gapSize: 0.4,
            transparent: true, opacity: major ? 0.55 : 0.25 });
        const line = new THREE.Line(geo, mat);
        line.computeLineDistances();
        layers[0].add(line);
    });

    layers[0].add(new THREE.ArrowHelper(
        new THREE.Vector3(1, 0, 0), new THREE.Vector3(), 4, 0xffff00, 0.4, 0.3));
    const tilt = 23.44 * Math.PI / 180;
    const rotAxis = new THREE.Vector3(Math.sin(tilt), Math.cos(tilt), 0).normalize();
    layers[0].add(new THREE.ArrowHelper(
        rotAxis, new THREE.Vector3(), 2.6, 0x00ff00, 0.3, 0.2));

    // ---- 渲染项实例表 ----
    const items = new Map();  // id -> 渲染项实例(registry 的 per-node 拷贝)

    function registerItem(spec) {
        if (!spec || !spec.id) throw new Error("渲染项必须提供 id");
        if (items.has(spec.id)) unregisterItem(spec.id);
        // spec 本身就是实例对象:registry.instantiate 为每个节点做了
        // Object.assign({}, tpl) 拷贝,方法(spec.onData 等)与状态
        // (this.group/this.meshes)必须同体 —— 包装对象会破坏 this 链
        try {
            spec.setup.call(spec, layers[spec.layer || 1], THREE, {
                host: exports, dispatch, applyParams,
            });
        } catch (e) {
            console.error("[renderHost] 渲染项 setup 失败:", spec.id, e);
            throw e;
        }
        items.set(spec.id, spec);
        console.log("[renderHost] 渲染项已挂载:", spec.id,
                    "(layer " + (spec.layer || 1) + ")");
        return spec;
    }

    function unregisterItem(id) {
        const inst = items.get(id);
        if (!inst) return;
        try { inst.dispose && inst.dispose.call(inst); }
        catch (e) { console.warn("[renderHost] dispose 失败:", id, e); }
        items.delete(id);
    }

    // ---- 帧分发:按 kind 路由到订阅项 ----
    function dispatch(kind, frame, meta) {
        for (const inst of items.values()) {
            const subs = inst.subscribes || [];
            if (subs.includes(kind)) {
                try {
                    inst.onData.call(inst, frame, meta || {});
                } catch (e) {
                    console.error("[renderHost] 渲染项", inst.id, "onData 失败:", e);
                }
            }
        }
    }

    // ---- 节点参数下发 ----
    function applyParams(itemId, params) {
        const inst = items.get(itemId);
        if (!inst) return false;
        if (inst.onParam) {
            try { inst.onParam.call(inst, params || {}); }
            catch (e) { console.error("[renderHost] onParam 失败:", itemId, e); }
        }
        return true;
    }

    function resize() {
        const w = container.clientWidth, h = container.clientHeight;
        camera.aspect = w / h;
        camera.updateProjectionMatrix();
        renderer3d.setSize(w, h);
    }
    window.addEventListener("resize", resize);
    resize();

    function animate() {
        requestAnimationFrame(animate);
        controls.update();
        renderer3d.render(scene, camera);
    }
    animate();

    const exports = {
        scene, layers, camera, renderer3d, controls,
        registerItem, unregisterItem, dispatch, applyParams,
        items,
    };
    return exports;
})();
