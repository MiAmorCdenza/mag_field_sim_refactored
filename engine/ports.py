"""端口与参数定义。

核心设计(REFACTOR_PLAN §5.3):
- 输入端口 = 参数 + 插座统一:默认值即滑块,连线即上游数据
- 类型系统:标量族 / 格点场 / 粒子流(粒子域后续接入)
"""
from __future__ import annotations

# 标量族(数值/参数)
SCALAR_TYPES = ("scalar", "int", "bool", "enum", "string")
# 格点场
FIELD_TYPES = ("vector_field", "scalar_field")
# 粒子域流(阶段 2 接入)
STREAM_TYPES = ("particle_buffer", "field_table", "geometry")

PORT_TYPES = set(SCALAR_TYPES) | set(FIELD_TYPES) | set(STREAM_TYPES)

_SCALAR_CAST = {
    "scalar": float,
    "int": int,
    "bool": bool,
    "enum": str,
    "string": str,
}


def coerce_scalar(ptype, value):
    """标量类型强制转换。"""
    if ptype in _SCALAR_CAST:
        return _SCALAR_CAST[ptype](value)
    return value


class Port:
    """输入端口定义(兼具参数语义)。"""

    def __init__(self, ptype, default=None, min=None, max=None,
                 ui="slider", desc="", choices=None):
        if ptype not in PORT_TYPES:
            raise ValueError(f"未知端口类型: {ptype}")
        self.ptype = ptype
        self.default = default
        self.min = min
        self.max = max
        self.ui = ui          # slider | number | select | checkbox | text | color
        self.desc = desc
        self.choices = choices

    def to_json(self):
        return {
            "ptype": self.ptype, "default": self.default,
            "min": self.min, "max": self.max, "ui": self.ui,
            "desc": self.desc, "choices": self.choices,
        }

    @classmethod
    def from_json(cls, d):
        return cls(d["ptype"], d.get("default"), d.get("min"), d.get("max"),
                   d.get("ui", "slider"), d.get("desc", ""), d.get("choices"))

    def __repr__(self):
        return f"<Port {self.ptype} default={self.default!r}>"


class Param:
    """无端口参数(枚举、开关等)。"""

    def __init__(self, ptype, default=None, min=None, max=None,
                 desc="", choices=None):
        if ptype not in PORT_TYPES:
            raise ValueError(f"未知参数类型: {ptype}")
        self.ptype = ptype
        self.default = default
        self.min = min
        self.max = max
        self.desc = desc
        self.choices = choices

    def to_json(self):
        return {
            "ptype": self.ptype, "default": self.default,
            "min": self.min, "max": self.max,
            "desc": self.desc, "choices": self.choices,
        }

    @classmethod
    def from_json(cls, d):
        return cls(d["ptype"], d.get("default"), d.get("min"), d.get("max"),
                   d.get("desc", ""), d.get("choices"))

    def __repr__(self):
        return f"<Param {self.ptype} default={self.default!r}>"
