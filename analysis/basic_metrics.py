"""内置粒子度量插件(#43)—— 暂停态属性查看器的默认物理量集合。

每个指标都是一个纯函数插件:新增指标 = 复制一段丢进 analysis/ 里改;
前端面板按服务器返回的目录自动成表,**不需要改前端或 C++**。

单位约定(与 C++ 快照一致):pos=Re、vel=Re/s、q=电荷数、m=amu、B=nT。
物理速度 = vel × 6371 km/s;相对论动能 = (γ−1)mc²。
"""
from __future__ import annotations

import numpy as np

from engine.analysis import register_metric, RE_KM, AMU_KG, C_KM_S, MEV_J, B_SURF_NT


def _speed_kms(vel):
    return float(np.linalg.norm(vel)) * RE_KM


def _gamma(vel):
    beta = _speed_kms(vel) / C_KM_S
    return 1.0 / np.sqrt(max(1e-12, 1.0 - beta * beta))


@register_metric("r_re", title="地心距 r", unit="Re", order=10,
                 desc="|位置|(GSM,地球半径)")
def r_re(pos, vel, q, m, B):
    return float(np.linalg.norm(pos))


@register_metric("speed_kms", title="速率", unit="km/s", order=20)
def speed_kms(pos, vel, q, m, B):
    return _speed_kms(vel)


@register_metric("gamma", title="洛伦兹因子 γ", unit="", order=30,
                 desc="1/√(1−β²);γ−1 是相对论动能占比")
def gamma(pos, vel, q, m, B):
    return float(_gamma(vel))


@register_metric("energy_mev", title="动能", unit="MeV", order=40,
                 desc="相对论动能 (γ−1)mc²(真实质量,非归一化)")
def energy_mev(pos, vel, q, m, B):
    g = _gamma(vel)
    mc2_mev = m * AMU_KG * (C_KM_S * 1000.0) ** 2 / MEV_J
    return float((g - 1.0) * mc2_mev)


@register_metric("b_nt", title="局部 |B|", unit="nT", order=50)
def b_nt(pos, vel, q, m, B):
    return float(np.linalg.norm(B))


@register_metric("pitch_deg", title="俯仰角 α", unit="°", order=60,
                 desc="速度与局部磁场的夹角;0=沿场线,90=垂直")
def pitch_deg(pos, vel, q, m, B):
    v, b = np.linalg.norm(vel), np.linalg.norm(B)
    if v < 1e-12 or b < 1e-12:
        return float("nan")
    return float(np.degrees(np.arccos(
        np.clip(np.dot(vel, B) / (v * b), -1.0, 1.0))))


@register_metric("loss_cone_deg", title="损失锥 α_loss", unit="°", order=70,
                 desc="asin√(B/B_surf):α 小于它会被沉降(偶极近似)")
def loss_cone_deg(pos, vel, q, m, B):
    b = np.linalg.norm(B)
    if b <= 0 or b >= B_SURF_NT:
        return float("nan")
    return float(np.degrees(np.arcsin(np.sqrt(b / B_SURF_NT))))


@register_metric("trapped", title="捕获判定", unit="", order=80,
                 desc="α 是否大于损失锥(捕获=沿场线来回反弹)")
def trapped(pos, vel, q, m, B):
    a = pitch_deg(pos, vel, q, m, B)
    al = loss_cone_deg(pos, vel, q, m, B)
    if not np.isfinite(a) or not np.isfinite(al):
        return "—"
    return "捕获" if a > al else "损失锥"


@register_metric("gyro_radius_re", title="回旋半径 R_g", unit="Re", order=90,
                 desc="|v|/ω_c,ω_c = |q/m|·B(相对论修正用 γ)")
def gyro_radius_re(pos, vel, q, m, B):
    b = np.linalg.norm(B)
    if b < 1e-12 or m < 1e-12:
        return float("nan")
    # ω_c[rad/s] = |q|e·B[T]/m[kg],B[nT] = 1e-9 T
    wc = abs(q) * 1.602176634e-19 * (b * 1e-9) / (m * AMU_KG)
    if wc < 1e-30:
        return float("nan")
    return float((np.linalg.norm(vel) * RE_KM * 1000.0) * _gamma(vel) / wc / (RE_KM * 1000.0))


@register_metric("gyro_period_s", title="回旋周期 T_g", unit="s", order=100)
def gyro_period_s(pos, vel, q, m, B):
    b = np.linalg.norm(B)
    if b < 1e-12 or m < 1e-12:
        return float("nan")
    wc = abs(q) * 1.602176634e-19 * (b * 1e-9) / (m * AMU_KG)
    if wc < 1e-30:
        return float("nan")
    return float(2.0 * np.pi * _gamma(vel) / wc)


