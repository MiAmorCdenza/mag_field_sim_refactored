"""发布 v0.2.0-beta 预发布:创建 release + 上传便携 zip(幂等,可重复运行)。

从 git 凭据管理器取 token(git credential fill),只用 REST API。
用法: python tests/release_020.py [--dry]
"""
import json
import os
import subprocess
import sys

import requests

REPO = "MiAmorCdenza/mag_field_sim_refactored"
TAG = "v0.2.0-beta"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIP = os.path.join(ROOT, "dist", f"mf_server_{TAG}_win64_portable.zip")
DRY = "--dry" in sys.argv

NOTES = """## v0.2.0-beta —— 节点式架构 + 引导页 + 5 个预设(初步测试版)

解压后双击 **`启动.bat`** 即用(无需 Python/VS;Win10/11 x64)。
打开网页是**引导页**:5 张预设卡片,点一张即载入;或进「自定义 / 空预设」从零搭图。

### 本次亮点

- **节点式三域管线**:场域(Python 烘焙)/ 粒子域(C++ 原生,每帧零 Python)/
  渲染域(浏览器 JS 插件);**丢文件即新节点**(热加载)
- **引导页 + 预设自动发现**:放一个 `graphs/preset_*.json` 就多一张卡片
- **5 个预设**(每个都配同名 .md 调试指南):
  - 标准偶极子 · 单粒子(单粒子工具:磁镜捕获 + 初条件预览 + 俯仰角锥)
  - T89 磁层 · 单粒子(`mul(w=0.01)` 缩放场 → 可见回旋螺旋)
  - 复合场 · 多种群(T89 + 磁尾 + 偶极 + IMF 经磁层顶合成;电子/质子/α)
  - Van Allen 辐射带(T89)(体积随机 + c/3 动能 → 损失锥 + 磁镜捕获成带)
  - 自定义 / 空预设
- **画布必须说真话**:引擎隐式解析的东西以「虚影节点 + 虚线」摆在画布上;
  编译期诊断(无 B 表 / 槽位未解析 / 渲染项未接线 / 注入+count>1 退化…)报到界面
- **接线决定归属**:物种(种群行表)、注入、渲染数据通道都由接线决定;
  未接线即不生效并告警(不再静默)
- **顺序走参数**:粒子域 `order`、渲染域 `layer`(移除了仪式性 prev/next 链)
- **动态渲染插件示例**:俯仰角锥(`nodes/render_item_pitch_cone.py` +
  `static/renderer/items/pitch_cone.js`)

### 验收

- 默认图烘焙与老引擎在 19 个诊断点**位级一致**(max|Δ|=0.00e+00)
- 2 万粒子单步 ~0.23 ms(预算 5 ms)
- 引擎/预设/WS/追踪器测试全绿

### 已知限制

- 一个图只有第一个发射器生效(v1)
- 电子回旋周期 ~1e-4 s,`dt=0.01` 下欠采样(弹跳/漂移正确)
- Windows x64 专用

反馈请附 `logs\\server.jsonl` 末尾几行 + 你点的预设名。
"""


def token():
    p = subprocess.run(["git", "credential", "fill"],
                       input=b"protocol=https\nhost=github.com\n\n",
                       capture_output=True, check=True)
    for line in p.stdout.decode().splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1]
    raise SystemExit("未取到 GitHub token")


def main():
    assert os.path.exists(ZIP), f"缺少 zip: {ZIP}(先跑 scripts\\package.ps1)"
    size = os.path.getsize(ZIP) / 1e6
    print(f"资产: {os.path.basename(ZIP)}({size:.1f} MB)")
    if DRY:
        print("(--dry:不实际发布)"); return
    tok = token()
    h = {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"}

    r = requests.get(f"https://api.github.com/repos/{REPO}/releases/tags/{TAG}",
                     headers=h, timeout=30)
    if r.status_code == 200:
        rel = r.json()
        print(f"release 已存在: {rel['html_url']}")
    else:
        r = requests.post(f"https://api.github.com/repos/{REPO}/releases",
                          headers=h, timeout=60, json={
                              "tag_name": TAG,
                              "name": f"EarthMagFieldSim {TAG}(便携版)",
                              "body": NOTES,
                              "draft": False,
                              "prerelease": True,
                          })
        r.raise_for_status()
        rel = r.json()
        print(f"release 已创建: {rel['html_url']}")

    # 同名资产先删后传(可重复运行)
    for a in rel.get("assets", []):
        if a["name"] == os.path.basename(ZIP):
            requests.delete(f"https://api.github.com/repos/{REPO}/releases/assets/{a['id']}",
                            headers=h, timeout=30)
            print("  旧资产已删除")
    up = rel["upload_url"].split("{")[0]
    with open(ZIP, "rb") as f:
        r = requests.post(f"{up}?name={os.path.basename(ZIP)}",
                          headers={**h, "Content-Type": "application/zip"},
                          data=f, timeout=900)
    r.raise_for_status()
    print("  资产已上传:", r.json()["browser_download_url"])
    print(f"\n下载页: {rel['html_url']}")


if __name__ == "__main__":
    main()
