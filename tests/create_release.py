"""创建 GitHub Release(beta):tag 已推送,这里仅调 REST API。"""
import json
import os
import subprocess
import sys

import requests

REPO = "MiAmorCdenza/mag_field_sim_refactored"
TAG = "v0.1.0-beta"

# 从 git 凭据管理器取 token
p = subprocess.run(
    ["git", "credential", "fill"],
    input=b"protocol=https\nhost=github.com\n\n",
    capture_output=True, check=True)
cred = {}
for line in p.stdout.decode().splitlines():
    if "=" in line:
        k, v = line.split("=", 1)
        cred[k] = v
token = cred.get("password", "")

notes = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "logs", "release_notes.md"), encoding="utf-8").read()

r = requests.post(
    f"https://api.github.com/repos/{REPO}/releases",
    headers={"Authorization": f"Bearer {token}",
             "Accept": "application/vnd.github+json"},
    json={"tag_name": TAG,
          "name": "v0.1.0-beta · 首个公开测试版",
          "body": notes,
          "prerelease": True,
          "target_commitish": "main",
          "draft": False},
    timeout=30)

if r.status_code in (200, 201):
    d = r.json()
    print("Release 创建成功:")
    print("  tag:", d["tag_name"])
    print("  url:", d["html_url"])
    print("  prerelease:", d["prerelease"])
else:
    print("失败:", r.status_code, r.text[:400], file=sys.stderr)
    sys.exit(1)
