// Three.js Setup
const container = document.getElementById('canvas-container');
const scene = new THREE.Scene();

// Panel collapse/expand — uses uiPanel declared later in this file
const panelToggle = document.getElementById('panel-toggle');
function togglePanel() {
    if (!uiPanel) return;
    const collapsed = uiPanel.classList.toggle('collapsed');
    panelToggle.classList.toggle('collapsed', collapsed);
    panelToggle.innerHTML = collapsed ? '▶' : '◀';
    panelToggle.title = collapsed ? '展开面板' : '收起面板';
}
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') togglePanel();
});

const camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.1, 10000);
camera.position.set(10, 5, 10);

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(window.innerWidth, window.innerHeight);
container.appendChild(renderer.domElement);

const controls = new THREE.OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.05;

// Add Lighting
const ambientLight = new THREE.AmbientLight(0x404040); // Soft white light
scene.add(ambientLight);
const dirLight = new THREE.DirectionalLight(0xffffff, 1);
dirLight.position.set(5, 3, 5);
scene.add(dirLight);

// Add Earth
// In our simulation, Earth Radius (Re) = 1.0
const earthGeometry = new THREE.SphereGeometry(1.0, 32, 32);
const earthMaterial = new THREE.MeshPhongMaterial({ 
    color: 0x1a5276, 
    emissive: 0x0a1a2a,
    wireframe: false 
});
const earth = new THREE.Mesh(earthGeometry, earthMaterial);
scene.add(earth);

// Add Axes Helper (removed original, replaced with custom arrows)
const origin = new THREE.Vector3(0, 0, 0);

// Rotation Axis (Tilted 23.44 deg from Ecliptic North)
// Ecliptic North in Three.js is +Y.
// We tilt it towards +X (Sun) during summer solstice for visualization.
const tiltRot = 23.44 * Math.PI / 180;
const rotAxis = new THREE.Vector3(Math.sin(tiltRot), Math.cos(tiltRot), 0).normalize();
const rotArrow = new THREE.ArrowHelper(rotAxis, origin, 2.5, 0x00ff00, 0.3, 0.2);
scene.add(rotArrow);

// Earth Rotation Direction Arrow (CCW around rotAxis)
const earthRotGroup = new THREE.Group();
const rotArc = Math.PI * 1.5;
const rotR = 1.2;
const torusGeo = new THREE.TorusGeometry(rotR, 0.015, 8, 32, rotArc);
const torusMat = new THREE.MeshBasicMaterial({ color: 0x00ff00 });
const torus = new THREE.Mesh(torusGeo, torusMat);
earthRotGroup.add(torus);

const coneGeo = new THREE.ConeGeometry(0.06, 0.2, 8);
const cone = new THREE.Mesh(coneGeo, torusMat);
cone.position.set(rotR * Math.cos(rotArc), rotR * Math.sin(rotArc), 0);
cone.rotation.z = rotArc;
earthRotGroup.add(cone);
scene.add(earthRotGroup);

// Magnetic Axis (Tilted 11 deg from Rotation Axis)
let currentSeasonalTilt = tiltRot;
let currentTotalTilt = tiltRot + 11.0 * Math.PI / 180;
const magAxis = new THREE.Vector3(Math.sin(currentTotalTilt), Math.cos(currentTotalTilt), 0).normalize();
const magArrow = new THREE.ArrowHelper(magAxis, origin, 2.8, 0xff00ff, 0.3, 0.2);
scene.add(magArrow);

// Sun Direction (Solar Wind from +X)
const sunAxis = new THREE.Vector3(1, 0, 0);
const sunArrow = new THREE.ArrowHelper(sunAxis, origin, 4.0, 0xffff00, 0.4, 0.3);
scene.add(sunArrow);

// Earth Orbit (Moves along Python Y, which is Three.js -Z)
// Since Sun is +X, Earth moves locally along Z axis in our Three.js view.
const orbitGeo = new THREE.BufferGeometry();
orbitGeo.setFromPoints([
    new THREE.Vector3(0, 0, -1000),
    new THREE.Vector3(0, 0, 1000)
]);
const orbitMat = new THREE.LineDashedMaterial({color: 0xaaaaaa, dashSize: 1, gapSize: 1});
const orbitLine = new THREE.Line(orbitGeo, orbitMat);
orbitLine.computeLineDistances();
scene.add(orbitLine);

// Re (Earth Radius) Scale Rings
const scaleGroup = new THREE.Group();
const scaleRadii = [2, 3, 4, 5, 6, 7, 8, 9, 10, 15, 20, 30, 40, 50, 60, 70, 80, 90];
const scaleLabels = [];

scaleRadii.forEach(r => {
    const pts = [];
    for(let i = 0; i <= 64; i++){
        const theta = (i / 64) * Math.PI * 2;
        pts.push(new THREE.Vector3(r * Math.cos(theta), 0, r * Math.sin(theta)));
    }
    const ringGeo = new THREE.BufferGeometry().setFromPoints(pts);
    const isMajor = (r % 5 === 0);
    const ringMat = new THREE.LineDashedMaterial({ 
        color: isMajor ? 0x888888 : 0x555555, 
        dashSize: isMajor ? 0.4 : 0.2, 
        gapSize: isMajor ? 0.4 : 0.2, 
        transparent: true, 
        opacity: isMajor ? 0.6 : 0.3 
    });
    const ring = new THREE.Line(ringGeo, ringMat);
    ring.computeLineDistances();
    scaleGroup.add(ring);
});
scene.add(scaleGroup);

// HTML Labels
function createLabel(text, color) {
    const div = document.createElement('div');
    div.className = 'label';
    div.style.color = color;
    div.innerText = text;
    document.body.appendChild(div);
    return div;
}
const labelRot = createLabel('地轴 (N)', '#00ff00');
const labelMag = createLabel('磁极', '#ff00ff');
const labelSun = createLabel('太阳方向', '#ffff00');
const labelOrbit = createLabel('地球轨道', '#aaaaaa');
const labelRotDir = createLabel('自转方向', '#00ff00');

scaleRadii.forEach(r => {
    const isMajor = (r % 5 === 0);
    const color = isMajor ? '#aaaaaa' : '#666666';
    scaleLabels.push({ div: createLabel(`${r} Re`, color), r: r });
});

