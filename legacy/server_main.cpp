#include <iostream>
#include <string>
#include <thread>
#include <chrono>
#include <condition_variable>
#include <mutex>
#include <optional>
#include <fstream>
#include <unordered_set>
#include <future>
#include <sstream>

#include "crow.h"
#include <pybind11/embed.h>
#include <pybind11/stl.h>
#include <nlohmann/json.hpp>

namespace py = pybind11;
using json = nlohmann::json;

// Include the refactored physics engine directly
#include "physics_engine.cpp"

// Global state matching Python's global_state
json global_state;
std::mutex state_mutex;

// Active websocket connections
std::unordered_set<crow::websocket::connection*> active_connections;
std::mutex connections_mutex;

struct GridJobParams {
    int mag_model = 0;
    int tail_model = 0;
    int magnetopause_model = 0;
    int imf_polarity = -1;
    bool parker_custom = false;
    double parker_angle = 40.0;
    double kp = 2.0;
    double ps = 0.0;
    uint64_t seq = 0;
};

struct GridJobResult {
    GridJobParams params;
    bool clear_grid = false;
    bool success = true;
    std::string error;
    std::vector<double> bx, by, bz, xs, ys, zs;
};

std::mutex grid_job_mutex;
std::condition_variable grid_job_cv;
bool grid_worker_running = true;
bool grid_request_pending = false;
bool grid_job_active = false;
bool has_latest_grid_request = false;
uint64_t grid_request_seq = 0;
GridJobParams latest_grid_request;
std::optional<GridJobResult> completed_grid_job;

void broadcast_text(const std::string& data);

bool same_grid_params(const GridJobParams& a, const GridJobParams& b) {
    return a.mag_model == b.mag_model &&
           a.tail_model == b.tail_model &&
           a.magnetopause_model == b.magnetopause_model &&
           a.imf_polarity == b.imf_polarity &&
           a.parker_custom == b.parker_custom &&
           std::abs(a.parker_angle - b.parker_angle) < 0.01 &&
           std::abs(a.kp - b.kp) < 0.01 &&
           std::abs(a.ps - b.ps) < 0.01;
}

void broadcast_grid_progress(uint64_t seq, const std::string& state, const std::string& note = "") {
    json progress;
    progress["type"] = "grid_progress";
    progress["state"] = state;
    progress["seq"] = seq;
    if (!note.empty()) progress["note"] = note;
    broadcast_text(progress.dump());
}

void broadcast_config(crow::websocket::connection* exclude = nullptr) {
    json msg;
    msg["type"] = "init_config";
    {
        std::lock_guard<std::mutex> lock(state_mutex);
        msg["config"] = global_state;
    }
    std::string msg_str = msg.dump();
    
    std::lock_guard<std::mutex> lock(connections_mutex);
    for (auto* conn : active_connections) {
        if (conn != exclude) {
            conn->send_text(msg_str);
        }
    }
}

void broadcast_data(const std::string& data) {
    std::lock_guard<std::mutex> lock(connections_mutex);
    for (auto* conn : active_connections) {
        conn->send_binary(data);
    }
}

void broadcast_text(const std::string& data) {
    std::lock_guard<std::mutex> lock(connections_mutex);
    for (auto* conn : active_connections) {
        conn->send_text(data);
    }
}

// Initialize default global state
void init_global_state(const json& config) {
    std::cout << "DEBUG: Entering init_global_state" << std::endl;
    // Default values
    global_state = {
        {"max_range", 90.0},
        {"particle_count", 100},
        {"day", 172.0},
        {"model_prec", 1},
        {"field_prec", 1},
        {"mag_model", 1},
        {"tail_model", 0},
        {"magnetopause_model", 0},
        {"parker_custom", false},
        {"parker_angle", 40.0},
        {"b_multiplier", 1.0},
        {"spawn_radius_ratio", 0.5},
        {"render_radius_ratio", 1.0},
        {"enable_gravity", false},
        {"gravity_multiplier", 1.0},
        {"enable_electric_field", false},
        {"efield_model", 0},
        {"electric_field_multiplier", 1.0},
        {"enable_atmosphere", false},
        {"atmos_model", 0},
        {"atmosphere_multiplier", 1.0},
        {"emitter_mode", 0},
        {"emitter_lon", 0.0},
        {"emitter_lat", 0.0},
        {"v_base", 400.0},
        {"v_random", 10.0},
        {"angle_random", 5.0},
        {"dist_ratio", 1.0},
        {"kp", 2.0},
        {"solar_wind_compression", 1.22},
        {"auto_fetch_solar", true},
        {"imf_polarity", -1},
        {"particle_types", json::array({
            json::parse("{\"id\": 1, \"name\": \"Positive Charge\", \"q\": 1.0, \"m\": 0.1, \"v\": 1.0, \"weight\": 1.0, \"color\": \"#ff3333\", \"checked\": true}"),
            json::parse("{\"id\": 2, \"name\": \"Negative Charge\", \"q\": -1.0, \"m\": 0.1, \"v\": 1.0, \"weight\": 1.0, \"color\": \"#3333ff\", \"checked\": true}"),
            json::parse("{\"id\": 3, \"name\": \"Proton\", \"q\": 1.0, \"m\": 1.0, \"v\": 1.0, \"weight\": 1.0, \"color\": \"#ff8800\", \"checked\": false}"),
            json::parse("{\"id\": 4, \"name\": \"Electron\", \"q\": -1.0, \"m\": 0.00054, \"v\": 1.0, \"weight\": 1.0, \"color\": \"#00ffff\", \"checked\": false}"),
            json::parse("{\"id\": 5, \"name\": \"Alpha\", \"q\": 2.0, \"m\": 4.0, \"v\": 1.0, \"weight\": 1.0, \"color\": \"#ff00ff\", \"checked\": false}")
        })}
    };
    std::cout << "DEBUG: global_state initialized" << std::endl;

    // Override with config.json if available
    if (config.contains("default_state")) {
        for (auto& [key, value] : config["default_state"].items()) {
            global_state[key] = value;
        }
        std::cout << "DEBUG: global_state overridden from config" << std::endl;
    }
}

