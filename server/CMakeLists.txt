cmake_minimum_required(VERSION 3.20)
project(MagFieldSimServer CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ---- 1. Python 嵌入 ----
find_package(Python3 COMPONENTS Interpreter Development REQUIRED)
message(STATUS "Python3_EXECUTABLE: ${Python3_EXECUTABLE}")

# ---- 2. pybind11 ----
include(FetchContent)
FetchContent_Declare(
    pybind11
    GIT_REPOSITORY https://github.com/pybind/pybind11.git
    GIT_TAG        v3.0.0
)
FetchContent_MakeAvailable(pybind11)

# ---- 3. 服务器可执行文件 ----
add_executable(mf_server
    src/main.cpp
    src/bake_bridge.cpp
    src/sim_pipeline.cpp
)

target_include_directories(mf_server PRIVATE
    src
    core
    ${Python3_INCLUDE_DIRS}
)

target_link_libraries(mf_server PRIVATE
    pybind11::embed
    ${Python3_LIBRARIES}
)

if(MSVC)
    target_compile_options(mf_server PRIVATE /EHsc /bigobj /utf-8)
endif()
