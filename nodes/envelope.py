"""磁层顶包边与场拼接节点。

忠实移植自 legacy/python_bridge.py:
- tail_blend:     mp=0 时的 X 轴远磁尾拼接(_apply_tail_blend)
- internal_blend: 磁层顶内 Tsyganenko+尾场(包边 STEP 1)
- magnetopause:   Shue 磁层顶 + IMF/披流 + 矢量势无散度混合 + 偶极抑制
                  (mp_model: 0=legacy直通 / 1=MP+均匀IMF / 2=MP+磁鞘披流 / 3=MSH23)

MSH23(mp=3)经由子进程调用;exe 缺失或失败时按 legacy 行为回退到 mode 2。
"""
from __future__ import annotations

import os
import subprocess

import numpy as np

from engine import register_node, Node, Port, Param, Field

# 旧 MSH23 Fortran 可执行文件(legacy 归档中;robocopy 排除 *.exe 后需从原目录恢复)
_MSH23_EXE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "legacy", "msh23_model", "msh23_test.exe")


@register_node(
    type="tail_blend",
    name="远磁尾拼接(直通模式)", category="磁场/拼接", icon="🧵",
    inputs={"base": Port("vector_field"),
            "tail": Port("vector_field", default=None),
            "kp": Port("scalar", default=2.0, min=0.0, max=9.0),
            "ps": Port("scalar", default=0.0)},
    outputs={"field": "vector_field"},
)
class TailBlendNode(Node):
    """legacy _apply_tail_blend:mp=0 时的沿 X 轴 sigmoid 拼接(含无散度 bz 修正)。"""

    def compute(self, base, tail, kp, ps):
        if tail is None:
            return {"field": base}
        X, Y, Z = self.lattice.mesh()
        B00 = 30.0 + kp * 5.0
        L0 = 1.5
        bx_b, by_b, bz_b = base.data[..., 0], base.data[..., 1], base.data[..., 2]
        bx_t, by_t, bz_t = tail.data[..., 0], tail.data[..., 1], tail.data[..., 2]

        x_trans = -20.0
        width = 2.5
        w = 1.0 / (1.0 + np.exp((X - x_trans) / width))
        dw_dx = -w * (1.0 - w) / width

        bx = (1.0 - w) * bx_b + w * bx_t
        by = (1.0 - w) * by_b + w * by_t
        bz_corr = -dw_dx * (B00 * L0 * np.log(np.cosh(Z / L0)) - Z * bx_b)
        bz = (1.0 - w) * bz_b + w * bz_t + bz_corr * 0.1
        return {"field": Field.vector(bx, by, bz, self.lattice)}


@register_node(
    type="internal_blend",
    name="内部场拼接(磁层顶内)", category="磁场/拼接", icon="🧩",
    inputs={"base": Port("vector_field"),
            "tail": Port("vector_field", default=None),
            "kp": Port("scalar", default=2.0, min=0.0, max=9.0),
            "ps": Port("scalar", default=0.0)},
    outputs={"field": "vector_field"},
)
class InternalBlendNode(Node):
    """磁层顶内:Tsyganenko + 远磁尾,含铰接修正的无散度拼接(包边 STEP 1)。"""

    def compute(self, base, tail, kp, ps):
        if tail is None:
            return {"field": base}
        X, Y, Z = self.lattice.mesh()
        B00 = 30.0 + kp * 5.0
        L0 = 1.5
        bx_b, by_b, bz_b = base.data[..., 0], base.data[..., 1], base.data[..., 2]
        bx_t, by_t, bz_t = tail.data[..., 0], tail.data[..., 1], tail.data[..., 2]

        x_trans = -20.0
        width = 3.0
        w = 1.0 / (1.0 + np.exp((X - x_trans) / width))
        dw_dx = -w * (1.0 - w) / width

        hinged_z = Z - 0.5 * np.tan(ps) * (X + 10.0 - np.sqrt((X + 10.0) ** 2 + 16.0))
        bz_corr = -dw_dx * (B00 * L0 * np.log(np.cosh(hinged_z / L0)) - Z * bx_b)

        bx = (1.0 - w) * bx_b + w * bx_t
        by = (1.0 - w) * by_b + w * by_t
        bz = (1.0 - w) * bz_b + w * bz_t + bz_corr * 0.1
        return {"field": Field.vector(bx, by, bz, self.lattice)}