@register_metric("drift_dir", title="漂移方向", unit="", order=110,
                 desc="梯度/曲率漂移符号:电荷正→西,电子→东(由 v×B 判定)")
def drift_dir(pos, vel, q, m, B):
    c = np.cross(vel, B)
    if np.linalg.norm(c) < 1e-15:
        return "—"
    return "西" if q > 0 else ("东" if q < 0 else "—")


@register_metric("mu_mev_per_nt", title="第一绝热不变量 μ", unit="MeV/nT", order=120,
                 desc="E_⊥/B,磁镜捕获的守恒量(缓变场中近似不变)")
def mu_mev_per_nt(pos, vel, q, m, B):
    b = np.linalg.norm(B)
    if b < 1e-12:
        return float("nan")
    v, bb = np.linalg.norm(vel), B / max(np.linalg.norm(B), 1e-30)
    v_perp = np.linalg.norm(vel - np.dot(vel, bb) * bb) * RE_KM  # km/s
    g = _gamma(vel)
    mc2 = m * AMU_KG * (C_KM_S * 1000.0) ** 2 / MEV_J
    e_perp = (g - 1.0) * mc2 * (v_perp / max(v, 1e-30)) ** 2     # ⊥ 部分动能
    return float(e_perp / b)


@register_metric("status_text", title="状态", unit="", order=130)
def status_text(pos, vel, q, m, B):
    return ""      # 由快照原样显示(status 字段),占位说明面板可混合"原样字段"


# ---- 球坐标:位置 (r, θ, φ) 与 速度的径向-经向-纬向分解 ----
# 约定:GSM 类坐标;θ = 与 +Z(GSM 北)的夹角(余纬);φ = XY 平面内自 +X 逆时针。

@register_metric("theta_deg", title="极角 θ", unit="°", order=11,
                 desc="与 +Z(GSM 北)的夹角(余纬);θ=90° 即赤道面")
def theta_deg(pos, vel, q, m, B):
    r = float(np.linalg.norm(pos))
    if r < 1e-12:
        return float("nan")
    return float(np.degrees(np.arccos(np.clip(pos[2] / r, -1.0, 1.0))))


@register_metric("phi_deg", title="方位角 φ", unit="°", order=12,
                 desc="XY 平面内自 +X 逆时针(0~360°)")
def phi_deg(pos, vel, q, m, B):
    return float(np.degrees(np.arctan2(pos[1], pos[0])) % 360.0)


@register_metric("lat_deg", title="纬度 λ", unit="°", order=13,
                 desc="90° − θ(偶极纬度)")
def lat_deg(pos, vel, q, m, B):
    return 90.0 - theta_deg(pos, vel, q, m, B)


@register_metric("l_shell_dipole", title="L 壳(偶极)", unit="Re", order=14,
                 desc="L = r / cos²λ(偶极近似;赤道处 L=r)")
def l_shell_dipole(pos, vel, q, m, B):
    c = np.cos(np.radians(lat_deg(pos, vel, q, m, B)))
    return float(np.linalg.norm(pos) / max(c * c, 1e-9))


def _sph_vel(pos, vel):
    """速度的球坐标分量 (v_r, v_θ, v_φ),单位 km/s(θ̂ 指向赤道为正)。"""
    r = float(np.linalg.norm(pos))
    if r < 1e-12:
        return (float("nan"),) * 3
    rho = float(np.hypot(pos[0], pos[1]))
    v_r = float(np.dot(vel, pos / r))
    if rho < 1e-12:                       # 极点:θ̂/φ̂ 退化
        return (v_r * RE_KM, float("nan"), float("nan"))
    th = np.array([pos[2] * pos[0] / (r * rho), pos[2] * pos[1] / (r * rho),
                   -rho / r])
    ph = np.array([-pos[1] / rho, pos[0] / rho, 0.0])
    return (v_r * RE_KM, float(np.dot(vel, th)) * RE_KM,
            float(np.dot(vel, ph)) * RE_KM)


@register_metric("v_rad_kms", title="速度 径向 v_r", unit="km/s", order=21,
                 desc="沿 r̂ 分量(向外为正)")
def v_rad_kms(pos, vel, q, m, B):
    return float(_sph_vel(pos, vel)[0])


@register_metric("v_theta_kms", title="速度 经向 v_θ", unit="km/s", order=22,
                 desc="沿 θ̂ 分量(指向赤道为正)")
def v_theta_kms(pos, vel, q, m, B):
    return float(_sph_vel(pos, vel)[1])


@register_metric("v_phi_kms", title="速度 纬向 v_φ", unit="km/s", order=23,
                 desc="沿 φ̂ 分量(绕 +Z 方向为正)")
def v_phi_kms(pos, vel, q, m, B):
    return float(_sph_vel(pos, vel)[2])
