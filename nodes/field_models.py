"""场模型节点:偶极子 + Tsyganenko 外部模型(T89/T96/T01/T04/TS05/TA16)。

数学忠实移植自 legacy/python_bridge.py 的 _compute_dipole 与 _compute_external。
geopack/Fortran 扩展均延迟导入:引擎与其它节点不依赖这些包。
"""
from __future__ import annotations

import numpy as np

from engine import register_node, Node, Port, Field, GraphError


def _mesh(self):
    return self.lattice.mesh()


@register_node(
    type="dipole",
    name="倾斜偶极子", category="磁场/内部场", icon="🧲",
    inputs={"ps": Port("scalar", default=0.0)},
    outputs={"field": "vector_field"},
)
class DipoleNode(Node):
    """随倾角 ps 转动的纯偶极场(31200 nT 表面强度)。"""

    def compute(self, ps):
        X, Y, Z = self.lattice.mesh()
        mx = -np.sin(ps) * 31200.0
        my = 0.0
        mz = -np.cos(ps) * 31200.0
        r2 = X ** 2 + Y ** 2 + Z ** 2
        r = np.sqrt(r2)
        r = np.where(r < 0.1, 0.1, r)
        m_dot_r = mx * X + my * Y + mz * Z
        r5 = r ** 5
        r3 = r ** 3
        bx = 3.0 * m_dot_r * X / r5 - mx / r3
        by = 3.0 * m_dot_r * Y / r5 - my / r3
        bz = 3.0 * m_dot_r * Z / r5 - mz / r3
        return {"field": Field.vector(bx, by, bz, self.lattice)}


def _external_vectorize(fn):
    return np.vectorize(fn)


@register_node(
    type="t89",
    name="T89 (1989)", category="磁场/外部模型", icon="🌐", cost="expensive",
    inputs={"kp": Port("scalar", default=2.0, min=0.0, max=9.0),
            "ps": Port("scalar", default=0.0)},
    outputs={"field": "vector_field"},
)
class T89Node(Node):
    def compute(self, kp, ps):
        import geopack.t89 as _t89
        X, Y, Z = self.lattice.mesh()
        iopt = int(kp) + 1
        iopt = max(1, min(7, iopt))
        v = _external_vectorize(lambda x, y, z: _t89.t89(iopt, ps, x, y, z))
        bx, by, bz = v(X, Y, Z)
        return {"field": Field.vector(bx, by, bz, self.lattice)}


def _common_parmod(kp):
    """T96/T01/T04/TS05 共用的太阳风参数。"""
    pdyn = 2.0 + kp * 0.5
    dst = -10.0 * kp
    return [pdyn, dst, 0.0, -2.0 - kp, 0, 0, 0, 0, 0, 0]


def _safe(fn):
    """r<0.1 → 0,异常 → 0 的包装(与 legacy 一致)。"""

    def wrapped(x, y, z):
        if np.sqrt(x * x + y * y + z * z) < 0.1:
            return 0.0, 0.0, 0.0
        try:
            return fn(x, y, z)
        except Exception:
            return 0.0, 0.0, 0.0

    return wrapped


@register_node(
    type="t96",
    name="T96 (1996)", category="磁场/外部模型", icon="🌐", cost="expensive",
    inputs={"kp": Port("scalar", default=2.0, min=0.0, max=9.0),
            "ps": Port("scalar", default=0.0)},
    outputs={"field": "vector_field"},
)
class T96Node(Node):
    def compute(self, kp, ps):
        import geopack.t96 as _t96
        X, Y, Z = self.lattice.mesh()
        parmod = _common_parmod(kp)
        v = _external_vectorize(_safe(lambda x, y, z: _t96.t96(parmod, ps, x, y, z)))
        bx, by, bz = v(X, Y, Z)
        return {"field": Field.vector(bx, by, bz, self.lattice)}


