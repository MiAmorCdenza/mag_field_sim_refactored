"""参数中文名补丁(#54)—— 让界面显示中文名,变量名以小字附后。

为什么要集中一张表,而不是逐个节点写 label?
  · 同类参数在几十个节点里反复出现(count / dt / opacity / layer …),
    逐处写会漏、会不一致,评审现场就会出现"这个滑杆叫什么"的尴尬;
  · 集中一处便于你一眼审阅、一次改全;
  · 节点里显式写了 label 的**优先**(个别参数语义特殊时,就地覆盖即可)。

用法:本表由 engine.registry.describe() 自动套用 —— 节点的 inputs/params 若没有自己的
label,就按 (节点类型, 参数名) → 通用名 → 空 的顺序取值。变量名仍会以小字显示,
调参的人依旧能对照文档与代码。
"""

# 通用名:绝大多数节点里同名的参数语义一致
COMMON = {
    # 时间 / 空间天气驱动
    "year": "年份", "month": "月份", "day": "日期(几日)", "ut": "UT 小时",
    "kp": "Kp 指数", "dst": "Dst 指数", "al": "AL 指数",
    "by": "IMF By", "bz": "IMF Bz", "sw_speed": "太阳风速度",
    "rho": "太阳风密度 ρ", "v": "太阳风速度 V",
    "mp_model": "磁层顶模型", "model": "模型", "iopt": "模型选项",
    "parker_custom": "自定义帕克角", "pscale": "功率谱指数",
    # 磁场 / 倾角
    "ps": "倾角 ψ", "b_mult": "场强倍率",
    # 粒子发射与推进
    "count": "粒子数", "v_base": "初速度", "v_random": "速度随机量(%)",
    "angle_random": "角度随机量(%)", "lon": "发射经度", "lat": "发射纬度",
    "dist_ratio": "创生点距离比例", "spawn_radius_ratio": "播撒半径比例",
    "max_range": "活动半径上限", "dt": "时间步长", "substeps": "子步数",
    "substep_cap": "子步上限", "respawn": "持续创生", "mode": "模式",
    # 物种 / 种群
    "q": "电荷数", "mass": "质量(原子质量单位)", "weight": "权重",
    "v_mult": "速度倍率", "preset": "预设", "enabled": "启用", "name": "名称",
    "rows": "行表(物种表)", "density": "密度倍率",
    # 渲染
    "order": "执行顺序", "slot": "槽位名", "layer": "渲染层", "visible": "显示",
    "opacity": "不透明度", "color": "颜色(留空=按模式)",
    "color_mode": "着色方式", "size": "点大小", "trail_length": "拖尾长度",
    "max_points": "最大记录点数", "max_traced_particles": "累积粒子数上限",
    "fps_cap": "帧率上限", "grid": "网格", "bg": "背景", "arrows": "箭头",
    "arrow_spacing": "箭头间距", "dsmax": "线间距", "err": "误差容限",
    "code": "内联代码", "w": "倍率", "axis": "轴", "fmt": "格式",
}

# 节点级覆盖:(节点类型, 参数名) → 中文名(仅当语义与通用名不同时写)
OVERRIDE = {
    ("paraboloid", "v"): "太阳风速度 V",
    ("paraboloid", "rho"): "太阳风密度 ρ",
    ("tilt_source", "day"): "日期(几日)",
    ("tilt_source", "ut"): "UT 小时(倾角有周日变化)",
    ("dipole", "ps"): "倾角 ψ(北轴朝日为正)",
    ("particle_emitter", "mode"): "发射模式",
    ("boris_integrator", "dt"): "时间步长(Re/s 单位制)",
}


def label_for(node_type: str, param_name: str, own: str = "") -> str:
    """取中文名:节点自带的 label 优先,其次节点级覆盖,最后通用名。"""
    if own:
        return own
    hit = OVERRIDE.get((node_type, param_name))
    if hit:
        return hit
    return COMMON.get(param_name, "")