function updateLabels() {
    const updatePos = (div, pos3d) => {
        const vector = pos3d.clone();
        vector.project(camera);
        if (vector.z < 1) {
            const x = (vector.x * 0.5 + 0.5) * window.innerWidth;
            const y = (vector.y * -0.5 + 0.5) * window.innerHeight;
            div.style.left = x + 'px';
            div.style.top = y + 'px';
            div.style.display = 'block';
        } else {
            div.style.display = 'none';
        }
    };
    updatePos(labelRot, new THREE.Vector3(Math.sin(currentSeasonalTilt)*2.7, Math.cos(currentSeasonalTilt)*2.7, 0));
    updatePos(labelMag, new THREE.Vector3(Math.sin(currentTotalTilt)*3.0, Math.cos(currentTotalTilt)*3.0, 0));
    updatePos(labelSun, new THREE.Vector3(4.2, 0, 0));
    updatePos(labelOrbit, new THREE.Vector3(0, 0, 10));
    
    // Label for rotation direction (placed near the arrowhead)
    const rotDirPos = new THREE.Vector3(rotR * Math.cos(rotArc + 0.3), rotR * Math.sin(rotArc + 0.3), 0);
    rotDirPos.applyQuaternion(earthRotGroup.quaternion);
    updatePos(labelRotDir, rotDirPos);

    scaleLabels.forEach(item => {
        // Place label at 45 degrees angle on the XZ plane, stagger slightly to prevent overlap
        const angle = Math.PI / 4 + (item.r % 2 === 0 ? 0.08 : -0.08);
        updatePos(item.div, new THREE.Vector3(item.r * Math.cos(angle), 0, item.r * Math.sin(angle)));
    });
}

// Arrow Updates
function updateArrows(seasonalTilt, totalTilt) {
    rotAxis.set(Math.sin(seasonalTilt), Math.cos(seasonalTilt), 0).normalize();
    rotArrow.setDirection(rotAxis);
    earthRotGroup.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), rotAxis);

    magAxis.set(Math.sin(totalTilt), Math.cos(totalTilt), 0).normalize();
    magArrow.setDirection(magAxis);
}

const fieldLinesGroup = new THREE.Group();
scene.add(fieldLinesGroup);

const efieldLinesGroup = new THREE.Group();
scene.add(efieldLinesGroup);

// Sub-groups for the actual line geometries (so we can clear them without removing arrows)
const fieldLinesSubGroup = new THREE.Group();
const efieldLinesSubGroup = new THREE.Group();
fieldLinesGroup.add(fieldLinesSubGroup);
efieldLinesGroup.add(efieldLinesSubGroup);

// --- Arrow meshes for field direction ---
const MAX_B_ARROWS = 15000;
const MAX_E_ARROWS = 10000;
const arrowConeGeo = new THREE.ConeGeometry(0.35, 1.2, 4, 3);
arrowConeGeo.translate(0, 0.6, 0); // move pivot to base
const bArrowMaterial = new THREE.MeshBasicMaterial({ color: 0x88aaff, transparent: true, opacity: 0.85 });
const eArrowMaterial = new THREE.MeshBasicMaterial({ color: 0x00ffcc, transparent: true, opacity: 0.9 });
const bArrowMesh = new THREE.InstancedMesh(arrowConeGeo, bArrowMaterial, MAX_B_ARROWS);
const eArrowMesh = new THREE.InstancedMesh(arrowConeGeo, eArrowMaterial, MAX_E_ARROWS);
fieldLinesGroup.add(bArrowMesh);
efieldLinesGroup.add(eArrowMesh);
bArrowMesh.count = 0;
eArrowMesh.count = 0;

const _dummyObj = new THREE.Object3D();
const _upVec = new THREE.Vector3(0, 1, 0);
const _quat = new THREE.Quaternion();

function populateArrows(mesh, lines, spacing) {
    let idx = 0;
    const max = mesh.instanceMatrix.count; // capacity
    for (const linePts of lines) {
        if (idx >= max) break;
        if (linePts.length < 2) continue;
        let accum = 0;
        for (let i = 0; i < linePts.length - 1; i++) {
            const p = linePts[i];
            const pn = linePts[i + 1];
            const dx = pn[0] - p[0], dy = pn[1] - p[1], dz = pn[2] - p[2];
            const segLen = Math.sqrt(dx*dx + dy*dy + dz*dz);
            accum += segLen;
            if (accum >= spacing) {
                accum = 0;
                const dir = new THREE.Vector3(dx, dy, dz).normalize();
                if (dir.length() < 0.001) continue;
                // Remap from physics coords to Three.js: [x,y,z] → [x,z,-y]
                _dummyObj.position.set(p[0], p[2], -p[1]);
                _quat.setFromUnitVectors(_upVec, new THREE.Vector3(dir.x, dir.z, -dir.y));
                _dummyObj.setRotationFromQuaternion(_quat);
                _dummyObj.updateMatrix();
                mesh.setMatrixAt(idx, _dummyObj.matrix);
                idx++;
                if (idx >= max) break;
            }
        }
        if (idx >= max) break;
    }
    mesh.count = idx;
    mesh.instanceMatrix.needsUpdate = true;
}

// Particles Management
const particlesData = {}; // Store meshes and trails
let maxTrailLength = 50;
const collidedTrailsGroup = new THREE.Group();
const activeParticlesGroup = new THREE.Group();
scene.add(collidedTrailsGroup);
scene.add(activeParticlesGroup);

// Memory Optimization for 20000 particles: InstancedMesh
const sharedParticleGeo = new THREE.SphereGeometry(0.08, 8, 8); // Reduced segments for performance
const maxParticlesPerColor = 20000;
const instancedMeshes = {}; // Keyed by colorHex
const trailMeshes = {}; // Keyed by colorHex

function getInstancedMesh(colorHex) {
    if (!instancedMeshes[colorHex]) {
        const mat = new THREE.MeshBasicMaterial({ color: colorHex });
        const iMesh = new THREE.InstancedMesh(sharedParticleGeo, mat, maxParticlesPerColor);
        iMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
        // Hide all instances initially by placing them far away or scaling to 0
        const dummy = new THREE.Object3D();
        dummy.scale.set(0, 0, 0);
        dummy.updateMatrix();
        for (let i = 0; i < maxParticlesPerColor; i++) {
            iMesh.setMatrixAt(i, dummy.matrix);
        }
        iMesh.instanceMatrix.needsUpdate = true;
        iMesh.count = 0; // Number of currently active instances of this color
        activeParticlesGroup.add(iMesh);
        instancedMeshes[colorHex] = iMesh;
    }
    return instancedMeshes[colorHex];
}

function getTrailMesh(colorHex) {
    if (!trailMeshes[colorHex]) {
        const mat = new THREE.LineBasicMaterial({ color: colorHex, transparent: true, opacity: 0.6 });
        const geom = new THREE.BufferGeometry();
        
        const safeLen = Math.max(2, maxTrailLength);
        
        // P * L vertices
        const positions = new Float32Array(maxParticlesPerColor * safeLen * 3);
        geom.setAttribute('position', new THREE.BufferAttribute(positions, 3));
        geom.attributes.position.setUsage(THREE.DynamicDrawUsage);
        
        // Index buffer
        const indices = new Uint32Array(maxParticlesPerColor * (safeLen - 1) * 2);
        let idx = 0;
        for (let p = 0; p < maxParticlesPerColor; p++) {
            const offset = p * safeLen;
            for (let i = 0; i < safeLen - 1; i++) {
                indices[idx++] = offset + i;
                indices[idx++] = offset + i + 1;
            }
        }
        geom.setIndex(new THREE.BufferAttribute(indices, 1));
        
        const mesh = new THREE.LineSegments(geom, mat);
        mesh.frustumCulled = false; // Important because vertices are dynamic
        activeParticlesGroup.add(mesh);
        
        trailMeshes[colorHex] = {
            mesh: mesh,
            positions: positions,
            count: 0
        };
    }
    return trailMeshes[colorHex];
}

