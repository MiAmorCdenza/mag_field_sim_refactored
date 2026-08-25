#!/usr/bin/env python3
"""SSH into SWMF machine and explore output files."""
import paramiko

HOST = '192.168.134.128'
USER = 'rivatuna'
PASS = '070523'

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASS, timeout=10)

def run(cmd):
    stdin, stdout, stderr = client.exec_command(cmd)
    return stdout.read().decode(), stderr.read().decode()

print("=" * 60)
print(f"Connected to {HOST}")
out, _ = run("uname -a")
print(out.strip())
out, _ = run("pwd")
print(f"Home: {out.strip()}")

# Find SWMF output
cmds = [
    ("ls SWMF/output/test1/ 2>/dev/null | head -30", "SWMF/output/test1/"),
    ("ls SWMF/ 2>/dev/null | head -10", "SWMF/"),
    ('find SWMF/output -name "*.h" -type f 2>/dev/null | head -20', "Header (*.h) files"),
    ('find SWMF/output -name "*.idl" -type f 2>/dev/null | head -5', "IDL files (first 5)"),
    ('find SWMF -name "3d_mhd*" -o -name "3d_*" 2>/dev/null | head -10', "3D outputs"),
    ('find SWMF -name "*.tree" -type f 2>/dev/null | head -5', "Tree files"),
    ("cat SWMF/output/test1/README 2>/dev/null", "README"),
]

for cmd, title in cmds:
    out, _ = run(cmd)
    print(f"\n=== {title} ===")
    if out.strip():
        print(out.strip()[:800])
    else:
        print("(none)")

# Check for active/output dirs
out, _ = run("ls -d SWMF/output/*/ 2>/dev/null | head -10")
print("\n=== Output subdirs ===")
print(out.strip() if out.strip() else "(none)")

client.close()
print("\nDone.")
