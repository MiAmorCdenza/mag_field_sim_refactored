"""把便携 zip 上传为 GitHub Release 资产。"""
import json
import os
import subprocess
import sys

import requests

REPO = "MiAmorCdenza/mag_field_sim_refactored"
TAG = "v0.1.0-beta"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIP = os.path.join(ROOT, "dist", "mf_server_v0.1.0-beta_win64_portable.zip")

p = subprocess.run(["git", "credential", "fill"],
                   input=b"protocol=https\nhost=github.com\n\n",
                   capture_output=True, check=True)
tok = [l.split("=", 1)[1] for l in p.stdout.decode().splitlines()
       if l.startswith("password=")][0]
h = {"Authorization": f"Bearer {tok}",
     "Accept": "application/vnd.github+json"}

rel = requests.get(f"https://api.github.com/repos/{REPO}/releases/tags/{TAG}",
                   headers=h, timeout=30)
if rel.status_code != 200:
    print("取 release 失败:", rel.status_code, rel.text[:200], file=sys.stderr)
    sys.exit(1)
rid = rel.json()["id"]

name = os.path.basename(ZIP)
with open(ZIP, "rb") as f:
    data = f.read()
r = requests.post(
    f"https://uploads.github.com/repos/{REPO}/releases/{rid}/assets?name={name}",
    headers={**h, "Content-Type": "application/zip"},
    data=data, timeout=600)
if r.status_code in (200, 201):
    a = r.json()
    print(f"资产已上传: {a['name']} ({a['size']/1e6:.1f} MB)")
    print(f"下载: {a['browser_download_url']}")
else:
    print("上传失败:", r.status_code, r.text[:300], file=sys.stderr)
    sys.exit(1)