// UI Elements
const kpVal = document.getElementById('kp-val');
const kpSlider = document.getElementById('kp-slider');
const compVal = document.getElementById('comp-val');
const compSlider = document.getElementById('comp-slider');
const autoFetchCb = document.getElementById('auto-fetch-cb');
const parkerCustomCb = document.getElementById('parker-custom-cb');
const parkerAngleSlider = document.getElementById('parker-angle-slider');
const parkerAngleVal = document.getElementById('parker-angle-val');

parkerCustomCb.addEventListener('change', () => {
    const enabled = parkerCustomCb.checked;
    parkerAngleSlider.disabled = !enabled;
    parkerAngleVal.style.color = enabled ? 'var(--accent2)' : 'var(--text-dim)';
    sendParkerAngle();
});

parkerAngleSlider.addEventListener('input', () => {
    parkerAngleVal.innerText = parkerAngleSlider.value;
    sendParkerAngle();
});

function sendParkerAngle() {
    if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
            type: 'set_parker_angle',
            enabled: parkerCustomCb.checked,
            angle_deg: parseFloat(parkerAngleSlider.value)
        }));
    }
}

function applyParkerUi(enabled, angleDeg) {
    parkerCustomCb.checked = !!enabled;
    parkerAngleSlider.value = angleDeg;
    parkerAngleSlider.disabled = !enabled;
    parkerAngleVal.innerText = angleDeg;
    parkerAngleVal.style.color = enabled ? 'var(--accent2)' : 'var(--text-dim)';
}
const ptcVal = document.getElementById('ptc-val');
const rangeSlider = document.getElementById('range-slider');
const rangeVal = document.getElementById('range-val');
const renderRadiusSlider = document.getElementById('render-radius-slider');
const renderRadiusVal = document.getElementById('render-radius-val');
const ptcSlider = document.getElementById('ptc-slider');
const spawnRatioSlider = document.getElementById('spawn-ratio-slider');
const spawnRatioVal = document.getElementById('spawn-ratio-val');
const daySlider = document.getElementById('day-slider');
const dayVal = document.getElementById('day-val');
const modelPrecSlider = document.getElementById('model-prec-slider');
const modelPrecVal = document.getElementById('model-prec-val');
const fieldPrecSlider = document.getElementById('field-prec-slider');
const fieldPrecVal = document.getElementById('field-prec-val');
const magModel = document.getElementById('mag-model');
const bMultSlider = document.getElementById('b-mult-slider');
const bMultVal = document.getElementById('b-mult-val');
const renderMagCb = document.getElementById('render-mag-cb');
const renderColCb = document.getElementById('render-col-cb');
const hidePtcCb = document.getElementById('hide-ptc-cb');
const hideTrailCb = document.getElementById('hide-trail-cb');
const respawnAllBtn = document.getElementById('respawn-all-btn');

const enableGravityCb = document.getElementById('enable-gravity-cb');
const gravMultSlider = document.getElementById('grav-mult-slider');
const gravMultVal = document.getElementById('grav-mult-val');

const enableEfieldCb = document.getElementById('enable-efield-cb');
const efieldModel = document.getElementById('efield-model');
const efieldMultSlider = document.getElementById('efield-mult-slider');
const efieldMultVal = document.getElementById('efield-mult-val');

const enableAtmosCb = document.getElementById('enable-atmos-cb');
const atmosModel = document.getElementById('atmos-model');
const atmosMultSlider = document.getElementById('atmos-mult-slider');
const atmosMultVal = document.getElementById('atmos-mult-val');

const enableTailCb = document.getElementById('enable-tail-cb');
const tailModel = document.getElementById('tail-model');

const enableMpCb = document.getElementById('enable-mp-cb');
const mpModel = document.getElementById('mp-model');

const emitterMode = document.getElementById('emitter-mode');
const directionalControls = document.getElementById('directional-controls');
const lonSlider = document.getElementById('lon-slider');
const lonVal = document.getElementById('lon-val');
const latSlider = document.getElementById('lat-slider');
const latVal = document.getElementById('lat-val');
const spawnRatioContainer = document.getElementById('spawn-ratio-container');
const spawnDistSlider = document.getElementById('spawn-dist-slider');
const spawnDistVal = document.getElementById('spawn-dist-val');
const spawnDistContainer = document.getElementById('spawn-dist-container');

const vbaseSlider = document.getElementById('vbase-slider');
const vbaseVal = document.getElementById('vbase-val');
const vrandSlider = document.getElementById('vrand-slider');
const vrandVal = document.getElementById('vrand-val');
const angrandSlider = document.getElementById('angrand-slider');
const angrandVal = document.getElementById('angrand-val');

const particleTypesContainer = document.getElementById('particle-types-container');
const addPtypeBtn = document.getElementById('add-ptype-btn');

const trailLenSlider = document.getElementById('trail-len-slider');
const trailLenVal = document.getElementById('trail-len-val');

const uiPanel = document.getElementById('ui-panel');

// Prevent OrbitControls from stealing UI events
['mousedown', 'touchstart', 'wheel', 'pointerdown'].forEach(evt => {
    uiPanel.addEventListener(evt, e => e.stopPropagation());
});

// WebSocket Connection
const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

rangeSlider.addEventListener('input', (e) => {
    const val = e.target.value;
    rangeVal.innerText = val;
    if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'set_max_range', value: parseFloat(val) }));
    }
});

let updateTimeout = null;
kpSlider.addEventListener('input', (e) => {
    const val = parseFloat(e.target.value);
    kpVal.innerText = val.toFixed(1);
    const comp = 1.0 + val / 9.0;
    compVal.innerText = comp.toFixed(3);
    compSlider.value = comp;
    if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'set_kp', value: val }));
    }
});

compSlider.addEventListener('input', (e) => {
    const val = parseFloat(e.target.value);
    compVal.innerText = val.toFixed(3);
    const kp = (val - 1.0) * 9.0;
    kpVal.innerText = Math.max(0, Math.min(9, kp)).toFixed(1);
    kpSlider.value = Math.max(0, Math.min(9, kp));
    if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'set_compression', value: val }));
    }
});

autoFetchCb.addEventListener('change', (e) => {
    const checked = e.target.checked;
    kpSlider.disabled = checked;
    compSlider.disabled = checked;
    if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'set_auto_fetch_solar', value: checked }));
    }
});

let renderRadiusRatio = 1.0;
renderRadiusSlider.addEventListener('input', (e) => {
    renderRadiusVal.innerText = e.target.value;
    renderRadiusRatio = parseFloat(e.target.value) / 100.0;
    if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'set_render_radius_ratio', value: renderRadiusRatio }));
    }
});

