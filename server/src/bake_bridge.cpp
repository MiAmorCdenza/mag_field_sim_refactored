// bake_bridge 实现:pybind11 嵌入,接口保持 C++ 类型纯净。
#include "bake_bridge.h"

#include <pybind11/embed.h>
#include <pybind11/stl.h>
namespace py = pybind11;

struct BakeBridge::Impl {
    py::scoped_interpreter guard;
    std::unique_ptr<py::gil_scoped_release> release;  // 主线程释放 GIL
    py::object graph;
};

BakeBridge::BakeBridge() = default;
BakeBridge::~BakeBridge() = default;

bool BakeBridge::init(const std::string& root, std::string& err) {
    try {
        impl_ = std::make_unique<Impl>();
        auto sys = py::module_::import("sys");
        sys.attr("path").attr("insert")(0, root);
        auto engine = py::module_::import("engine");
        auto reg = engine.attr("default_registry")();
        impl_->graph = engine.attr("Graph")(reg, py::none());
        // 预热导入:工作线程内的首次包导入在嵌入式场景下不稳定
        py::module_::import("numpy");
        py::module_::import("geopack.t89");
        py::module_::import("geopack.t96");
        py::module_::import("geopack.t01");
        py::module_::import("geopack.t04");
        return true;
    } catch (const std::exception& e) {
        err = e.what();
        return false;
    }
}

bool BakeBridge::release_main_thread() {
    if (!impl_) return false;
    try {
        impl_->release = std::make_unique<py::gil_scoped_release>();
        return true;
    } catch (...) {
        return false;
    }
}

bool BakeBridge::load_graph(const std::string& json, std::string& err) {
    try {
        py::gil_scoped_acquire g;
        auto json_mod = py::module_::import("json");
        auto doc = json_mod.attr("loads")(json);
        impl_->graph.attr("load_json")(doc);
        return true;
    } catch (const std::exception& e) {
        err = e.what();
        return false;
    }
}

bool BakeBridge::set_param(const std::string& node, const std::string& name,
                           double value, std::string& err) {
    return set_param_value(node, name, std::to_string(value), err);
}

bool BakeBridge::set_param_value(const std::string& node, const std::string& name,
                                 const std::string& json_value, std::string& err) {
    try {
        py::gil_scoped_acquire g;
        auto json_mod = py::module_::import("json");
        py::object v = json_mod.attr("loads")(json_value);
        impl_->graph.attr("set_param")(node, name, v);
        return true;
    } catch (const std::exception& e) {
        err = e.what();
        return false;
    }
}

uint64_t BakeBridge::graph_version() {
    py::gil_scoped_acquire g;
    return impl_->graph.attr("version").cast<uint64_t>();
}

bool BakeBridge::describe_types(std::string& out_json, std::string& err) {
    try {
        py::gil_scoped_acquire g;
        auto json_mod = py::module_::import("json");
        py::object desc = impl_->graph.attr("registry").attr("describe")();
        out_json = json_mod.attr("dumps")(desc).cast<std::string>();
        return true;
    } catch (const std::exception& e) {
        err = e.what();
        return false;
    }
}

bool BakeBridge::rescan(std::string& err) {
    try {
        py::gil_scoped_acquire g;
        impl_->graph.attr("registry").attr("scan")();
        return true;
    } catch (const std::exception& e) {
        err = e.what();
        return false;
    }
}

std::optional<BakedField> BakeBridge::bake(const std::string& slot, std::string& err) {
    try {
        py::gil_scoped_acquire g;
        py::list names;
        names.append(py::str(slot));
        py::dict result = impl_->graph.attr("bake")(names);
        if (!result.contains(py::str(slot))) {
            err = "槽位不存在: " + slot;
            return std::nullopt;
        }
        py::dict d = result[py::str(slot)].cast<py::dict>();
        BakedField f;
        f.slot = slot;
        f.xs = d["xs"].cast<std::vector<double>>();
        f.ys = d["ys"].cast<std::vector<double>>();
        f.zs = d["zs"].cast<std::vector<double>>();
        if (d.contains("bx")) {
            f.is_vector = true;
            f.c0 = d["bx"].cast<std::vector<double>>();
            f.c1 = d["by"].cast<std::vector<double>>();
            f.c2 = d["bz"].cast<std::vector<double>>();
        } else if (d.contains("scalar")) {
            f.is_vector = false;
            f.c0 = d["scalar"].cast<std::vector<double>>();
        } else {
            err = "槽位类型未知: " + slot;
            return std::nullopt;
        }
        return f;
    } catch (const std::exception& e) {
        err = e.what();
        return std::nullopt;
    }
}

bool BakeBridge::declared_outputs(std::vector<std::string>& slots, std::string& err) {
    try {
        py::gil_scoped_acquire g;
        py::object keys = impl_->graph.attr("outputs").attr("keys")();
        for (auto k : py::list(keys)) slots.push_back(k.cast<std::string>());
        return true;
    } catch (const std::exception& e) {
        err = e.what();
        return false;
    }
}

bool BakeBridge::graph_json(std::string& out_json, std::string& err) {
    try {
        py::gil_scoped_acquire g;
        auto json_mod = py::module_::import("json");
        out_json = json_mod.attr("dumps")(
            impl_->graph.attr("to_json")(), py::arg("ensure_ascii") = false
        ).cast<std::string>();
        return true;
    } catch (const std::exception& e) {
        err = e.what();
        return false;
    }
}
