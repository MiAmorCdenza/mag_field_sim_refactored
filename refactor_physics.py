import re

with open("physics_engine.cpp", "r", encoding="utf-8") as f:
    code = f.read()

# Replace pybind headers with json
code = code.replace("#include <pybind11/embed.h>", "#include <nlohmann/json.hpp>")
code = code.replace("#include <pybind11/stl.h>", "")
code = code.replace("namespace py = pybind11;", "")

# Replace get_state
def repl_get_state(m):
    inner = m.group(1)
    inner = inner.replace("py::list state;", "nlohmann::json state = nlohmann::json::array();")
    inner = inner.replace("py::dict p_dict;", "nlohmann::json p_dict = nlohmann::json::object();")
    
    # Fix the pos and vel list appends
    inner = re.sub(r"py::list pos_list;\s*pos_list\.append\((.*?)\);\s*pos_list\.append\((.*?)\);\s*pos_list\.append\((.*?)\);\s*p_dict\[\"pos\"\] = pos_list;",
                   r'p_dict["pos"] = {\1, \2, \3};', inner, flags=re.DOTALL)
    
    inner = re.sub(r"py::list vel_list;\s*vel_list\.append\((.*?)\);\s*vel_list\.append\((.*?)\);\s*vel_list\.append\((.*?)\);\s*p_dict\[\"vel\"\] = vel_list;",
                   r'p_dict["vel"] = {\1, \2, \3};', inner, flags=re.DOTALL)
                   
    inner = inner.replace("state.append(p_dict);", "state.push_back(p_dict);")
    return "nlohmann::json get_state() {" + inner + "}"

code = re.sub(r"py::list get_state\(\)\s*\{(.*?return state;\s*)\}", repl_get_state, code, flags=re.DOTALL)

# Replace compute_field_lines
def repl_compute(m):
    inner = m.group(1)
    inner = inner.replace("py::list lines;", "nlohmann::json lines = nlohmann::json::array();")
    inner = inner.replace("py::list full_line;", "nlohmann::json full_line = nlohmann::json::array();")
    
    inner = re.sub(r"py::list pt;\s*pt\.append\((.*?)\);\s*pt\.append\((.*?)\);\s*pt\.append\((.*?)\);\s*full_line\.append\(pt\);",
                   r'full_line.push_back({\1, \2, \3});', inner, flags=re.DOTALL)
                   
    inner = inner.replace("lines.append(full_line);", "lines.push_back(full_line);")
    return "nlohmann::json compute_field_lines() {" + inner + "}"

code = re.sub(r"py::list compute_field_lines\(\)\s*\{(.*?return lines;\s*)\}", repl_compute, code, flags=re.DOTALL)

with open("physics_engine.cpp", "w", encoding="utf-8") as f:
    f.write(code)
print("physics_engine.cpp refactored successfully.")