cmake_minimum_required(VERSION 3.20)
project(MagFieldSimServer CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ---- 1. Python 嵌入 ----
find_package(Python3 COMPONENTS Interpreter Development REQUIRED)
message(STATUS "Python3_EXECUTABLE: ${Python3_EXECUTABLE}")

# ---- 2. 依赖获取 ----
include(FetchContent)

FetchContent_Declare(
    pybind11
    GIT_REPOSITORY https://github.com/pybind/pybind11.git
    GIT_TAG        v3.0.0
)
FetchContent_MakeAvailable(pybind11)

# nlohmann_json(header-only,用 INTERFACE 库避免其自身 CMake 版本问题)
FetchContent_Declare(
    nlohmann_json
    URL https://github.com/nlohmann/json/releases/download/v3.11.2/json.tar.xz
)
FetchContent_Populate(nlohmann_json)
add_library(nlohmann_json INTERFACE)
target_include_directories(nlohmann_json INTERFACE ${nlohmann_json_SOURCE_DIR}/include)

# Crow + standalone Asio
FetchContent_Declare(
    asio
    URL https://github.com/chriskohlhoff/asio/archive/refs/tags/asio-1-28-2.tar.gz
)
FetchContent_MakeAvailable(asio)

FetchContent_Declare(
    Crow
    URL https://github.com/CrowCpp/Crow/releases/download/v1.2.0/Crow-1.2.0.zip
)
FetchContent_MakeAvailable(Crow)

# ---- 3. 服务器可执行文件 ----
add_executable(mf_server
    src/main.cpp
    src/bake_bridge.cpp
    src/sim_pipeline.cpp
    src/server_app.cpp
)

target_include_directories(mf_server PRIVATE
    src
    core
    ${Python3_INCLUDE_DIRS}
    ${crow_SOURCE_DIR}/include
    ${asio_SOURCE_DIR}/asio/include
)

target_compile_definitions(mf_server PRIVATE ASIO_STANDALONE)

target_link_libraries(mf_server PRIVATE
    pybind11::embed
    nlohmann_json
    ws2_32
    ${Python3_LIBRARIES}
)

if(MSVC)
    target_compile_options(mf_server PRIVATE /EHsc /bigobj /utf-8 /Zi)
    target_link_options(mf_server PRIVATE /DEBUG /MAP)
endif()
