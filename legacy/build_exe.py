import os
import subprocess
import sys
import shutil

def build_exe():
    print("="*50)
    print("🚀 Building MagFieldSim Executable 🚀")
    print("="*50)

    # 1. Verify we have the C++ extension built
    import glob
    pyd_files = glob.glob("physics_ext*.pyd")
    if not pyd_files:
        print("❌ Error: C++ extension (.pyd) not found!")
        print("Please run `python setup.py build_ext --inplace` first.")
        sys.exit(1)
    
    physics_pyd = pyd_files[0]
    print(f"✅ Found C++ extension: {physics_pyd}")

    # 2. Clean previous builds
    for folder in ['build', 'dist']:
        if os.path.exists(folder):
            shutil.rmtree(folder)
            print(f"🧹 Cleaned old {folder}/ directory")

    # 3. Construct PyInstaller command
    pyinstaller_cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "MagFieldSim",
        "--onedir",           # Create a directory with the exe and dlls (faster startup than onefile)
        # "--windowed",         # Temporarily commented out for debugging
        "--add-data", "static;static", # Bundle the static HTML/JS files
        "--add-binary", f"{physics_pyd};.", # Bundle the C++ extension
        "--hidden-import", "geopack",
        "--hidden-import", "geopack.t89",
        "--hidden-import", "geopack.t96",
        "--hidden-import", "geopack.t01",
        "--hidden-import", "uvicorn.logging",
        "--hidden-import", "uvicorn.loops",
        "--hidden-import", "uvicorn.loops.auto",
        "--hidden-import", "uvicorn.protocols",
        "--hidden-import", "uvicorn.protocols.http",
        "--hidden-import", "uvicorn.protocols.http.auto",
        "--hidden-import", "uvicorn.protocols.websockets",
        "--hidden-import", "uvicorn.protocols.websockets.auto",
        "--hidden-import", "uvicorn.lifespan",
        "--hidden-import", "uvicorn.lifespan.on",
        "--collect-data", "geopack",   # Make sure geopack's data files (like igrf_coeffs) are included
        "main.py"
    ]

    # 4. Run PyInstaller
    print("\n📦 Running PyInstaller... This may take a minute or two.")
    try:
        # Since --windowed hides the console, we need a small wrapper to actually launch it and open the browser
        create_launcher()
        subprocess.check_call(pyinstaller_cmd)
        
        # Build the launcher
        print("\n📦 Building launcher...")
        subprocess.check_call([
            sys.executable, "-m", "PyInstaller",
            "--name", "Run_MagFieldSim",
            "--onefile",
            "--console",
            "launcher.py"
        ])
        
        # Move launcher to the main dist folder
        shutil.copy("dist/Run_MagFieldSim.exe", "dist/MagFieldSim/Run_MagFieldSim.exe")
        
        print("\n" + "="*50)
        print("🎉 Build Complete! 🎉")
        print("="*50)
        print(f"Your standalone application is ready in: {os.path.abspath('dist/MagFieldSim')}")
        print("You can zip this entire 'MagFieldSim' folder and send it to any Windows PC.")
        print("To start the app, double-click: Run_MagFieldSim.exe")
        
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Build failed with error code: {e.returncode}")

def create_launcher():
    # Create a small script that opens the console, starts the hidden server, and opens the browser
    content = """import os
import sys
import subprocess
import webbrowser
import time

print("="*50)
print("🌍 Earth Magnetic Field & Particle Simulation")
print("="*50)
print("Starting simulation server...")

# Find the hidden server executable
server_exe = os.path.join(os.path.dirname(sys.executable), "MagFieldSim.exe")
if not os.path.exists(server_exe):
    server_exe = os.path.join(os.path.dirname(os.path.abspath(__file__)), "MagFieldSim.exe")

try:
    # Start the server process
    server_process = subprocess.Popen([server_exe])
    
    print("Waiting for server to initialize...")
    time.sleep(2)  # Give uvicorn a moment to start
    
    url = "http://127.0.0.1:8001"
    print(f"Opening browser at {url} ...")
    webbrowser.open(url)
    
    print("\\n✅ Server is running in the background.")
    print("Do not close this window until you are done.")
    print("Press Ctrl+C or close this window to exit the simulation.")
    
    # Wait for user to terminate
    server_process.wait()
except KeyboardInterrupt:
    print("\\nShutting down server...")
    server_process.terminate()
except Exception as e:
    print(f"\\n❌ Error: {e}")
    input("Press Enter to exit...")
"""
    with open("launcher.py", "w", encoding="utf-8") as f:
        f.write(content)

if __name__ == "__main__":
    build_exe()