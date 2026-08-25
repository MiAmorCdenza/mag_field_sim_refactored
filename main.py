import asyncio
import json
import threading
import numpy as np
from geopack import geopack
import geopack.t89
import geopack.t96
import geopack.t01
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn
import sys
import os

import physics_ext  # Use the new C++ core!
from solar_data import SolarDataManager

app = FastAPI()

class ConnectionManager:
    def __init__(self):
        self.active_connections = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast_config(self, config: dict, exclude: WebSocket = None):
        for connection in self.active_connections:
            if connection != exclude:
                try:
                    await connection.send_text(json.dumps({"type": "init_config", "config": config}))
                except:
                    pass

manager = ConnectionManager()

# Mount static files
# Get base path for static files whether running as script or pyinstaller exe
if getattr(sys, 'frozen', False):
    # Running in a PyInstaller bundle
    base_path = sys._MEIPASS
else:
    # Running in normal Python environment
    base_path = os.path.dirname(os.path.abspath(__file__))

static_dir = os.path.join(base_path, "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir)

app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
async def get_index():
    return FileResponse(os.path.join(static_dir, "index.html"))

# Global instances
sim_engine = physics_ext.SimulationEngine()
solar_data = SolarDataManager()

# Global state for syncing UI across clients
global_state = {
    "max_range": 10.0,
    "particle_count": 100,
    "day": 172.0,
    "model_prec": 1,
    "field_prec": 1,
    "mag_model": 1,
    "b_multiplier": 1.0,
    "spawn_radius_ratio": 0.5,
    "render_radius_ratio": 1.0,
    "enable_gravity": False,
    "gravity_multiplier": 1.0,
    "enable_electric_field": False,
    "efield_model": 0,
    "electric_field_multiplier": 1.0,
    "enable_atmosphere": False,
    "atmos_model": 0,
    "atmosphere_multiplier": 1.0,
    "emitter_mode": 0,
    "emitter_lon": 0.0,
    "emitter_lat": 0.0,
    "v_base": 400.0,
    "v_random": 10.0,
    "angle_random": 5.0,
    "dist_ratio": 1.0,
    "particle_types": [
        {"id": 1, "name": "正电荷", "q": 1, "m": 0.1, "v": 1.0, "weight": 1.0, "color": "#ff3333", "checked": True},
        {"id": 2, "name": "负电荷", "q": -1, "m": 0.1, "v": 1.0, "weight": 1.0, "color": "#3333ff", "checked": True},
        {"id": 3, "name": "质子 (H+)", "q": 1, "m": 1, "v": 1.0, "weight": 1.0, "color": "#ff8800", "checked": False},
        {"id": 4, "name": "电子 (e-)", "q": -1, "m": 0.00054, "v": 1.0, "weight": 1.0, "color": "#00ffff", "checked": False},
        {"id": 5, "name": "α粒子 (He2+)", "q": 2, "m": 4, "v": 1.0, "weight": 1.0, "color": "#ff00ff", "checked": False}
    ]
}

# Initialize sim_engine with global_state
sim_engine.max_range = global_state["max_range"]
sim_engine.set_particle_count(global_state["particle_count"])
sim_engine.set_day_of_year(global_state["day"])
sim_engine.set_model_precision(global_state["model_prec"])
sim_engine.set_field_precision(global_state["field_prec"])
sim_engine.set_b_multiplier(global_state["b_multiplier"])
sim_engine.set_spawn_radius_ratio(global_state["spawn_radius_ratio"])
sim_engine.enable_gravity = global_state["enable_gravity"]
sim_engine.gravity_multiplier = global_state["gravity_multiplier"]
sim_engine.enable_electric_field = global_state["enable_electric_field"]
sim_engine.efield_model = global_state["efield_model"]
sim_engine.electric_field_multiplier = global_state["electric_field_multiplier"]
sim_engine.enable_atmosphere = global_state["enable_atmosphere"]
sim_engine.atmos_model = global_state["atmos_model"]
sim_engine.atmosphere_multiplier = global_state["atmosphere_multiplier"]
sim_engine.set_emitter_params(
    global_state["emitter_mode"],
    global_state["emitter_lon"],
    global_state["emitter_lat"],
    global_state["v_base"],
    global_state["v_random"],
    global_state["angle_random"],
    global_state["dist_ratio"]
)
sim_engine.clear_particle_types()
for t in global_state["particle_types"]:
    if t["checked"]:
        sim_engine.add_particle_type(float(t["q"]), float(t["m"]), int(t["color"].replace("#", ""), 16), float(t["v"]), float(t.get("weight", 1.0)))
sim_engine.respawn_all()

class GridManager:
    def __init__(self, engine):
        self.engine = engine
        self.last_iopt = None
        self.last_ps = None
        self.last_mag_model = None
        self.is_computing = False
        self.lock = threading.Lock()
        
        # Grid parameters
        self.xmin, self.xmax, self.nx = -40.0, 20.0, 61
        self.ymin, self.ymax, self.ny = -20.0, 20.0, 41
        self.zmin, self.zmax, self.nz = -20.0, 20.0, 41
        
        x = np.linspace(self.xmin, self.xmax, self.nx)
        y = np.linspace(self.ymin, self.ymax, self.ny)
        z = np.linspace(self.zmin, self.zmax, self.nz)
        X, Y, Z = np.meshgrid(x, y, z, indexing='ij')
        self.X_flat = X.flatten()
        self.Y_flat = Y.flatten()
        self.Z_flat = Z.flatten()

    def update_grid_if_needed(self, kp, total_tilt, mag_model):
        iopt = int(kp) + 1
        if iopt < 1: iopt = 1
        if iopt > 7: iopt = 7
        
        ps = total_tilt # Dipole tilt angle
        
        with self.lock:
            if self.is_computing:
                return
            if self.last_iopt == iopt and self.last_ps is not None and abs(self.last_ps - ps) < 0.01 and self.last_mag_model == mag_model:
                return
            self.is_computing = True
            
        def compute_worker():
            try:
                if mag_model == 0:
                    print("Using simple mag model. Clearing grid.")
                    self.engine.set_magnetic_grid(-1, 1, 0, -1, 1, 0, -1, 1, 0, [], [], [])
                elif mag_model == 1:
                    print(f"Computing T89 grid for iopt={iopt}, ps={ps:.3f}...")
                    v_t89 = np.vectorize(lambda x,y,z: geopack.t89.t89(iopt, ps, x, y, z))
                    bx, by, bz = v_t89(self.X_flat, self.Y_flat, self.Z_flat)
                    
                    # Prevent any NaN values from T89 singularities (e.g., at the exact origin)
                    bx = np.nan_to_num(bx, nan=0.0)
                    by = np.nan_to_num(by, nan=0.0)
                    bz = np.nan_to_num(bz, nan=0.0)
                    
                    # Pass to C++
                    self.engine.set_magnetic_grid(
                        self.xmin, self.xmax, self.nx,
                        self.ymin, self.ymax, self.ny,
                        self.zmin, self.zmax, self.nz,
                        bx.tolist(), by.tolist(), bz.tolist()
                    )
                elif mag_model == 2:
                    print(f"Computing T96 grid for kp={kp:.2f}...")
                    pdyn = 2.0 + kp * 0.5
                    dst = -10.0 * kp
                    by_imf = 0.0
                    bz_imf = -2.0 - kp
                    parmod = [pdyn, dst, by_imf, bz_imf, 0, 0, 0, 0, 0, 0]
                    
                    def safe_t96(x, y, z):
                        r = np.sqrt(x**2 + y**2 + z**2)
                        # Avoid singularity at the exact center (Earth's core)
                        if r < 0.1:
                            return 0.0, 0.0, 0.0
                        try:
                            return geopack.t96.t96(parmod, ps, x, y, z)
                        except Exception:
                            return 0.0, 0.0, 0.0
                            
                    v_t96 = np.vectorize(safe_t96)
                    bx, by, bz = v_t96(self.X_flat, self.Y_flat, self.Z_flat)
                    bx = np.nan_to_num(bx, nan=0.0)
                    by = np.nan_to_num(by, nan=0.0)
                    bz = np.nan_to_num(bz, nan=0.0)
                    self.engine.set_magnetic_grid(
                        self.xmin, self.xmax, self.nx,
                        self.ymin, self.ymax, self.ny,
                        self.zmin, self.zmax, self.nz,
                        bx.tolist(), by.tolist(), bz.tolist()
                    )
                elif mag_model == 3:
                    print(f"Computing T01 grid for kp={kp:.2f}...")
                    pdyn = 2.0 + kp * 0.5
                    dst = -10.0 * kp
                    by_imf = 0.0
                    bz_imf = -2.0 - kp
                    parmod = [pdyn, dst, by_imf, bz_imf, 0, 0, 0, 0, 0, 0]
                    
                    def safe_t01(x, y, z):
                        r = np.sqrt(x**2 + y**2 + z**2)
                        # Avoid singularity at the exact center (Earth's core)
                        if r < 0.1:
                            return 0.0, 0.0, 0.0
                        if x < -15.0:
                            # T01 is not valid beyond x=-15 Re in the tail.
                            # Fallback to T96 for the deep tail region.
                            try:
                                return geopack.t96.t96(parmod, ps, x, y, z)
                            except Exception:
                                return 0.0, 0.0, 0.0
                        else:
                            try:
                                return geopack.t01.t01(parmod, ps, x, y, z)
                            except Exception:
                                return 0.0, 0.0, 0.0
                             
                    v_t01 = np.vectorize(safe_t01)
                    bx, by, bz = v_t01(self.X_flat, self.Y_flat, self.Z_flat)
                    bx = np.nan_to_num(bx, nan=0.0)
                    by = np.nan_to_num(by, nan=0.0)
                    bz = np.nan_to_num(bz, nan=0.0)
                    self.engine.set_magnetic_grid(
                        self.xmin, self.xmax, self.nx,
                        self.ymin, self.ymax, self.ny,
                        self.zmin, self.zmax, self.nz,
                        bx.tolist(), by.tolist(), bz.tolist()
                    )
                    
                print(f"Grid for mag_model={mag_model} updated successfully.")
                
                with self.lock:
                    self.last_iopt = iopt
                    self.last_ps = ps
                    self.last_mag_model = mag_model
                    self.is_computing = False
            except Exception as e:
                print(f"Grid computation failed: {e}")
                with self.lock:
                    self.is_computing = False

        threading.Thread(target=compute_worker, daemon=True).start()

grid_manager = GridManager(sim_engine)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    print("Client connected via WebSocket")
    
    # Send initial configuration to client
    await websocket.send_text(json.dumps({
        "type": "init_config",
        "config": global_state
    }))
    
    # Task to read messages from client
    async def read_from_client():
        try:
            while True:
                data = await websocket.receive_text()
                msg = json.loads(data)
                
                # Flag to check if we should broadcast config changes
                config_changed = False
                
                if msg.get("type") == "set_max_range":
                    val = float(msg["value"])
                    global_state["max_range"] = val
                    sim_engine.max_range = val
                    config_changed = True
                elif msg.get("type") == "set_particle_count":
                    val = int(msg["value"])
                    global_state["particle_count"] = val
                    sim_engine.set_particle_count(val)
                    config_changed = True
                elif msg.get("type") == "set_day":
                    val = float(msg["value"])
                    global_state["day"] = val
                    sim_engine.set_day_of_year(val)
                    config_changed = True
                elif msg.get("type") == "set_mag_model":
                    val = int(msg["value"])
                    global_state["mag_model"] = val
                    config_changed = True
                elif msg.get("type") == "set_model_prec":
                    val = int(msg["value"])
                    global_state["model_prec"] = val
                    sim_engine.set_model_precision(val)
                    config_changed = True
                elif msg.get("type") == "set_field_prec":
                    val = int(msg["value"])
                    global_state["field_prec"] = val
                    sim_engine.set_field_precision(val)
                    config_changed = True
                elif msg.get("type") == "set_b_multiplier":
                    val = float(msg["value"])
                    global_state["b_multiplier"] = val
                    sim_engine.set_b_multiplier(val)
                    config_changed = True
                elif msg.get("type") == "set_spawn_radius_ratio":
                    val = float(msg["value"])
                    global_state["spawn_radius_ratio"] = val
                    sim_engine.set_spawn_radius_ratio(val)
                    config_changed = True
                elif msg.get("type") == "set_render_radius_ratio":
                    val = float(msg["value"])
                    global_state["render_radius_ratio"] = val
                    config_changed = True
                elif msg.get("type") == "set_enable_gravity":
                    val = bool(msg["value"])
                    global_state["enable_gravity"] = val
                    sim_engine.enable_gravity = val
                    config_changed = True
                elif msg.get("type") == "set_gravity_multiplier":
                    val = float(msg["value"])
                    global_state["gravity_multiplier"] = val
                    sim_engine.gravity_multiplier = val
                    config_changed = True
                elif msg.get("type") == "set_enable_electric_field":
                    val = bool(msg["value"])
                    global_state["enable_electric_field"] = val
                    sim_engine.enable_electric_field = val
                    config_changed = True
                elif msg.get("type") == "set_efield_model":
                    val = int(msg["value"])
                    global_state["efield_model"] = val
                    sim_engine.efield_model = val
                    config_changed = True
                elif msg.get("type") == "set_electric_field_multiplier":
                    val = float(msg["value"])
                    global_state["electric_field_multiplier"] = val
                    sim_engine.electric_field_multiplier = val
                    config_changed = True
                elif msg.get("type") == "set_enable_atmosphere":
                    val = bool(msg["value"])
                    global_state["enable_atmosphere"] = val
                    sim_engine.enable_atmosphere = val
                    config_changed = True
                elif msg.get("type") == "set_atmos_model":
                    val = int(msg["value"])
                    global_state["atmos_model"] = val
                    sim_engine.atmos_model = val
                    config_changed = True
                elif msg.get("type") == "set_atmosphere_multiplier":
                    val = float(msg["value"])
                    global_state["atmosphere_multiplier"] = val
                    sim_engine.atmosphere_multiplier = val
                    config_changed = True
                elif msg.get("type") == "set_emitter_params":
                    mode = int(msg.get("mode", 0))
                    lon = float(msg.get("lon", 0.0))
                    lat = float(msg.get("lat", 0.0))
                    v_base = float(msg.get("v_base", 400.0))
                    v_random = float(msg.get("v_random", 10.0))
                    angle_random = float(msg.get("angle_random", 5.0))
                    dist_ratio = float(msg.get("dist_ratio", 1.0))
                    
                    global_state["emitter_mode"] = mode
                    global_state["emitter_lon"] = lon
                    global_state["emitter_lat"] = lat
                    global_state["v_base"] = v_base
                    global_state["v_random"] = v_random
                    global_state["angle_random"] = angle_random
                    global_state["dist_ratio"] = dist_ratio
                    
                    sim_engine.set_emitter_params(mode, lon, lat, v_base, v_random, angle_random, dist_ratio)
                    config_changed = True
                elif msg.get("type") == "set_particle_types":
                    if "raw_types" in msg:
                        global_state["particle_types"] = msg["raw_types"]
                    
                    sim_engine.clear_particle_types()
                    types = msg.get("types", [])
                    for t in types:
                        sim_engine.add_particle_type(float(t["q"]), float(t["mass"]), int(t["color"]), float(t.get("v_multiplier", 1.0)), float(t.get("weight", 1.0)))
                    sim_engine.respawn_all()
                    config_changed = True
                elif msg.get("type") == "respawn_all":
                    sim_engine.respawn_all()
                
                if config_changed:
                    await manager.broadcast_config(global_state, exclude=websocket)
                    
        except WebSocketDisconnect:
            pass

    client_task = asyncio.create_task(read_from_client())
    
    try:
        last_kp = None
        while True:
            # Update solar activity based on fetched Kp index
            kp = solar_data.get_kp_index()
            if kp != last_kp:
                sim_engine.set_solar_activity(kp)
                last_kp = kp
                
            grid_manager.update_grid_if_needed(kp, sim_engine.total_tilt, global_state["mag_model"])
            
            # Perform multiple steps per frame to speed up the simulation visually
            for _ in range(5):
                sim_engine.step()
                
            state = sim_engine.get_state()
            
            data = {
                "kp_index": kp,
                "compression": sim_engine.solar_wind_compression,
                "max_range": sim_engine.max_range,
                "seasonal_tilt": sim_engine.seasonal_tilt,
                "total_tilt": sim_engine.total_tilt,
                "particles": state
            }
            
            if getattr(sim_engine, 'needs_field_update', False):
                # Compute field lines and send them to the frontend
                data["field_lines"] = sim_engine.compute_field_lines()
                sim_engine.needs_field_update = False
            
            await websocket.send_text(json.dumps(data))
            
            # Send ~60 frames per second
            await asyncio.sleep(1.0 / 60.0)
    except (WebSocketDisconnect, RuntimeError, Exception) as e:
        print(f"Client disconnected or error: {e}")
    finally:
        client_task.cancel()
        manager.disconnect(websocket)

if __name__ == "__main__":
    import multiprocessing
    # This is required for PyInstaller to work with multiprocessing
    multiprocessing.freeze_support()
    # In PyInstaller, running uvicorn programmatically needs to reference the app differently
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
