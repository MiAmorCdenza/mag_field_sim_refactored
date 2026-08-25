// 粒子可视化:Three.js 视口(InstancedMesh 每颜色一组,协议 21B/粒子)。
// 坐标已由服务端完成重映射(x, z, -y)。
window.renderer = (function () {
    "use strict";
    const container = document.getElementById("viewport");
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0d1117);

    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 10000);
    camera.position.set(14, 8, 14);

    const renderer3d = new THREE.WebGLRenderer({ antialias: true });
    renderer3d.setPixelRatio(window.devicePixelRatio);
    container.appendChild(renderer3d.domElement);

    const controls = new THREE.OrbitControls(camera, renderer3d.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;

    scene.add(new THREE.AmbientLight(0x404040));
    const sun = new THREE.DirectionalLight(0xffffff, 1);
    sun.position.set(5, 3, 5);
    scene.add(sun);

    // 地球
    const earth = new THREE.Mesh(
        new THREE.SphereGeometry(1.0, 32, 32),
        new THREE.MeshPhongMaterial({ color: 0x1a5276, emissive: 0x0a1a2a }));
    scene.add(earth);

    // Re 标尺环
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
        scene.add(line);
    });

    // 坐标轴指示
    scene.add(new THREE.ArrowHelper(new THREE.Vector3(1, 0, 0), new THREE.Vector3(), 4, 0xffff00, 0.4, 0.3)); // 太阳方向 +X
    const tilt = 23.44 * Math.PI / 180;
    const rotAxis = new THREE.Vector3(Math.sin(tilt), Math.cos(tilt), 0).normalize();
    scene.add(new THREE.ArrowHelper(rotAxis, new THREE.Vector3(), 2.6, 0x00ff00, 0.3, 0.2));

    // 粒子 InstancedMesh(每颜色一组,容量 20000)
    const MAX = 20000;
    const sphereGeo = new THREE.SphereGeometry(0.07, 8, 8);
    const meshes = {};  // colorHex(string) -> THREE.InstancedMesh
    const dummy = new THREE.Object3D();

    function meshFor(color) {
        const hex = "#" + color.toString(16).padStart(6, "0");
        if (!meshes[hex]) {
            const m = new THREE.InstancedMesh(
                sphereGeo, new THREE.MeshBasicMaterial({ color: hex }), MAX);
            m.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
            dummy.scale.set(0, 0, 0);
            dummy.updateMatrix();
            for (let i = 0; i < MAX; i++) m.setMatrixAt(i, dummy.matrix);
            m.instanceMatrix.needsUpdate = true;
            m.count = 0;
            scene.add(m);
            meshes[hex] = m;
        }
        return meshes[hex];
    }

    // 解析二进制帧并更新实例
    function updateFrame(buf) {
        const view = new DataView(buf);
        const hlen = view.getUint32(0, true);
        const header = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 4, hlen)));
        const n = header.n;
        const counts = {};
        let off = 4 + hlen;
        for (let i = 0; i < n; i++) {
            const id = view.getInt32(off, true);
            const px = view.getFloat32(off + 4, true);
            const py = view.getFloat32(off + 8, true);
            const pz = view.getFloat32(off + 12, true);
            const status = view.getUint8(off + 16);
            const color = view.getUint32(off + 17, true);
            off += 21;
            if (status !== 0) continue;  // 仅渲染存活粒子
            const hex = "#" + color.toString(16).padStart(6, "0");
            counts[hex] = (counts[hex] || 0);
            const m = meshFor(color);
            if (m.count < MAX) {
                dummy.position.set(px, py, pz);
                dummy.scale.set(1, 1, 1);
                dummy.updateMatrix();
                m.setMatrixAt(m.count, dummy.matrix);
                m.count++;
                counts[hex] = m.count;
            }
        }
        // 各颜色实例数 = 本帧计数
        Object.keys(meshes).forEach(hex => {
            meshes[hex].count = Math.min(counts[hex] || 0, MAX);
            meshes[hex].instanceMatrix.needsUpdate = true;
        });
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

    return { updateFrame };
})();
