# 预设指南(人类 / Agent 共用)

> 这份文档放在 `graphs/` 里:与预设同目录,且会被 `scripts/package.ps1` 一起打进发布包。
> 目标:让**人**和**Agent**都能可靠地读、写、验、改预设,不必先读源码。

---

## 一句话

**预设 = `graphs/preset_<id>.json` 里的一整张图**(节点 + 连线 + 点阵 + 元数据)。
**加文件 = 多一张引导页卡片;改文件 = 改卡片**,不需要改任何代码。

---

## 1. 预设是怎么被发现的

| 环节 | 位置 | 说明 |
|---|---|---|
| 列表 | `GET /api/presets` | 扫 `graphs/preset_*.json`,**只认 `preset_` 前缀** |
| id | 文件名 | `preset_compare_fields.json` → id = `compare_fields` |
| 卡片 | 文件里的 `preset` 块 | `name` / `desc` / `sort`(排序,小在前) |
| 载入 | `GET /api/preset?id=` | 引导页点卡片 → 画布 + 服务器同时换上这张图 |

---

## 2. 文件结构(最小可用)

```json
{
  "preset": { "id": "my_demo", "name": "我的演示",
              "desc": "一句话说明这张图看什么", "sort": 50 },
  "version": 1,
  "lattice": { "preset": "tiny" },
  "nodes": [
    { "id": "d",  "type": "dipole", "input_defaults": { "ps": 0.5 }, "pos": [60, 40] },
    { "id": "ob", "type": "output_slot", "params": { "slot": "B" }, "pos": [300, 40] }
  ],
  "edges": [ { "from": ["d", "field"], "to": ["ob", "field"] } ],
  "outputs": {}
}
```

约定:
- 文件里的 `id` **只允许 `[a-z0-9_-]`**,并与文件名/卡片 id 保持一致(保存接口也是这个规则)
- `pos` 是画布坐标(可省,见"常见坑")
- `outputs` 一般**留空** —— 由 `output_slot` 节点推导(两种写法并存容易自相矛盾)
- 参数分两类:`input_defaults`(端口默认值,上游没接线时生效)与 `params`(节点自有参数)

---

## 3. 保存 / 覆盖(界面)

工具栏 **「💾 保存预设」** → 目标选「另存为新预设」或「覆盖:<现有预设>」→ 填名称/说明 → 保存。

服务端行为(都在 `POST /api/preset` 内):
1. **先跑图校验**(见第 5 节),不过就 **400 拒绝**,并回传 `detail.errors`
2. 覆盖已有文件前**自动备份**到 `graphs/.backup/preset_<id>.<时间戳>.json`(已在 `.gitignore`)
3. **原子写**:先写 `.tmp` 再 `rename`,中途失败不会留半个文件
4. 只允许写 `graphs/preset_<slug>.json`(slug 限 `[a-z0-9_-]`,防目录穿越)
5. 纯中文名称生成不出 slug → **用时间戳兜底**作 id(中文仍可作显示名称)
6. 现场防误覆盖:启动服务器时设 **`MF_PRESETS_READONLY=1`** → 保存返回 403

---

## 4. 命令行 / Agent 工作流(推荐顺序)

```powershell
# 1) 写文件:graphs/preset_<id>.json(照第 2 节结构)

# 2) 先校验再交付(单文件、秒级;唯一权威口径)
python -c "import json;from engine.validate import validate_graph as v;g=json.load(open('graphs/preset_x.json',encoding='utf-8'));print(v(json.dumps({'root':'.','graph':g})))"
#    看 ok:true;若 false,读 errors(能加载 / 零告警 / 能烘焙 三关)

# 3) 跑预设回归(更严:对每个非空预设要求 **零告警 + 能烘焙**)
python tests\test_presets.py

# 4) 界面验收:引导页点卡片 → 看 HUD 的 N/E、计划粒子、场源、粒子数、帧率
```

> 给 Agent 的提示:改预设**只需**这四步;不要用"猜 API"的方式改服务端代码。
> 本项目的既有 API 用法(如 `POST` 路由、日志宏)都可在源码里 grep 到,先看再写。

---

## 5. 校验口径(与回归完全一致)

| 关 | 判据 | 失败表现 |
|---|---|---|
| 1 | **能加载**:所有 `type` 都在节点注册表里 | `errors: ["图加载失败:未知节点类型: xxx"]` |
| 2 | **计划零告警**:`particle_plan().warnings` 为空 | `warnings: ["code @node", …]` |
| 3 | **能烘焙**:声明槽位(或 `output_slot` 推导的)求出**全有限**值 | `errors: ["槽位 B 含非有限值(NaN/Inf)"]` |

常见告警码(现场会成为画布红框 / 退化计划,**建议都清掉**):

```
step_no_b            积分器没接磁场
no_emitter/no_encoder 粒子域缺发射器/编码器
injection_unwired    注入节点没接线
species_not_wired    物种种群没接到发射器
render_item_unwired  渲染项没接数据
degenerate_injection 注入参数退化(粒子全重合等)
respawn_off          关掉了持续创生(种群会衰减)
population_decaying  运行期:死伤过半仍在衰减
external_only_field  T89/T96/… 只给外部场,要内场请另加 dipole / A2000
multiple_step_ops    图里有多个积分器(**只允许一个**)
```

---

## 6. 常见坑(都是踩过的)

1. **别按 `id` 匹配编辑器里的节点** —— 编辑器里 `node.id` 是 LiteGraph 的**数字** id,与文件里的 `"id"` 不同。
   若要做白名单之类的事(如 `static/ui/demo_focus.json`),请按 **`type` 或节点名** 匹配。
2. **`outputs` 别两种写法混用** —— 留空最安全(由 `output_slot` 推导)。
3. **`pos` 缺失** —— 只有"所有节点都没位置(或全是 0,0)"时载入才会自动层次化布局;否则保持作者排布。
   想重排:标准面板的「🧹 自动布局」。
4. **外部场模型不含偶极子** —— `T89/T96/T01/T04/TS05/TA16` 只给外部场;要内场请加 `dipole`
   或 `A2000 抛物面(内场)`(后者自带环电流/尾电流/磁层顶屏蔽,**别再叠 T89**)。
5. **倾角统一** —— 用一个「倾角源(日期→倾角)」节点喂给各模型;`A2000` 的 `par(1)` 与 `ps` **符号相反**,
   节点内部已取负,**不要在预设里手动再取负**。
6. **点阵选择**:`tiny` 快(约 1–4 s),`coarse` 慢但域大。A2000 / 磁层顶类模型在 `tiny` 下域偏小,
   看完整磁层请换 `coarse`。
7. **一个积分器** —— 多个积分器会把同一批粒子重复推进;引擎只保留第一个并报 `multiple_step_ops`。

---

## 7. 相关文件索引

| 内容 | 位置 |
|---|---|
| 图校验入口(唯一权威口径) | `engine/validate.py` |
| 预设回归测试 | `tests/test_presets.py` |
| 保存接口 | `server/src/server_app.cpp` 的 `register_preset_routes`(**POST /api/preset**) |
| 点阵预设 | `engine/` 内的 `lattice presets`(`tiny` / `coarse` …) |
| 引导模式白名单(现场只显示重点参数) | `static/ui/demo_focus.json` + `static/simple_ui.js` 的 `GUIDED` |
| 每个预设的讲解 | 同目录 `preset_<id>.md` |