@register_node(
    type="t01",
    name="T01 (2001)", category="磁场/外部模型", icon="🌐", cost="expensive",
    inputs={"kp": Port("scalar", default=2.0, min=0.0, max=9.0),
            "ps": Port("scalar", default=0.0)},
    outputs={"field": "vector_field"},
)
class T01Node(Node):
    """x < -15 Re 回退 T96(与 legacy 一致)。"""

    def compute(self, kp, ps):
        import geopack.t01 as _t01
        import geopack.t96 as _t96
        X, Y, Z = self.lattice.mesh()
        parmod = _common_parmod(kp)

        def fn(x, y, z):
            if x < -15.0:
                return _t96.t96(parmod, ps, x, y, z)
            return _t01.t01(parmod, ps, x, y, z)

        v = _external_vectorize(_safe(fn))
        bx, by, bz = v(X, Y, Z)
        return {"field": Field.vector(bx, by, bz, self.lattice)}


@register_node(
    type="t04",
    name="T04 (2004)", category="磁场/外部模型", icon="🌐", cost="expensive",
    inputs={"kp": Port("scalar", default=2.0, min=0.0, max=9.0),
            "ps": Port("scalar", default=0.0)},
    outputs={"field": "vector_field"},
)
class T04Node(Node):
    def compute(self, kp, ps):
        import geopack.t04 as _t04
        import geopack.t96 as _t96
        X, Y, Z = self.lattice.mesh()
        parmod = _common_parmod(kp)

        def fn(x, y, z):
            if x < -15.0:
                return _t96.t96(parmod, ps, x, y, z)
            return _t04.t04(parmod, ps, x, y, z)

        v = _external_vectorize(_safe(fn))
        bx, by, bz = v(X, Y, Z)
        return {"field": Field.vector(bx, by, bz, self.lattice)}


@register_node(
    type="ts05",
    name="TS05 (2005 · 暴时)", category="磁场/外部模型", icon="🌐", cost="expensive",
    inputs={"kp": Port("scalar", default=2.0, min=0.0, max=9.0),
            "ps": Port("scalar", default=0.0)},
    outputs={"field": "vector_field"},
)
class TS05Node(Node):
    """需要 f2py 扩展 models/ts05_module(旧 models/ 目录中)。"""

    def compute(self, kp, ps):
        try:
            import ts05_module
        except ImportError as e:
            raise GraphError(f"TS05 需要 f2py 扩展 ts05_module,未找到: {e}")
        import geopack.t04 as _t04
        X, Y, Z = self.lattice.mesh()
        parmod = _common_parmod(kp)

        def fn(x, y, z):
            if x < -15.0:
                return _t04.t04(parmod, ps, x, y, z)
            bx, by, bz = ts05_module.t04_s(0, parmod, ps, x, y, z)
            return float(-bx), float(-by), float(-bz)

        v = _external_vectorize(_safe(fn))
        bx, by, bz = v(X, Y, Z)
        return {"field": Field.vector(bx, by, bz, self.lattice)}


@register_node(
    type="ta16",
    name="TA16 RBF (2016)", category="磁场/外部模型", icon="🌐", cost="expensive",
    inputs={"kp": Port("scalar", default=2.0, min=0.0, max=9.0),
            "ps": Port("scalar", default=0.0)},
    outputs={"field": "vector_field"},
)
class TA16Node(Node):
    """需要 f2py 扩展 models/ta16_module 与 TA16_RBF.par(旧 models/ 目录中)。"""

    def compute(self, kp, ps):
        try:
            import ta16_module
        except ImportError as e:
            raise GraphError(f"TA16 需要 f2py 扩展 ta16_module,未找到: {e}")
        import geopack.t04 as _t04
        X, Y, Z = self.lattice.mesh()
        pdyn = 2.0 + kp * 0.5
        dst = -10.0 * kp
        xind = min(2.0, kp / 5.0)
        parmod_rbf = [pdyn, dst, xind, 0.0, 0, 0, 0, 0, 0, 0]

        def fn(x, y, z):
            if x < -15.0:
                return _t04.t04(_common_parmod(kp), ps, x, y, z)
            bx, by, bz = ta16_module.rbf_model_2016(0, parmod_rbf, ps, x, y, z)
            return float(-bx), float(-by), float(-bz)

        v = _external_vectorize(_safe(fn))
        bx, by, bz = v(X, Y, Z)
        return {"field": Field.vector(bx, by, bz, self.lattice)}