ptcSlider.addEventListener('input', (e) => {
    ptcVal.innerText = e.target.value;
});

ptcSlider.addEventListener('change', (e) => {
    const val = parseInt(e.target.value);
    ptcVal.innerText = val;
    if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'set_particle_count', value: val }));
    }
});

daySlider.addEventListener('input', (e) => {
    dayVal.innerText = e.target.value;
    if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'set_day', value: parseFloat(e.target.value) }));
});

spawnRatioSlider.addEventListener('input', (e) => {
    spawnRatioVal.innerText = e.target.value;
    if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'set_spawn_radius_ratio', value: parseFloat(e.target.value) }));
});

const precLabels = ['低', '中', '高', '极高'];
modelPrecSlider.addEventListener('input', (e) => {
    modelPrecVal.innerText = precLabels[e.target.value];
    if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'set_model_prec', value: parseInt(e.target.value) }));
});

fieldPrecSlider.addEventListener('input', (e) => {
    fieldPrecVal.innerText = precLabels[e.target.value];
    if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'set_field_prec', value: parseInt(e.target.value) }));
});

magModel.addEventListener('change', (e) => {
    if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'set_mag_model', value: parseInt(e.target.value) }));
});

bMultSlider.addEventListener('input', (e) => {
    bMultVal.innerText = e.target.value;
    if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'set_b_multiplier', value: parseFloat(e.target.value) }));
});

let renderMagneticField = true;
renderMagCb.addEventListener('change', (e) => {
    renderMagneticField = e.target.checked;
    fieldLinesGroup.visible = renderMagneticField;
});

let renderEField = true;
const renderEFieldCb = document.getElementById('render-efield-cb');
renderEFieldCb.addEventListener('change', (e) => {
    renderEField = e.target.checked;
    efieldLinesGroup.visible = renderEField;
});

let renderCollided = true;
renderColCb.addEventListener('change', (e) => {
    renderCollided = e.target.checked;
    collidedTrailsGroup.visible = renderCollided;
});

let hideParticles = false;
hidePtcCb.addEventListener('change', (e) => {
    hideParticles = e.target.checked;
    Object.values(instancedMeshes).forEach(iMesh => {
        iMesh.visible = !hideParticles;
    });
});

let hideTrails = false;
hideTrailCb.addEventListener('change', (e) => {
    hideTrails = e.target.checked;
    Object.values(trailMeshes).forEach(tMesh => {
        tMesh.mesh.visible = !hideTrails;
    });
});

respawnAllBtn.addEventListener('click', () => {
    if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'respawn_all' }));
    }
});

enableGravityCb.addEventListener('change', (e) => {
    if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'set_enable_gravity', value: e.target.checked }));
    }
});

gravMultSlider.addEventListener('input', (e) => {
    gravMultVal.innerText = e.target.value;
    if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'set_gravity_multiplier', value: parseFloat(e.target.value) }));
    }
});

enableEfieldCb.addEventListener('change', (e) => {
    if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'set_enable_electric_field', value: e.target.checked }));
    }
});

efieldModel.addEventListener('change', (e) => {
    if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'set_efield_model', value: parseInt(e.target.value) }));
    }
});

efieldMultSlider.addEventListener('input', (e) => {
    efieldMultVal.innerText = e.target.value;
    if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'set_electric_field_multiplier', value: parseFloat(e.target.value) }));
    }
});

enableAtmosCb.addEventListener('change', (e) => {
    if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'set_enable_atmosphere', value: e.target.checked }));
    }
});

atmosModel.addEventListener('change', (e) => {
    if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'set_atmos_model', value: parseInt(e.target.value) }));
    }
});

atmosMultSlider.addEventListener('input', (e) => {
    atmosMultVal.innerText = e.target.value;
    if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'set_atmosphere_multiplier', value: parseFloat(e.target.value) }));
    }
});

enableTailCb.addEventListener('change', (e) => {
    const val = e.target.checked ? parseInt(tailModel.value) : 0;
    tailModel.disabled = !e.target.checked;
    if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'set_tail_model', value: val }));
    }
});

tailModel.addEventListener('change', (e) => {
    if (enableTailCb.checked && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'set_tail_model', value: parseInt(e.target.value) }));
    }
});

enableMpCb.addEventListener('change', (e) => {
    const val = e.target.checked ? parseInt(mpModel.value) : 0;
    mpModel.disabled = !e.target.checked;
    if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'set_magnetopause_model', value: val }));
    }
});

mpModel.addEventListener('change', (e) => {
    if (enableMpCb.checked && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'set_magnetopause_model', value: parseInt(e.target.value) }));
    }
});

function sendEmitterParams() {
    if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
            type: 'set_emitter_params',
            mode: parseInt(emitterMode.value),
            lon: parseFloat(lonSlider.value),
            lat: parseFloat(latSlider.value),
            v_base: parseFloat(vbaseSlider.value),
            v_random: parseFloat(vrandSlider.value),
            angle_random: parseFloat(angrandSlider.value),
            dist_ratio: parseFloat(spawnDistSlider.value)
        }));
    }
}

emitterMode.addEventListener('change', (e) => {
    const mode = e.target.value;
    const isOmni = mode === "1";
    directionalControls.style.display = isOmni ? 'none' : 'block';
    spawnRatioContainer.style.display = isOmni ? 'none' : 'block';
    sendEmitterParams();
});

spawnDistSlider.addEventListener('input', (e) => {
    spawnDistVal.innerText = e.target.value;
    sendEmitterParams();
});

lonSlider.addEventListener('input', (e) => {
    lonVal.innerText = e.target.value;
    sendEmitterParams();
});

latSlider.addEventListener('input', (e) => {
    latVal.innerText = e.target.value;
    sendEmitterParams();
});

vbaseSlider.addEventListener('input', (e) => {
    vbaseVal.innerText = e.target.value;
    sendEmitterParams();
});

vrandSlider.addEventListener('input', (e) => {
    vrandVal.innerText = e.target.value;
    sendEmitterParams();
});

angrandSlider.addEventListener('input', (e) => {
    angrandVal.innerText = e.target.value;
    sendEmitterParams();
});

