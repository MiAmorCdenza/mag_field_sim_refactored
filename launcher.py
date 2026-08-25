import os
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
    
    print("\n✅ Server is running in the background.")
    print("Do not close this window until you are done.")
    print("Press Ctrl+C or close this window to exit the simulation.")
    
    # Wait for user to terminate
    server_process.wait()
except KeyboardInterrupt:
    print("\nShutting down server...")
    server_process.terminate()
except Exception as e:
    print(f"\n❌ Error: {e}")
    input("Press Enter to exit...")