@register_node(
    type="magnetopause",
    name="磁层顶包边", category="磁场/磁层顶", icon="🛡",
    inputs={"internal": Port("vector_field"),
            "dipole": Port("vector_field", default=None),
            "imf": Port("vector_field", default=None),
            "kp": Port("scalar", default=2.0, min=0.0, max=9.0),
            "ps": Port("scalar", default=0.0)},
    outputs={"field": "vector_field"},
    params={"mp_model": Param("int", default=0)},
)
class MagnetopauseNode(Node):
    def compute(self, internal, dipole, imf, kp, ps):
        mp_model = int(self.params["mp_model"])
        if mp_model == 0:
            return {"field": internal}

        lat = self.lattice
        X, Y, Z = lat.mesh()
        bx_in, by_in, bz_in = internal.data[..., 0], internal.data[..., 1], internal.data[..., 2]

        r = np.sqrt(X ** 2 + Y ** 2 + Z ** 2)
        safe_r = np.where(r < 0.1, 0.1, r)
        cos_theta = np.clip(X / safe_r, -0.9999, 0.9999)

        # Shue (1998) 磁层顶
        pdyn = 2.0 + kp * 0.5
        r0 = 10.0 / pdyn ** (1.0 / 3.0)
        alpha = 0.55 + kp * 0.02
        r_mp = r0 * (2.0 / (1.0 + cos_theta)) ** alpha

        # ============ mp=3: MSH23 磁鞘(失败即回退 mode 2) ============
        if mp_model == 3 and os.path.exists(_MSH23_EXE):
            try:
                return self._msh23(X, Y, Z, internal, dipole, imf, kp, ps,
                                   safe_r, r_mp, pdyn, r0)
            except Exception as exc:
                print(f"[magnetopause] MSH23 失败,回退 mode 2: {exc}", flush=True)
                mp_model = 2  # fall through

        # ============ mp=1/2:解析包边 ============
        d_out = safe_r - r_mp
        blend_mp_width = 4.0
        w_out = 1.0 / (1.0 + np.exp(-d_out / blend_mp_width))

        # 外部场:IMF(可无)+ 日侧披流(mode 2)
        if imf is None:
            bx_ext = np.zeros_like(X)
            by_ext = np.zeros_like(Y)
            bz_ext = np.zeros_like(Z)
        else:
            bx_ext = imf.data[..., 0].copy()
            by_ext = imf.data[..., 1].copy()
            bz_ext = imf.data[..., 2].copy()

        if mp_model == 2:
            day_mask = X > -10.0
            if np.any(day_mask):
                r_mp_ext = r_mp[day_mask]
                r_ext = safe_r[day_mask]
                compress = 3.5 * (r_mp_ext / r_ext) ** 2
                compress = np.clip(compress, 1.0, 5.0)
                x_e, y_e, z_e = X[day_mask], Y[day_mask], Z[day_mask]
                r3, r5 = r_ext ** 3, r_ext ** 5

                bx_i = bx_ext[day_mask]
                by_i = by_ext[day_mask]
                bz_i = bz_ext[day_mask]
                M_x = -bx_i * (r_mp_ext ** 3) / 2.0
                M_y = -by_i * (r_mp_ext ** 3) / 2.0
                M_z = -bz_i * (r_mp_ext ** 3) / 2.0
                M_dot_r = M_x * x_e + M_y * y_e + M_z * z_e

                bx_draping = 3.0 * M_dot_r * x_e / r5 - M_x / r3
                by_draping = 3.0 * M_dot_r * y_e / r5 - M_y / r3
                bz_draping = 3.0 * M_dot_r * z_e / r5 - M_z / r3

                bx_dd = bx_i * compress + bx_draping * compress
                by_dd = by_i * compress + by_draping * compress
                bz_dd = bz_i * compress + bz_draping * compress

                w_drape = 1.0 / (1.0 + np.exp(-(x_e - (-5.0)) / 2.0))
                bx_ext[day_mask] = w_drape * bx_dd + (1.0 - w_drape) * bx_i
                by_ext[day_mask] = w_drape * by_dd + (1.0 - w_drape) * by_i
                bz_ext[day_mask] = w_drape * bz_dd + (1.0 - w_drape) * bz_i

        # 矢量势无散度混合修正(legacy STEP 3)
        dw_dr = w_out * (1.0 - w_out) / blend_mp_width
        nx, ny, nz = X / safe_r, Y / safe_r, Z / safe_r
        grad_w_x = dw_dr * nx
        grad_w_y = dw_dr * ny
        grad_w_z = dw_dr * nz

        dbx = bx_ext - bx_in
        dby = by_ext - by_in
        dbz = bz_ext - bz_in

        dAx = 0.5 * (dby * Z - dbz * Y)
        dAy = 0.5 * (dbz * X - dbx * Z)
        dAz = 0.5 * (dbx * Y - dby * X)

        corr_bx = grad_w_y * dAz - grad_w_z * dAy
        corr_by = grad_w_z * dAx - grad_w_x * dAz
        corr_bz = grad_w_x * dAy - grad_w_y * dAx
        corr_scale = np.clip(safe_r / 10.0, 0.0, 1.0)

        bx = (1.0 - w_out) * bx_in + w_out * bx_ext + corr_bx * corr_scale
        by = (1.0 - w_out) * by_in + w_out * by_ext + corr_by * corr_scale
        bz = (1.0 - w_out) * bz_in + w_out * bz_ext + corr_bz * corr_scale

        # 偶极场仅在磁层顶内(legacy 尾部逻辑)
        if dipole is not None:
            w_dipole_out = 1.0 / (1.0 + np.exp(-d_out / 1.5))
            suppress = 1.0 - w_dipole_out
            bx = bx + suppress * dipole.data[..., 0]
            by = by + suppress * dipole.data[..., 1]
            bz = bz + suppress * dipole.data[..., 2]

        return {"field": Field.vector(bx, by, bz, lat)}

    # ------------------------------------------------------------------
    def _msh23(self, X, Y, Z, internal, dipole, imf, kp, ps,
               safe_r, r_mp, pdyn, r0):
        """legacy MSH23 子进程路径(mp=3)。"""
        lat = self.lattice
        bx_in, by_in, bz_in = internal.data[..., 0], internal.data[..., 1], internal.data[..., 2]
        if imf is None:
            bx_i = by_i = bz_i = np.zeros_like(X)
        else:
            bx_i = imf.data[..., 0]
            by_i = imf.data[..., 1]
            bz_i = imf.data[..., 2]

        Xf, Yf, Zf = X.ravel(), Y.ravel(), Z.ravel()
        n = Xf.size
        lines = [f"{Xf[i]:.4f} {Yf[i]:.4f} {Zf[i]:.4f} {ps:.6f} {pdyn:.4f} "
                 f"{bx_i.ravel()[i]:.4f} {by_i.ravel()[i]:.4f} {bz_i.ravel()[i]:.4f}"
                 for i in range(n)]
        p = subprocess.run([_MSH23_EXE], input="\n".join(lines),
                           capture_output=True, text=True, timeout=120)
        out_lines = p.stdout.strip().split("\n")
        bx_msh = np.zeros(n)
        by_msh = np.zeros(n)
        bz_msh = np.zeros(n)
        ids = np.zeros(n, dtype=np.int32)
        for i, line in enumerate(out_lines):
            parts = line.split()
            ids[i] = int(parts[0])
            bx_msh[i] = float(parts[1])
            by_msh[i] = float(parts[2])
            bz_msh[i] = float(parts[3])
        bx_msh = bx_msh.reshape(X.shape)
        by_msh = by_msh.reshape(X.shape)
        bz_msh = bz_msh.reshape(X.shape)
        ids = ids.reshape(X.shape)

        d_out_local = safe_r - r_mp
        is_msh = ids == 0
        is_sw = ids == 1
        bx_out = np.where(is_msh, bx_msh, np.where(is_sw, bx_i, bx_in))
        by_out = np.where(is_msh, by_msh, np.where(is_sw, by_i, by_in))
        bz_out = np.where(is_msh, bz_msh, np.where(is_sw, bz_i, bz_in))
        return {"field": Field.vector(bx_out, by_out, bz_out, lat)}