function hexToInt(hexStr) {
    return parseInt(hexStr.replace(/^#/, ''), 16);
}

let pTypes = [
    {id: 1, name: "正电荷", q: 1, m: 0.1, v: 1.0, weight: 1.0, color: "#ff3333", checked: true},
    {id: 2, name: "负电荷", q: -1, m: 0.1, v: 1.0, weight: 1.0, color: "#3333ff", checked: true},
    {id: 3, name: "质子 (H+)", q: 1, m: 1, v: 1.0, weight: 1.0, color: "#ff8800", checked: false},
    {id: 4, name: "电子 (e-)", q: -1, m: 0.00054, v: 1.0, weight: 1.0, color: "#00ffff", checked: false},
    {id: 5, name: "α粒子 (He2+)", q: 2, m: 4, v: 1.0, weight: 1.0, color: "#ff00ff", checked: false}
];
let nextPtypeId = 6;

function renderPTypes() {
    particleTypesContainer.innerHTML = '';
    pTypes.forEach(pt => {
        const div = document.createElement('div');
        div.className = 'ptype-row';
        div.innerHTML = `
            <input type="checkbox" ${pt.checked ? 'checked' : ''} onchange="updatePType(${pt.id}, 'checked', this.checked)" title="启用/禁用">
            <span style="width:10px;height:10px;border-radius:50%;background:${pt.color};flex-shrink:0;box-shadow:0 0 4px ${pt.color};"></span>
            <input type="text" value="${pt.name}" class="pt-name" onchange="updatePType(${pt.id}, 'name', this.value)">
            q:<input type="number" value="${pt.q}" class="pt-num" step="1" onchange="updatePType(${pt.id}, 'q', this.value)">
            m:<input type="number" value="${pt.m}" class="pt-num" step="0.001" onchange="updatePType(${pt.id}, 'm', this.value)">
            v:<input type="number" value="${pt.v}" class="pt-num" step="0.1" onchange="updatePType(${pt.id}, 'v', this.value)">
            w:<input type="number" value="${pt.weight || 1.0}" class="pt-num" step="0.1" min="0" onchange="updatePType(${pt.id}, 'weight', this.value)" title="生成比例权重">
            <input type="color" value="${pt.color}" style="width:20px;height:20px;padding:0;border:1px solid #ccc;border-radius:3px;cursor:pointer;flex-shrink:0;" onchange="updatePType(${pt.id}, 'color', this.value)">
            <button onclick="deletePType(${pt.id})" class="pt-del" title="删除">✕</button>
        `;
        particleTypesContainer.appendChild(div);
    });
    sendParticleTypes();
}

window.updatePType = function(id, field, value) {
    const pt = pTypes.find(p => p.id === id);
    if(pt) {
        if(field === 'checked') pt.checked = value;
        else if(field === 'name') pt.name = value;
        else if(field === 'color') pt.color = value;
        else pt[field] = parseFloat(value);
        if (field !== 'name') sendParticleTypes();
    }
};

window.deletePType = function(id) {
    pTypes = pTypes.filter(p => p.id !== id);
    renderPTypes();
};

addPtypeBtn.addEventListener('click', () => {
    pTypes.push({ id: nextPtypeId++, name: "新粒子", q: 1, m: 1, v: 1.0, color: "#ffffff", checked: true });
    renderPTypes();
});

let isSyncing = false;

function sendParticleTypes() {
    if (isSyncing) return;
    const types = pTypes.filter(p => p.checked).map(p => ({
        q: p.q, 
        mass: p.m, 
        v_multiplier: p.v, 
        weight: p.weight || 1.0,
        color: hexToInt(p.color)
    }));

    if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
            type: 'set_particle_types',
            types: types,
            raw_types: pTypes
        }));
    }
}

// Initial render
renderPTypes();

trailLenSlider.addEventListener('input', (e) => {
    trailLenVal.innerText = e.target.value;
    const newLen = parseInt(e.target.value);
    if (newLen !== maxTrailLength) {
        maxTrailLength = newLen;
        // Trails will be re-created automatically if we delete existing ones
        // Force re-creation by clearing particlesData
        Object.keys(particlesData).forEach(id => {
            delete particlesData[id];
        });
        
        Object.keys(trailMeshes).forEach(hex => {
            const tMesh = trailMeshes[hex];
            activeParticlesGroup.remove(tMesh.mesh);
            tMesh.mesh.geometry.dispose();
            tMesh.mesh.material.dispose();
            delete trailMeshes[hex];
        });
    }
});

const dummy = new THREE.Object3D();

ws.binaryType = 'arraybuffer';
let activeGridSeq = 0;
let activeGridAnim = null;
let gridHideTimer = null;

ws.onmessage = function(event) {
    if (event.data instanceof ArrayBuffer) {
        console.log('[WS] Binary message received, size:', event.data.byteLength);
        handleBinaryState(event.data);
    } else if (event.data instanceof Blob) {
        console.warn('[WS] Blob received (binaryType not set?), size:', event.data.size);
    } else {
        const preview = typeof event.data === 'string' ? event.data.substring(0, 100) : typeof event.data;
        console.log('[WS] Text message received:', preview);
        handleTextMessage(event.data);
    }
};

