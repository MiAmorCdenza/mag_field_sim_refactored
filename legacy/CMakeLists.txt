cmake_minimum_required(VERSION 3.20)
# Allow compatibility with older CMake versions used by third-party libraries
if(POLICY CMP0135)
  cmake_policy(SET CMP0135 NEW)
endif()
set(CMAKE_POLICY_VERSION_MINIMUM 3.1)
project(MagFieldSim CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ---------------------------------------------------------
# 1. Python Embedding Setup
# ---------------------------------------------------------
find_package(Python3 COMPONENTS Interpreter Development REQUIRED)
message(STATUS "Found Python3: ${Python3_FOUND}")
message(STATUS "Python3_INCLUDE_DIRS: ${Python3_INCLUDE_DIRS}")
message(STATUS "Python3_LIBRARIES: ${Python3_LIBRARIES}")

# ---------------------------------------------------------
# 2. Fetch dependencies automatically
# ---------------------------------------------------------
include(FetchContent)

# pybind11 (for embedding python)
FetchContent_Declare(
    pybind11
    GIT_REPOSITORY https://github.com/pybind/pybind11.git
    GIT_TAG        v2.11.1
)
FetchContent_MakeAvailable(pybind11)

# nlohmann_json (for parsing websocket JSON)
# We can just use it as an INTERFACE library since it's header-only, 
# to avoid CMake version issues in its own CMakeLists.txt
FetchContent_Declare(
    nlohmann_json
    URL https://github.com/nlohmann/json/releases/download/v3.11.2/json.tar.xz
)
FetchContent_Populate(nlohmann_json)
add_library(nlohmann_json INTERFACE)
target_include_directories(nlohmann_json INTERFACE ${nlohmann_json_SOURCE_DIR}/include)

# Wait, I will use mongoose or simply crow for C++ WebSockets.
# Let's use Crow. Crow actually requires ASIO to compile!
# So we DO need Asio. Let's fetch standalone Asio (without Boost) to avoid the Boost download issues.
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

# ---------------------------------------------------------
# 3. Main Executable
# ---------------------------------------------------------
add_executable(MagFieldSim_Server
    server_main.cpp
    physics_engine.cpp
)

target_include_directories(MagFieldSim_Server PRIVATE
    ${Python3_INCLUDE_DIRS}
    ${pybind11_INCLUDE_DIRS}
    ${crow_SOURCE_DIR}/include
    ${asio_SOURCE_DIR}/asio/include
)

target_compile_definitions(MagFieldSim_Server PRIVATE ASIO_STANDALONE)

target_link_libraries(MagFieldSim_Server PRIVATE
    pybind11::embed
    nlohmann_json
    ws2_32  # Required for Crow on Windows
    ${Python3_LIBRARIES}
)

if(MSVC)
    target_compile_options(MagFieldSim_Server PRIVATE /EHsc /bigobj)
endif()
