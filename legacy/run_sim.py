import os
import subprocess
import sys
import platform

def print_step(msg):
    print(f"\n[{'='*40}]\n>>> {msg}\n[{'='*40}]")

def check_python_version():
    print_step("Checking Python Version")
    if sys.version_info < (3, 10):
        print("❌ Error: Python 3.10 or higher is required.")
        sys.exit(1)
    print(f"✅ Python version {sys.version_info.major}.{sys.version_info.minor} detected.")

def install_dependencies():
    print_step("Installing Python Dependencies")
    deps = [
        "setuptools",
        "fastapi",
        "uvicorn",
        "numpy",
        "requests",
        "pybind11",
        "geopack"
    ]
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
        subprocess.check_call([sys.executable, "-m", "pip", "install"] + deps)
        print("✅ Dependencies installed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"❌ Error installing dependencies: {e}")
        sys.exit(1)

def build_cpp_extension():
    print_step("Building C++ Physics Extension")
    try:
        subprocess.check_call([sys.executable, "setup.py", "build_ext", "--inplace"])
        print("✅ C++ extension built successfully.")
    except subprocess.CalledProcessError as e:
        print("❌ Error building C++ extension.")
        print("Please ensure you have a C++ compiler installed.")
        if platform.system() == "Windows":
            print("For Windows: Install 'Desktop development with C++' via Visual Studio Installer.")
        elif platform.system() == "Darwin":
            print("For macOS: Run 'xcode-select --install'")
        else:
            print("For Linux: Run 'sudo apt-get install build-essential python3-dev'")
        sys.exit(1)

def start_server():
    print_step("Starting Server")
    print("🚀 The simulation server will start on http://127.0.0.1:8001")
    print("Press Ctrl+C to stop the server.\n")
    try:
        subprocess.check_call([sys.executable, "-m", "uvicorn", "main:app", "--port", "8001", "--reload"])
    except KeyboardInterrupt:
        print("\nServer stopped.")
    except subprocess.CalledProcessError as e:
        print(f"❌ Error starting server: {e}")

if __name__ == "__main__":
    # Ensure we are in the same directory as this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    print("""
    🌍 Earth Magnetic Field & Particle Simulation 🌍
    =================================================
    This script will:
    1. Check your Python environment.
    2. Install necessary Python packages.
    3. Compile the C++ physics engine using pybind11.
    4. Start the FastAPI web server.
    """)
    
    check_python_version()
    install_dependencies()
    build_cpp_extension()
    start_server()