function handleTextMessage(textData) {
    const data = JSON.parse(textData);
    
    if (data.type === "grid_progress") {
        const progressEl = document.getElementById('grid-progress');
        const progressBar = document.getElementById('grid-progress-bar');
        const progressText = document.getElementById('grid-progress-text');
        const seq = Number(data.seq ?? 0);
        if (data.state === "queued") {
            if (seq >= activeGridSeq) {
                activeGridSeq = seq;
                if (gridHideTimer) clearTimeout(gridHideTimer);
                progressEl.style.display = 'block';
                progressBar.style.width = '5%';
                progressText.textContent = '⏳ 参数已更新，等待生成最新磁场网格...';
            }
        } else if (data.state === "computing") {
            if (seq < activeGridSeq) return;
            activeGridSeq = seq;
            if (gridHideTimer) clearTimeout(gridHideTimer);
            if (activeGridAnim) clearInterval(activeGridAnim);
            progressEl.style.display = 'block';
            progressBar.style.width = '0%';
            progressText.textContent = '⏳ 正在计算磁场网格...';
            let w = 0;
            const anim = setInterval(() => {
                w += Math.random() * 15;
                if (w > 90) w = 90;
                progressBar.style.width = w + '%';
            }, 300);
            activeGridAnim = anim;
        } else if (data.state === "done") {
            if (seq !== activeGridSeq) return;
            if (activeGridAnim) clearInterval(activeGridAnim);
            activeGridAnim = null;
            progressBar.style.width = '100%';
            progressText.textContent = '✅ 网格计算完成';
            gridHideTimer = setTimeout(() => { progressEl.style.display = 'none'; }, 800);
        } else if (data.state === "superseded") {
            if (seq !== activeGridSeq) return;
            progressText.textContent = '⏳ 已切换到更新的参数包，忽略旧结果...';
        } else if (data.state === "error") {
            if (seq !== activeGridSeq) return;
            if (activeGridAnim) clearInterval(activeGridAnim);
            activeGridAnim = null;
            progressBar.style.width = '100%';
            progressText.textContent = `❌ 网格生成失败: ${data.note ?? '未知错误'}`;
            gridHideTimer = setTimeout(() => { progressEl.style.display = 'none'; }, 1800);
        }
        return;
    }

    if (data.type === "init_config") {
        const config = data.config;

        if (config.kp !== undefined) {
            kpSlider.value = config.kp;
            kpVal.innerText = Number(config.kp).toFixed(1);
        }
        if (config.solar_wind_compression !== undefined) {
            compSlider.value = config.solar_wind_compression;
            compVal.innerText = Number(config.solar_wind_compression).toFixed(3);
        }
        if (config.auto_fetch_solar !== undefined) {
            autoFetchCb.checked = config.auto_fetch_solar;
            kpSlider.disabled = config.auto_fetch_solar;
            compSlider.disabled = config.auto_fetch_solar;
        }
        if (config.parker_custom !== undefined || config.parker_angle !== undefined) {
            applyParkerUi(
                config.parker_custom ?? false,
                Number(config.parker_angle ?? parkerAngleSlider.value)
            );
        }

        rangeSlider.value = config.max_range;
        rangeVal.innerText = config.max_range;
        
        if (config.render_radius_ratio !== undefined) {
            renderRadiusRatio = config.render_radius_ratio;
            renderRadiusSlider.value = Math.round(renderRadiusRatio * 100);
            renderRadiusVal.innerText = Math.round(renderRadiusRatio * 100);
        }
        
        ptcSlider.value = config.particle_count;
        ptcVal.innerText = config.particle_count;
        
        daySlider.value = config.day;
        dayVal.innerText = config.day;
        
        modelPrecSlider.value = config.model_prec;
        modelPrecVal.innerText = precLabels[config.model_prec];
        
        fieldPrecSlider.value = config.field_prec;
        fieldPrecVal.innerText = precLabels[config.field_prec];
        
        magModel.value = config.mag_model;
        
        bMultSlider.value = config.b_multiplier;
        bMultVal.innerText = config.b_multiplier;
        
        spawnRatioSlider.value = config.spawn_radius_ratio;
        spawnRatioVal.innerText = config.spawn_radius_ratio;
        
        enableGravityCb.checked = config.enable_gravity;
        gravMultSlider.value = config.gravity_multiplier;
        gravMultVal.innerText = config.gravity_multiplier;
        
        enableEfieldCb.checked = config.enable_electric_field;
        efieldModel.value = config.efield_model;
        efieldMultSlider.value = config.electric_field_multiplier;
        efieldMultVal.innerText = config.electric_field_multiplier;
        
        enableAtmosCb.checked = config.enable_atmosphere;
        atmosModel.value = config.atmos_model;
        atmosMultSlider.value = config.atmosphere_multiplier;
        atmosMultVal.innerText = config.atmosphere_multiplier;
        
        if (config.tail_model !== undefined) {
            const tm = config.tail_model;
            if (tm === 0) {
                enableTailCb.checked = false;
                tailModel.disabled = true;
            } else {
                enableTailCb.checked = true;
                tailModel.disabled = false;
                tailModel.value = tm;
            }
        }
        
        if (config.magnetopause_model !== undefined) {
            const mp = config.magnetopause_model;
            if (mp === 0) {
                enableMpCb.checked = false;
                mpModel.disabled = true;
            } else {
                enableMpCb.checked = true;
                mpModel.disabled = false;
                mpModel.value = mp;
            }
        }
        
        emitterMode.value = config.emitter_mode;
        lonSlider.value = config.emitter_lon;
        lonVal.innerText = config.emitter_lon;
        latSlider.value = config.emitter_lat;
        latVal.innerText = config.emitter_lat;
        vbaseSlider.value = config.v_base;
        vbaseVal.innerText = config.v_base;
        vrandSlider.value = config.v_random;
        vrandVal.innerText = config.v_random;
        angrandSlider.value = config.angle_random;
        angrandVal.innerText = config.angle_random;
        spawnDistSlider.value = config.dist_ratio;
        spawnDistVal.innerText = config.dist_ratio;
        
        const isOmni = config.emitter_mode === 1;
        directionalControls.style.display = isOmni ? 'none' : 'block';
        spawnRatioContainer.style.display = isOmni ? 'none' : 'block';
        
        if (config.particle_types) {
            pTypes = config.particle_types;
            nextPtypeId = Math.max(...pTypes.map(p => p.id), 0) + 1;
            isSyncing = true;
            renderPTypes();
            isSyncing = false;
        }
        
        return;
    }
}