int main() {
    std::cout << "🚀 Starting Pure C++ MagFieldSim Server with Embedded Python..." << std::endl;

    // Load config.json
    std::string host = "0.0.0.0";
    int port = 8001;
    int fps = 60;
    int steps_per_frame = 5;
    int network_fps = 30;
    json main_config;

    std::ifstream config_file("config.json");
    if (config_file.is_open()) {
        try {
            config_file >> main_config;
            if (main_config.contains("server")) {
                if (main_config["server"].contains("host")) host = main_config["server"]["host"];
                if (main_config["server"].contains("port")) port = main_config["server"]["port"];
            }
            if (main_config.contains("simulation")) {
                if (main_config["simulation"].contains("fps")) fps = main_config["simulation"]["fps"];
                if (main_config["simulation"].contains("steps_per_frame")) steps_per_frame = main_config["simulation"]["steps_per_frame"];
            }
            if (main_config.contains("network")) {
                if (main_config["network"].contains("fps")) network_fps = main_config["network"]["fps"];
            }
            std::cout << "✅ Loaded config.json (Host: " << host << ", Port: " << port << ", NetFPS: " << network_fps << ")" << std::endl;
        } catch (const std::exception& e) {
            std::cerr << "⚠️ Failed to parse config.json: " << e.what() << std::endl;
        }
    } else {
        std::cout << "⚠️ config.json not found, using defaults." << std::endl;
    }

    // Initialize Python interpreter
    py::scoped_interpreter guard{};
    std::cout << "✅ Python interpreter initialized." << std::endl;

    // Add current directory to Python path
    py::module_ sys = py::module_::import("sys");
    sys.attr("path").attr("append")(".");

    // Import our python bridge
    py::module_ python_bridge;
    try {
        python_bridge = py::module_::import("python_bridge");
        std::cout << "✅ python_bridge loaded." << std::endl;
    } catch (const std::exception& e) {
        std::cerr << "❌ Failed to load python_bridge: " << e.what() << std::endl;
        return 1;
    }

    init_global_state(main_config);

    // Sync IMF-related runtime parameters to Python bridge at startup
    {
        int startup_polarity = global_state.value("imf_polarity", -1);
        bool startup_parker_custom = global_state.value("parker_custom", false);
        double startup_parker_angle = global_state.value("parker_angle", 40.0);
        try {
            py::gil_scoped_acquire acquire;
            python_bridge.attr("set_imf_polarity")(startup_polarity);
            python_bridge.attr("set_parker_params")(startup_parker_custom, startup_parker_angle);
            std::cout << "✅ IMF polarity synced: " << startup_polarity << std::endl;
            std::cout << "✅ Parker params synced: enabled=" << startup_parker_custom
                      << " angle=" << startup_parker_angle << std::endl;
        } catch (const std::exception& e) {
            std::cerr << "⚠️ Failed to sync IMF runtime params: " << e.what() << std::endl;
        }
    }

    SimulationEngine sim_engine;
    std::cout << "DEBUG: sim_engine created" << std::endl;
    
    // Sync sim_engine with default global_state
    sim_engine.set_max_range(global_state["max_range"]);
    sim_engine.set_particle_count(global_state["particle_count"]);
    sim_engine.set_day_of_year(global_state["day"]);
    sim_engine.set_model_precision(global_state["model_prec"]);
    sim_engine.set_field_precision(global_state["field_prec"]);
    sim_engine.set_b_multiplier(global_state["b_multiplier"]);
    sim_engine.set_spawn_radius_ratio(global_state["spawn_radius_ratio"]);
    sim_engine.enable_gravity = global_state["enable_gravity"];
    sim_engine.gravity_multiplier = global_state["gravity_multiplier"];
    sim_engine.enable_electric_field = global_state["enable_electric_field"];
    sim_engine.efield_model = global_state["efield_model"];
    sim_engine.electric_field_multiplier = global_state["electric_field_multiplier"];
    sim_engine.enable_atmosphere = global_state["enable_atmosphere"];
    sim_engine.atmos_model = global_state["atmos_model"];
    sim_engine.atmosphere_multiplier = global_state["atmosphere_multiplier"];
    sim_engine.set_emitter_params(
        global_state["emitter_mode"], global_state["emitter_lon"], global_state["emitter_lat"],
        global_state["v_base"], global_state["v_random"], global_state["angle_random"], global_state["dist_ratio"]
    );
    std::cout << "DEBUG: synced basic fields" << std::endl;

    sim_engine.set_compression(global_state.value("solar_wind_compression", 1.22));
    std::cout << "DEBUG: synced kp/compression" << std::endl;

    sim_engine.clear_particle_types();
    for (const auto& t : global_state["particle_types"]) {
        if (t["checked"].get<bool>()) {
                std::string color_str = t["color"].get<std::string>();
                int color_hex = std::stoi(color_str.substr(1), nullptr, 16);
                sim_engine.add_particle_type(t["q"].get<double>(), t["m"].get<double>(), color_hex, t["v"].get<double>(), t.value("weight", 1.0));
            }
    }
    std::cout << "DEBUG: synced particle types" << std::endl;
    sim_engine.respawn_all();
    std::cout << "DEBUG: sim_engine fully synced" << std::endl;

    bool running = true;

    // Initialize KP before starting simulation
    double last_kp = global_state.value("kp", 2.0);
    bool auto_fetch_init = global_state.value("auto_fetch_solar", true);
    if (auto_fetch_init) {
        py::gil_scoped_acquire acquire;
        try {
            double init_kp = python_bridge.attr("get_solar_data")().cast<double>();
            if (init_kp >= 0) {
                last_kp = init_kp;
                std::cout << "INFO: Live solar Kp = " << last_kp << std::endl;
            }
        } catch (const std::exception& e) {
            std::cerr << "[Python] Solar fetch failed: " << e.what() << std::endl;
        }
        sim_engine.set_solar_activity(last_kp);
        {
            std::lock_guard<std::mutex> lock(state_mutex);
            global_state["kp"] = last_kp;
            global_state["solar_wind_compression"] = sim_engine.get_compression();
        }
    }
    std::cout << "INFO: Using Kp = " << last_kp << " comp = " << sim_engine.get_compression() << std::endl;

    // Pre-compute initial magnetic grid synchronously in main thread
    {
        int initial_model;
        {
            std::lock_guard<std::mutex> lock(state_mutex);
            initial_model = global_state["mag_model"];
        }
        if (initial_model > 0) {
            int initial_tail_model;
            int initial_mp_model;
            {
                std::unique_lock<std::mutex> lock(state_mutex);
                initial_tail_model = global_state["tail_model"];
                initial_mp_model = global_state["magnetopause_model"];
            }
            std::cout << "[Grid] Computing initial grid (model=" << initial_model << ", tail=" << initial_tail_model << ", mp=" << initial_mp_model << ")..." << std::endl;
            try {
                py::gil_scoped_acquire acquire;
                py::tuple result = python_bridge.attr("compute_grid")(
                    initial_model, last_kp, sim_engine.b_field.total_tilt, initial_tail_model, initial_mp_model,
                    py::make_tuple(-90.0, 25.0, 80),
                    py::make_tuple(-45.0, 45.0, 72),
                    py::make_tuple(-45.0, 45.0, 72)
                );
                auto bx = result[0].cast<std::vector<double>>();
                auto by = result[1].cast<std::vector<double>>();
                auto bz = result[2].cast<std::vector<double>>();
                auto xs = result[3].cast<std::vector<double>>();
                auto ys = result[4].cast<std::vector<double>>();
                auto zs = result[5].cast<std::vector<double>>();
                sim_engine.set_magnetic_grid(xs, ys, zs, bx, by, bz);
                std::cout << "[Grid] Initial grid ready (" << bx.size() << " cells)." << std::endl;
            } catch (const std::exception& e) {
                std::cerr << "[Grid] Pre-compute failed: " << e.what() << std::endl;
            }
        }
    }

    {
        std::lock_guard<std::mutex> lock(state_mutex);
        latest_grid_request.mag_model = global_state["mag_model"];
        latest_grid_request.tail_model = global_state["tail_model"];
        latest_grid_request.magnetopause_model = global_state["magnetopause_model"];
        latest_grid_request.imf_polarity = global_state.value("imf_polarity", -1);
        latest_grid_request.parker_custom = global_state.value("parker_custom", false);
        latest_grid_request.parker_angle = global_state.value("parker_angle", 40.0);
        latest_grid_request.kp = global_state.value("kp", last_kp);
        latest_grid_request.ps = sim_engine.b_field.total_tilt;
        latest_grid_request.seq = 0;
        has_latest_grid_request = true;
    }

    // Background grid computation worker.
    // Computes only the latest requested parameter set and discards stale results.
    std::thread grid_thread([&]() {
        while (true) {
            GridJobParams job;
            {
                std::unique_lock<std::mutex> lock(grid_job_mutex);
                grid_job_cv.wait(lock, [&]() { return !grid_worker_running || grid_request_pending; });
                if (!grid_worker_running) break;
                job = latest_grid_request;
                grid_request_pending = false;
                grid_job_active = true;
            }

            broadcast_grid_progress(job.seq, "computing");

            GridJobResult result;
            result.params = job;
            if (job.mag_model == 0) {
                result.clear_grid = true;
            } else {
                try {
                    py::gil_scoped_acquire acquire;
                    py::tuple py_result = python_bridge.attr("compute_grid")(
                        job.mag_model, job.kp, job.ps, job.tail_model, job.magnetopause_model,
                        py::make_tuple(-90.0, 25.0, 80),
                        py::make_tuple(-45.0, 45.0, 72),
                        py::make_tuple(-45.0, 45.0, 72)
                    );
                    result.bx = py_result[0].cast<std::vector<double>>();
                    result.by = py_result[1].cast<std::vector<double>>();
                    result.bz = py_result[2].cast<std::vector<double>>();
                    result.xs = py_result[3].cast<std::vector<double>>();
                    result.ys = py_result[4].cast<std::vector<double>>();
                    result.zs = py_result[5].cast<std::vector<double>>();
                } catch (const std::exception& e) {
                    result.success = false;
                    result.error = e.what();
                }
            }

            bool stale = false;
            uint64_t latest_seq = job.seq;
            {
                std::lock_guard<std::mutex> lock(grid_job_mutex);
                grid_job_active = false;
                latest_seq = latest_grid_request.seq;
                stale = has_latest_grid_request && latest_seq != job.seq;
                if (!stale) {
                    completed_grid_job = std::move(result);
                }
            }

            if (stale) {
                std::cout << "[Grid] Discarded stale result seq=" << job.seq
                          << " latest_seq=" << latest_seq << std::endl;
                broadcast_grid_progress(job.seq, "superseded");
            }
        }
    });

    // Background Simulation Thread
    std::thread sim_thread([&]() {
        try {
            auto next_solar_update = std::chrono::steady_clock::now() + std::chrono::minutes(5);
            int frame_count = 0;
            int broadcast_interval = std::max(1, fps / std::max(1, network_fps));

            while (running) {
                auto frame_start = std::chrono::steady_clock::now();
                double current_kp = last_kp;

                // 1. Fetch Solar Data (every 5 mins, only if auto_fetch enabled)
                if (std::chrono::steady_clock::now() >= next_solar_update) {
                    bool auto_fetch = true;
                    {
                        std::lock_guard<std::mutex> lock(state_mutex);
                        auto_fetch = global_state.value("auto_fetch_solar", true);
                    }
                    if (auto_fetch) {
                        try {
                            py::gil_scoped_acquire acquire;
                            current_kp = python_bridge.attr("get_solar_data")().cast<double>();
                            if (current_kp >= 0 && std::abs(current_kp - last_kp) > 0.01) {
                                sim_engine.set_solar_activity(current_kp);
                                last_kp = current_kp;
                                std::lock_guard<std::mutex> lock(state_mutex);
                                global_state["kp"] = last_kp;
                                global_state["solar_wind_compression"] = sim_engine.get_compression();
                            }
                        } catch (const std::exception& e) {
                            std::cerr << "[Python Error] Fetching solar data: " << e.what() << std::endl;
                        }
                    }
                    next_solar_update = std::chrono::steady_clock::now() + std::chrono::minutes(5);
                }

                // 2. Queue grid update if parameters changed
                GridJobParams current_grid;
                current_grid.ps = sim_engine.b_field.total_tilt;
                {
                    std::lock_guard<std::mutex> lock(state_mutex);
                    current_grid.mag_model = global_state["mag_model"];
                    current_grid.tail_model = global_state["tail_model"];
                    current_grid.magnetopause_model = global_state["magnetopause_model"];
                    current_grid.imf_polarity = global_state.value("imf_polarity", -1);
                    current_grid.parker_custom = global_state.value("parker_custom", false);
                    current_grid.parker_angle = global_state.value("parker_angle", 40.0);
                    current_grid.kp = global_state.value("kp", current_kp);
                }

                bool queued_new_grid = false;
                uint64_t queued_seq = 0;
                {
                    std::lock_guard<std::mutex> lock(grid_job_mutex);
                    if (!has_latest_grid_request || !same_grid_params(current_grid, latest_grid_request)) {
                        current_grid.seq = ++grid_request_seq;
                        latest_grid_request = current_grid;
                        has_latest_grid_request = true;
                        grid_request_pending = true;
                        queued_new_grid = true;
                        queued_seq = current_grid.seq;
                    }
                }
                if (queued_new_grid) {
                    std::cout << "[Grid] Queued seq=" << queued_seq
                              << " mag_model=" << current_grid.mag_model
                              << " kp=" << current_grid.kp
                              << " ps=" << current_grid.ps
                              << " tail=" << current_grid.tail_model
                              << " mp=" << current_grid.magnetopause_model
                              << " parker=" << current_grid.parker_custom
                              << " angle=" << current_grid.parker_angle
                              << std::endl;
                    broadcast_grid_progress(queued_seq, "queued");
                    grid_job_cv.notify_one();
                }

                // 3. Apply completed grid result on the simulation thread
                std::optional<GridJobResult> ready_grid;
                {
                    std::lock_guard<std::mutex> lock(grid_job_mutex);
                    if (completed_grid_job.has_value()) {
                        ready_grid = std::move(completed_grid_job);
                        completed_grid_job.reset();
                    }
                }
                if (ready_grid.has_value()) {
                    const auto& result = *ready_grid;
                    if (!result.success) {
                        std::cerr << "[Grid] Error seq=" << result.params.seq << ": " << result.error << std::endl;
                        broadcast_grid_progress(result.params.seq, "error", result.error);
                    } else if (result.clear_grid) {
                        sim_engine.set_magnetic_grid({}, {}, {}, {}, {}, {});
                        std::cout << "[Grid] Applied clear-grid seq=" << result.params.seq << std::endl;
                        broadcast_grid_progress(result.params.seq, "done");
                    } else {
                        sim_engine.set_magnetic_grid(result.xs, result.ys, result.zs, result.bx, result.by, result.bz);
                        std::cout << "[Grid] Applied seq=" << result.params.seq
                                  << " cells=" << result.bx.size() << std::endl;
                        broadcast_grid_progress(result.params.seq, "done");
                    }
                }

                // 4. Step physics
                for (int i = 0; i < steps_per_frame; ++i) {
                    sim_engine.step();
                }

                // 5. Broadcast State (at network_fps rate)
                if (frame_count % broadcast_interval == 0) {
                    json header;
                    header["type"] = "s";
                    header["k"] = last_kp;
                    header["c"] = sim_engine.get_compression();
                    header["r"] = sim_engine.get_max_range();
                    header["st"] = sim_engine.b_field.seasonal_tilt;
                    header["tt"] = sim_engine.b_field.total_tilt;

                    if (sim_engine.needs_field_update) {
                        header["fl"] = sim_engine.compute_field_lines();
                        header["ef"] = sim_engine.compute_efield_lines();
                        sim_engine.needs_field_update = false;
                    }

                    std::vector<uint8_t> body;
                    sim_engine.get_state_binary(body);

                    header["n"] = body.size() / 21;

                    std::string header_str = header.dump();
                    uint32_t header_len = (uint32_t)header_str.size();

                    std::string packet;
                    packet.reserve(4 + header_len + body.size());
                    packet.append(reinterpret_cast<const char*>(&header_len), 4);
                    packet.append(header_str);
                    packet.append(reinterpret_cast<const char*>(body.data()), body.size());

                    static int broadcast_log = 0;
                    if (++broadcast_log <= 10) {
                        std::cout << "[Broadcast #" << broadcast_log << "] " << body.size() / 21 << " particles, "
                                  << packet.size() << " bytes, conns=" << active_connections.size() << std::endl;
                    }

                    broadcast_data(packet);
                }

                frame_count++;

                // 5. Sleep to maintain FPS
                auto target_time = frame_start + std::chrono::milliseconds(1000 / fps);
                std::this_thread::sleep_until(target_time);
            }
        } catch (const std::exception& e) {
            std::cerr << "[sim_thread Error] " << e.what() << std::endl << std::flush;
        } catch (...) {
            std::cerr << "[sim_thread Error] Unknown exception" << std::endl << std::flush;
        }
    });

    // Setup Crow App
    crow::SimpleApp app;

    // IMPORTANT: WebSocket route MUST be registered BEFORE the catch-all <path> route
    CROW_WEBSOCKET_ROUTE(app, "/ws")
        .onopen([&](crow::websocket::connection& conn) {
            std::cout << "WebSocket Connected" << std::endl;
            {
                std::lock_guard<std::mutex> lock(connections_mutex);
                active_connections.insert(&conn);
            }
            json msg;
            msg["type"] = "init_config";
            {
                std::unique_lock<std::mutex> lock(state_mutex);
                msg["config"] = global_state;
            }
            conn.send_text(msg.dump());
        })
        .onclose([&](crow::websocket::connection& conn, const std::string& reason) {
            std::cout << "WebSocket Disconnected" << std::endl;
            std::lock_guard<std::mutex> lock(connections_mutex);
            active_connections.erase(&conn);
        })
        .onmessage([&](crow::websocket::connection& conn, const std::string& data, bool is_binary) {
            try {
                auto msg = json::parse(data);
                std::string type = msg.value("type", "");
                bool config_changed = false;

                std::unique_lock<std::mutex> lock(state_mutex);

                if (type == "set_max_range") {
                        double val = msg["value"].get<double>();
                        if (val > 90.0) val = 90.0;
                        if (val < 5.0) val = 5.0;
                        global_state["max_range"] = val;
                        sim_engine.set_max_range(global_state["max_range"]);
                        sim_engine.respawn_all();
                        config_changed = true;
                } else if (type == "set_kp") {
                        double val = msg["value"].get<double>();
                        if (val < 0.0) val = 0.0;
                        if (val > 9.0) val = 9.0;
                        global_state["kp"] = val;
                        double comp = 1.0 + val / 9.0;
                        global_state["solar_wind_compression"] = comp;
                        sim_engine.set_solar_activity(val);
                        last_kp = val;
                } else if (type == "set_compression") {
                        double val = msg["value"].get<double>();
                        if (val < 1.0) val = 1.0;
                        if (val > 2.2) val = 2.2;
                        global_state["solar_wind_compression"] = val;
                        sim_engine.set_compression(val);
                } else if (type == "set_auto_fetch_solar") {
                        bool val = msg["value"].get<bool>();
                        global_state["auto_fetch_solar"] = val;
                        if (val) {
                            last_kp = global_state["kp"];
                            sim_engine.set_solar_activity(last_kp);
                        }
                        config_changed = true;
                } else if (type == "set_particle_count") {
                    global_state["particle_count"] = msg["value"].get<int>();
                    sim_engine.set_particle_count(global_state["particle_count"]);
                    config_changed = true;
                } else if (type == "set_day") {
                    global_state["day"] = msg["value"].get<double>();
                    sim_engine.set_day_of_year(global_state["day"]);
                    config_changed = true;
                } else if (type == "set_mag_model") {
                    global_state["mag_model"] = msg["value"].get<int>();
                    config_changed = true;
                } else if (type == "set_tail_model") {
                    global_state["tail_model"] = msg["value"].get<int>();
                    config_changed = true;
                } else if (type == "set_magnetopause_model") {
                    global_state["magnetopause_model"] = msg["value"].get<int>();
                    config_changed = true;
                } else if (type == "set_imf_polarity") {
                    int pol = msg["value"].get<int>();
                    if (pol > 0) pol = 1; else pol = -1;
                    global_state["imf_polarity"] = pol;
                    // Immediately sync to Python bridge module-level variable
                    try {
                        py::gil_scoped_acquire acquire;
                        python_bridge.attr("set_imf_polarity")(pol);
                    } catch (const std::exception& e) {
                        std::cerr << "[IMF] Failed to sync polarity: " << e.what() << std::endl;
                    }
                    config_changed = true;
                } else if (type == "set_parker_angle") {
                    bool enabled = msg.value("enabled", false);
                    double angle_deg = msg.value("angle_deg", 40.0);
                    global_state["parker_custom"] = enabled;
                    global_state["parker_angle"] = angle_deg;
                    try {
                        py::gil_scoped_acquire acquire;
                        python_bridge.attr("set_parker_params")(enabled, angle_deg);
                    } catch (const std::exception& e) {
                        std::cerr << "[Parker] Failed to sync angle: " << e.what() << std::endl;
                    }
                    config_changed = true;
                } else if (type == "request_diagnostics") {
                    // Sample magnetic field at key diagnostic locations
                    try {
                        int diag_mag = global_state["mag_model"];
                        int diag_tail = global_state["tail_model"];
                        int diag_mp = global_state["magnetopause_model"];
                        double diag_kp = global_state["kp_index"];
                        py::gil_scoped_acquire acquire;
                        py::list results = python_bridge.attr("sample_diagnostics")(
                            diag_mag, diag_kp, sim_engine.b_field.total_tilt,
                            diag_tail, diag_mp
                        );
                        nlohmann::json resp;
                        resp["type"] = "diagnostics_result";
                        resp["model"] = diag_mag;
                        resp["kp"] = diag_kp;
                        resp["tail_model"] = diag_tail;
                        resp["magnetopause_model"] = diag_mp;
                        nlohmann::json pts = nlohmann::json::array();
                        for (auto& item : results) {
                            nlohmann::json pt;
                            py::dict d = item.cast<py::dict>();
                            for (auto& kv : d) {
                                std::string key = kv.first.cast<std::string>();
                                auto& val = kv.second;
                                if (py::isinstance<py::int_>(val)) pt[key] = val.cast<int>();
                                else if (py::isinstance<py::float_>(val)) {
                                    double dv = val.cast<double>();
                                    if (std::isnan(dv)) pt[key] = nullptr;
                                    else pt[key] = dv;
                                } else if (val.is_none()) {
                                    pt[key] = nullptr;
                                } else {
                                    pt[key] = val.cast<std::string>();
                                }
                            }
                            pts.push_back(pt);
                        }
                        resp["points"] = pts;
                        conn.send_text(resp.dump());
                    } catch (const std::exception& e) {
                        std::cerr << "[Diag] Error: " << e.what() << std::endl;
                        conn.send_text(R"({"type":"diagnostics_result","error":")" + std::string(e.what()) + R"("})");
                    }
                } else if (type == "set_model_prec") {
                    global_state["model_prec"] = msg["value"].get<int>();
                    sim_engine.set_model_precision(global_state["model_prec"]);
                    config_changed = true;
                } else if (type == "set_field_prec") {
                    global_state["field_prec"] = msg["value"].get<int>();
                    sim_engine.set_field_precision(global_state["field_prec"]);
                    config_changed = true;
                } else if (type == "set_b_multiplier") {
                    global_state["b_multiplier"] = msg["value"].get<double>();
                    sim_engine.set_b_multiplier(global_state["b_multiplier"]);
                    config_changed = true;
                } else if (type == "set_spawn_radius_ratio") {
                    global_state["spawn_radius_ratio"] = msg["value"].get<double>();
                    sim_engine.set_spawn_radius_ratio(global_state["spawn_radius_ratio"]);
                    config_changed = true;
                } else if (type == "set_render_radius_ratio") {
                    global_state["render_radius_ratio"] = msg["value"].get<double>();
                    config_changed = true;
                } else if (type == "set_enable_gravity") {
                    global_state["enable_gravity"] = msg["value"].get<bool>();
                    sim_engine.enable_gravity = global_state["enable_gravity"];
                    config_changed = true;
                } else if (type == "set_gravity_multiplier") {
                    global_state["gravity_multiplier"] = msg["value"].get<double>();
                    sim_engine.gravity_multiplier = global_state["gravity_multiplier"];
                    config_changed = true;
                } else if (type == "set_enable_electric_field") {
                    global_state["enable_electric_field"] = msg["value"].get<bool>();
                    sim_engine.enable_electric_field = global_state["enable_electric_field"];
                    config_changed = true;
                } else if (type == "set_efield_model") {
                    global_state["efield_model"] = msg["value"].get<int>();
                    sim_engine.efield_model = global_state["efield_model"];
                    config_changed = true;
                } else if (type == "set_electric_field_multiplier") {
                    global_state["electric_field_multiplier"] = msg["value"].get<double>();
                    sim_engine.electric_field_multiplier = global_state["electric_field_multiplier"];
                    config_changed = true;
                } else if (type == "set_enable_atmosphere") {
                    global_state["enable_atmosphere"] = msg["value"].get<bool>();
                    sim_engine.enable_atmosphere = global_state["enable_atmosphere"];
                    config_changed = true;
                } else if (type == "set_atmos_model") {
                    global_state["atmos_model"] = msg["value"].get<int>();
                    sim_engine.atmos_model = global_state["atmos_model"];
                    config_changed = true;
                } else if (type == "set_atmosphere_multiplier") {
                    global_state["atmosphere_multiplier"] = msg["value"].get<double>();
                    sim_engine.atmosphere_multiplier = global_state["atmosphere_multiplier"];
                    config_changed = true;
                } else if (type == "set_emitter_params") {
                    global_state["emitter_mode"] = msg.value("mode", 0);
                    global_state["emitter_lon"] = msg.value("lon", 0.0);
                    global_state["emitter_lat"] = msg.value("lat", 0.0);
                    global_state["v_base"] = msg.value("v_base", 400.0);
                    global_state["v_random"] = msg.value("v_random", 10.0);
                    global_state["angle_random"] = msg.value("angle_random", 5.0);
                    global_state["dist_ratio"] = msg.value("dist_ratio", 1.0);
                    sim_engine.set_emitter_params(
                        global_state["emitter_mode"], global_state["emitter_lon"], global_state["emitter_lat"],
                        global_state["v_base"], global_state["v_random"], global_state["angle_random"], global_state["dist_ratio"]
                    );
                    config_changed = true;
                } else if (type == "set_particle_types") {
                    if (msg.contains("raw_types")) {
                        global_state["particle_types"] = msg["raw_types"];
                    }
                    sim_engine.clear_particle_types();
                    for (const auto& t : msg["types"]) {
                        sim_engine.add_particle_type(
                            t["q"].get<double>(), t["mass"].get<double>(), t["color"].get<int>(),
                            t.value("v_multiplier", 1.0), t.value("weight", 1.0)
                        );
                    }
                    sim_engine.respawn_all();
                    config_changed = true;
                } else if (type == "respawn_all") {
                    sim_engine.respawn_all();
                }

                if (config_changed) {
                    // Release lock before broadcasting to avoid deadlock if broadcast tries to acquire
                    lock.unlock();
                    broadcast_config(&conn);
                    lock.lock();
                }
            } catch (const std::exception& e) {
                std::cerr << "Message parse error: " << e.what() << std::endl;
            }
        });

    // ===================================================================
    // Preset API: save/load/list/delete configuration snapshots
    // ===================================================================
    static const std::string PRESET_FILE = "presets.json";
    static std::mutex preset_mutex;

    auto load_presets_map = []() -> nlohmann::json {
        std::lock_guard<std::mutex> lock(preset_mutex);
        std::ifstream f(PRESET_FILE);
        if (f) return nlohmann::json::parse(f, nullptr, false);
        return nlohmann::json::object();
    };

    auto save_presets_map = [](const nlohmann::json& map) {
        std::lock_guard<std::mutex> lock(preset_mutex);
        std::ofstream f(PRESET_FILE);
        if (f) f << map.dump(2);
    };

    CROW_ROUTE(app, "/api/preset/save").methods("POST"_method)
    ([&](const crow::request& req) {
        auto body = nlohmann::json::parse(req.body, nullptr, false);
        if (body.is_null() || !body.contains("name") || !body.contains("settings")) {
            return crow::response(400, R"({"error":"Missing name or settings"})");
        }
        std::string name = body["name"];
        auto map = load_presets_map();
        map[name] = body["settings"];
        save_presets_map(map);
        return crow::response(R"({"ok":true})");
    });

    CROW_ROUTE(app, "/api/preset/list").methods("GET"_method)
    ([&]() {
        auto map = load_presets_map();
        nlohmann::json list = nlohmann::json::array();
        for (auto& [name, _] : map.items()) list.push_back(name);
        return crow::response(list.dump());
    });

    CROW_ROUTE(app, "/api/preset/load").methods("POST"_method)
    ([&](const crow::request& req) {
        auto body = nlohmann::json::parse(req.body, nullptr, false);
        std::string name = body.value("name", "");
        auto map = load_presets_map();
        if (!map.contains(name))
            return crow::response(404, R"({"error":"Preset not found"})");
        return crow::response(map[name].dump());
    });

    CROW_ROUTE(app, "/api/preset/delete").methods("POST"_method)
    ([&](const crow::request& req) {
        auto body = nlohmann::json::parse(req.body, nullptr, false);
        std::string name = body.value("name", "");
        auto map = load_presets_map();
        if (!map.contains(name))
            return crow::response(404, R"({"error":"Preset not found"})");
        map.erase(name);
        save_presets_map(map);
        return crow::response(R"({"ok":true})");
    });

    // Static file routes AFTER WebSocket to avoid catch-all interception
    CROW_ROUTE(app, "/")([]() {
        std::ifstream file("static/index.html");
        if (file) {
            std::ostringstream ss;
            ss << file.rdbuf();
            return crow::response(ss.str());
        }
        return crow::response(404);
    });

    CROW_ROUTE(app, "/<path>")([](std::string path) {
        std::ifstream file("static/" + path);
        if (file) {
            std::ostringstream ss;
            ss << file.rdbuf();
            return crow::response(ss.str());
        }
        return crow::response(404);
    });

    try {
        py::gil_scoped_release release;
        app.bindaddr(host).port(port).run();
    } catch (const std::exception& e) {
        std::cerr << "Crow run exception: " << e.what() << std::endl;
    }

    running = false;
    {
        std::lock_guard<std::mutex> lock(grid_job_mutex);
        grid_worker_running = false;
    }
    grid_job_cv.notify_all();
    if (sim_thread.joinable()) {
        sim_thread.join();
    }
    if (grid_thread.joinable()) {
        grid_thread.join();
    }
    std::cout << "DEBUG: Server exiting cleanly" << std::endl;
    return 0;
}