function handleBinaryState(buffer) {
    try {
    const view = new DataView(buffer);
    const headerLen = view.getUint32(0, true);
    console.log('[Binary] headerLen:', headerLen, 'totalSize:', buffer.byteLength);
    const headerBytes = new Uint8Array(buffer, 4, headerLen);
    const header = JSON.parse(new TextDecoder().decode(headerBytes));
    console.log('[Binary] header keys:', Object.keys(header).join(', '), 'n:', header.n);
    
    if (autoFetchCb.checked) {
        kpVal.innerText = header.k.toFixed(2);
        compVal.innerText = header.c.toFixed(3);
        kpSlider.value = header.k;
        compSlider.value = header.c;
    }
    ptcVal.innerText = header.n;

    currentSeasonalTilt = header.st;
    currentTotalTilt = header.tt;
    updateArrows(currentSeasonalTilt, currentTotalTilt);
    
    if (header.fl) {
        while(fieldLinesSubGroup.children.length > 0){ 
            const child = fieldLinesSubGroup.children[0];
            fieldLinesSubGroup.remove(child); 
            child.geometry.dispose();
            child.material.dispose();
        }
        const material = new THREE.LineBasicMaterial({ color: 0x88aaff, transparent: true, opacity: 0.8 });
        header.fl.forEach(linePoints => {
            const points = linePoints.map(p => new THREE.Vector3(p[0], p[2], -p[1]));
            const geometry = new THREE.BufferGeometry().setFromPoints(points);
            const line = new THREE.Line(geometry, material);
            fieldLinesSubGroup.add(line);
        });
        populateArrows(bArrowMesh, header.fl, 2.5);
    }

    if (header.ef) {
        while(efieldLinesSubGroup.children.length > 0){ 
            const child = efieldLinesSubGroup.children[0];
            efieldLinesSubGroup.remove(child); 
            child.geometry.dispose();
            child.material.dispose();
        }
        const material = new THREE.LineBasicMaterial({ color: 0x00ffcc, transparent: true, opacity: 0.9 });
        header.ef.forEach(linePoints => {
            const points = linePoints.map(p => new THREE.Vector3(p[0], p[2], -p[1]));
            const geometry = new THREE.BufferGeometry().setFromPoints(points);
            const line = new THREE.Line(geometry, material);
            efieldLinesSubGroup.add(line);
        });
        populateArrows(eArrowMesh, header.ef, 3.0);
    }
    
    Object.keys(instancedMeshes).forEach(hex => { instancedMeshes[hex].count = 0; });
    Object.keys(trailMeshes).forEach(hex => { trailMeshes[hex].count = 0; });

    const currentParticleIds = new Set();
    const renderRadius = header.r * renderRadiusRatio;
    const particleCount = header.n;
    const safeLen = Math.max(2, maxTrailLength);

    const effectiveHideTrails = hideTrails;

    let offset = 4 + headerLen;

    for (let i = 0; i < particleCount; i++) {
        const id = view.getInt32(offset, true);
        const px = view.getFloat32(offset + 4, true);
        const py = view.getFloat32(offset + 8, true);
        const pz = view.getFloat32(offset + 12, true);
        const status = view.getUint8(offset + 16);
        const color = view.getUint32(offset + 17, true);
        offset += 21;

        currentParticleIds.add(id);

        if (!effectiveHideTrails && !particlesData[id]) {
            particlesData[id] = {
                trailPositions: new Float32Array(safeLen * 3),
                trailIndex: 0,
                trailCount: 0,
                lastColor: color
            };
        }

        const isVisible = Math.sqrt(px * px + py * py + pz * pz) <= renderRadius;

        if (isVisible) {
            const iMesh = getInstancedMesh(color);
            iMesh.visible = !hideParticles;
            if (iMesh.count < maxParticlesPerColor) {
                dummy.position.set(px, py, pz);
                dummy.scale.set(1, 1, 1);
                dummy.updateMatrix();
                iMesh.setMatrixAt(iMesh.count, dummy.matrix);
                iMesh.count++;
                iMesh.instanceMatrix.needsUpdate = true;
            }
        }

        if (!effectiveHideTrails) {
            const pData = particlesData[id];
            if (pData.lastColor !== color) pData.lastColor = color;

            let isTeleport = false;
            if (pData.trailCount > 0) {
                let lastIdx = pData.trailIndex - 1;
                if (lastIdx < 0) lastIdx = safeLen - 1;
                const lx = pData.trailPositions[lastIdx * 3];
                const ly = pData.trailPositions[lastIdx * 3 + 1];
                const lz = pData.trailPositions[lastIdx * 3 + 2];
                const distSq = (lx - px) * (lx - px) + (ly - py) * (ly - py) + (lz - pz) * (lz - pz);
                if (distSq > 4.0) isTeleport = true;
            }

            if (isTeleport) {
                pData.trailCount = 0;
                for (let j = 0; j < safeLen; j++) {
                    pData.trailPositions[j * 3] = px;
                    pData.trailPositions[j * 3 + 1] = py;
                    pData.trailPositions[j * 3 + 2] = pz;
                }
            }

            if (status === 1) {
                if (renderCollided && pData.trailCount > 1) {
                    const geom = new THREE.BufferGeometry();
                    const clonedPositions = new Float32Array(pData.trailCount * 3);
                    let currentIdx = pData.trailIndex - 1;
                    if (currentIdx < 0) currentIdx = safeLen - 1;
                    for (let j = 0; j < pData.trailCount; j++) {
                        let readIdx = currentIdx - j;
                        if (readIdx < 0) readIdx += safeLen;
                        readIdx *= 3;
                        clonedPositions[j * 3] = pData.trailPositions[readIdx];
                        clonedPositions[j * 3 + 1] = pData.trailPositions[readIdx + 1];
                        clonedPositions[j * 3 + 2] = pData.trailPositions[readIdx + 2];
                    }
                    geom.setAttribute('position', new THREE.BufferAttribute(clonedPositions, 3));
                    const mat = new THREE.LineBasicMaterial({ color: color, opacity: 0.3, transparent: true });
                    const permanentLine = new THREE.Line(geom, mat);
                    collidedTrailsGroup.add(permanentLine);
                }
                pData.trailCount = 0;
            } else if (status === 2) {
                pData.trailCount = 0;
            }

            const idx = pData.trailIndex * 3;
            pData.trailPositions[idx] = px;
            pData.trailPositions[idx + 1] = py;
            pData.trailPositions[idx + 2] = pz;
            pData.trailIndex = (pData.trailIndex + 1) % safeLen;
            if (pData.trailCount < safeLen) pData.trailCount++;

            if (isVisible) {
                const tMesh = getTrailMesh(color);
                tMesh.mesh.visible = true;
                if (tMesh.count < maxParticlesPerColor) {
                    const tOffset = tMesh.count * safeLen * 3;
                    let currentIdx = pData.trailIndex - 1;
                    if (currentIdx < 0) currentIdx = safeLen - 1;
                    for (let j = 0; j < pData.trailCount; j++) {
                        let readIdx = currentIdx - j;
                        if (readIdx < 0) readIdx += safeLen;
                        readIdx *= 3;
                        tMesh.positions[tOffset + j * 3] = pData.trailPositions[readIdx];
                        tMesh.positions[tOffset + j * 3 + 1] = pData.trailPositions[readIdx + 1];
                        tMesh.positions[tOffset + j * 3 + 2] = pData.trailPositions[readIdx + 2];
                    }
                    let lastX = px, lastY = py, lastZ = pz;
                    if (pData.trailCount > 0) {
                        let lastReadIdx = currentIdx - (pData.trailCount - 1);
                        if (lastReadIdx < 0) lastReadIdx += safeLen;
                        lastReadIdx *= 3;
                        lastX = pData.trailPositions[lastReadIdx];
                        lastY = pData.trailPositions[lastReadIdx + 1];
                        lastZ = pData.trailPositions[lastReadIdx + 2];
                    }
                    for (let j = pData.trailCount; j < safeLen; j++) {
                        tMesh.positions[tOffset + j * 3] = lastX;
                        tMesh.positions[tOffset + j * 3 + 1] = lastY;
                        tMesh.positions[tOffset + j * 3 + 2] = lastZ;
                    }
                    tMesh.count++;
                }
            }
        }
    }

    Object.keys(trailMeshes).forEach(hex => {
        const sl = Math.max(2, maxTrailLength);
        const tMesh = trailMeshes[hex];
        tMesh.mesh.geometry.attributes.position.needsUpdate = true;
        tMesh.mesh.geometry.setDrawRange(0, tMesh.count * (sl - 1) * 2);
    });

    Object.keys(particlesData).forEach(id => {
        const numId = parseInt(id);
        if (!currentParticleIds.has(numId)) {
            delete particlesData[numId];
        }
    });
    } catch (e) {
        console.error('[Binary] Error:', e);
    }
}

ws.onopen = function() {
    console.log("WebSocket connected.");
    // Do not send local defaults; wait for init_config from server
};

ws.onclose = function() {
    console.log("WebSocket disconnected.");
};

// Animation Loop
function animate() {
    requestAnimationFrame(animate);
    controls.update();
    updateLabels();
    renderer.render(scene, camera);
}
animate();

// Handle window resize
window.addEventListener('resize', () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
});

// ===================================================================
// Preset save/load
// ===================================================================
const presetNameInput = document.getElementById('preset-name');
const presetSelect = document.getElementById('preset-select');
const presetSaveBtn = document.getElementById('preset-save-btn');
const presetLoadBtn = document.getElementById('preset-load-btn');
const presetDelBtn = document.getElementById('preset-del-btn');

function collectSettings() {
    return {
        kp: parseFloat(kpSlider.value),
        comp: parseFloat(compSlider.value),
        autoFetch: autoFetchCb.checked,
        range: parseFloat(rangeSlider.value),
        renderRadius: parseFloat(renderRadiusSlider.value),
        particles: parseInt(ptcSlider.value),
        spawnRatio: parseFloat(spawnRatioSlider.value),
        day: parseInt(daySlider.value),
        gravity: enableGravityCb.checked,
        gravMult: parseFloat(gravMultSlider.value),
        efield: enableEfieldCb.checked,
        efieldModel: parseInt(efieldModel.value),
        efieldMult: parseFloat(efieldMultSlider.value),
        atmos: enableAtmosCb.checked,
        atmosModel: parseInt(atmosModel.value),
        atmosMult: parseFloat(atmosMultSlider.value),
        emitterMode: parseInt(emitterMode.value),
        spawnDist: parseFloat(spawnDistSlider.value),
        lon: parseFloat(lonSlider.value),
        lat: parseFloat(latSlider.value),
        vbase: parseFloat(vbaseSlider.value),
        vrand: parseFloat(vrandSlider.value),
        angrand: parseFloat(angrandSlider.value),
        parkerCustom: parkerCustomCb.checked,
        parkerAngle: parseFloat(parkerAngleSlider.value),
        magModel: parseInt(magModel.value),
        tailEnabled: enableTailCb.checked,
        tailModel: parseInt(tailModel.value),
        mpEnabled: enableMpCb.checked,
        mpModel: parseInt(mpModel.value),
        bMult: parseFloat(bMultSlider.value),
        fieldPrec: parseInt(fieldPrecSlider.value),
        modelPrec: parseInt(modelPrecSlider.value),
        renderMag: renderMagCb.checked,
        renderEfield: renderEFieldCb.checked,
        renderCol: renderColCb.checked,
        hidePtc: hidePtcCb.checked,
        hideTrail: hideTrailCb.checked,
        trailLen: parseInt(trailLenSlider.value),
        particleTypes: pTypes.map(pt => ({...pt}))
    };
}

function applySettings(s) {
    if (!s) return;
    const set = (id, val) => { const el = document.getElementById(id); if (el) el.value = val; };
    const fire = (id, val) => { set(id, val); document.getElementById(id)?.dispatchEvent(new Event('input', {bubbles: true})); };
    const check = (id, val) => { const el = document.getElementById(id); if (el) { el.checked = val; el.dispatchEvent(new Event('change', {bubbles: true})); } };

    fire('kp-slider', s.kp ?? 2.0);
    fire('comp-slider', s.comp ?? 1.22);
    check('auto-fetch-cb', s.autoFetch ?? true);
    fire('range-slider', s.range ?? 12.5);
    fire('render-radius-slider', s.renderRadius ?? 100);
    fire('ptc-slider', s.particles ?? 100);
    fire('spawn-ratio-slider', s.spawnRatio ?? 0.5);
    fire('day-slider', s.day ?? 172);
    check('enable-gravity-cb', s.gravity ?? false);
    fire('grav-mult-slider', s.gravMult ?? 1);
    check('enable-efield-cb', s.efield ?? false);
    set('efield-model', s.efieldModel ?? 0);
    document.getElementById('efield-model')?.dispatchEvent(new Event('change', {bubbles: true}));
    fire('efield-mult-slider', s.efieldMult ?? 1);
    check('enable-atmos-cb', s.atmos ?? false);
    set('atmos-model', s.atmosModel ?? 0);
    document.getElementById('atmos-model')?.dispatchEvent(new Event('change', {bubbles: true}));
    fire('atmos-mult-slider', s.atmosMult ?? 1);
    set('emitter-mode', s.emitterMode ?? 0);
    document.getElementById('emitter-mode')?.dispatchEvent(new Event('change', {bubbles: true}));
    fire('spawn-dist-slider', s.spawnDist ?? 1.0);
    fire('lon-slider', s.lon ?? 0);
    fire('lat-slider', s.lat ?? 0);
    fire('vbase-slider', s.vbase ?? 400);
    fire('vrand-slider', s.vrand ?? 10);
    fire('angrand-slider', s.angrand ?? 5);
    applyParkerUi(s.parkerCustom ?? false, s.parkerAngle ?? 40);
    sendParkerAngle();
    set('mag-model', s.magModel ?? 4);
    document.getElementById('mag-model')?.dispatchEvent(new Event('change', {bubbles: true}));
    check('enable-tail-cb', s.tailEnabled ?? false);
    set('tail-model', s.tailModel ?? 2);
    document.getElementById('tail-model')?.dispatchEvent(new Event('change', {bubbles: true}));
    check('enable-mp-cb', s.mpEnabled ?? false);
    set('mp-model', s.mpModel ?? 1);
    document.getElementById('mp-model')?.dispatchEvent(new Event('change', {bubbles: true}));
    fire('b-mult-slider', s.bMult ?? 1.0);
    fire('field-prec-slider', s.fieldPrec ?? 1);
    fire('model-prec-slider', s.modelPrec ?? 1);
    check('render-mag-cb', s.renderMag ?? true);
    check('render-efield-cb', s.renderEfield ?? true);
    check('render-col-cb', s.renderCol ?? true);
    check('hide-ptc-cb', s.hidePtc ?? false);
    check('hide-trail-cb', s.hideTrail ?? false);
    fire('trail-len-slider', s.trailLen ?? 50);
    // Particle types
    if (s.particleTypes && Array.isArray(s.particleTypes)) {
        pTypes = s.particleTypes.map(pt => ({...pt}));
        nextPtypeId = Math.max(...pTypes.map(p => p.id), 5) + 1;
        renderPTypes();
    }
}

async function refreshPresetList() {
    try {
        const resp = await fetch('/api/preset/list');
        const names = await resp.json();
        const cur = presetSelect.value;
        presetSelect.innerHTML = '<option value="">-- 选择预设 --</option>';
        names.forEach(n => {
            const opt = document.createElement('option');
            opt.value = n; opt.textContent = n;
            if (n === cur) opt.selected = true;
            presetSelect.appendChild(opt);
        });
    } catch(e) { console.error('Preset list error:', e); }
}

presetSaveBtn.addEventListener('click', async () => {
    const name = presetNameInput.value.trim();
    if (!name) { alert('请输入预设名称'); return; }
    try {
        await fetch('/api/preset/save', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name, settings: collectSettings()})
        });
        presetNameInput.value = '';
        await refreshPresetList();
    } catch(e) { alert('保存失败: ' + e); }
});

presetLoadBtn.addEventListener('click', async () => {
    const name = presetSelect.value;
    if (!name) { alert('请选择一个预设'); return; }
    try {
        const resp = await fetch('/api/preset/load', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name})
        });
        const settings = await resp.json();
        applySettings(settings);
    } catch(e) { alert('加载失败: ' + e); }
});

presetDelBtn.addEventListener('click', async () => {
    const name = presetSelect.value;
    if (!name) { alert('请选择一个预设'); return; }
    if (!confirm('删除预设 "' + name + '"？')) return;
    try {
        await fetch('/api/preset/delete', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name})
        });
        await refreshPresetList();
    } catch(e) { alert('删除失败: ' + e); }
});

// Load preset list on startup
refreshPresetList();
