// 执行计划编译测试:plan_compiler.h(JSON→Plan + 默认后备计划)。
//
// 编译(MSVC,需 nlohmann include —— CMake 已 FetchContent):
//   cl /EHsc /O2 /std:c++17 /I..\core /I..\build\_deps\nlohmann_json-src\include plan_test.cpp
#include <cstdio>
#include <string>

#include <nlohmann/json.hpp>

#include "plan.h"
#include "plan_compiler.h"
#include "advancers.h"

using json = nlohmann::json;

static int failures = 0;
#define CHECK(cond, msg)                                                      \
    do {                                                                      \
        if (!(cond)) {                                                        \
            std::printf("FAIL: %s\n", msg);                                   \
            ++failures;                                                       \
        } else {                                                              \
            std::printf("  ok: %s\n", msg);                                   \
        }                                                                     \
    } while (0)

int main() {
    std::printf("=== 1) JSON → Plan 编译(引擎 particle_plan 输出) ===\n");
    {
        json doc = {
            {"slow_path", false},
            {"count", 4},
            {"ops", json::array({
                json{{"kind", "emitter"}, {"node", "pe"},
                     {"params", json{{"mode", 1}, {"v_base", 500.0}}}},
                json{{"kind", "step"}, {"node", "bi"}, {"kernel", "boris"},
                     {"params", json{{"dt", 0.02}, {"substeps", 4},
                                     {"enable_gravity", true},
                                     {"gravity_mult", 2.0}}},
                     {"slots", json{{"b", "B"}, {"e", "E"}, {"drag", nullptr}}}},
                json{{"kind", "step"}, {"node", "rk"}, {"kernel", "rk4"},
                     {"slots", json{{"b", "B"}}}},
                json{{"kind", "encode"}, {"node", "oe"}},
            })},
        };
        Plan p;
        std::string err;
        CHECK(plancomp::plan_from_json(doc, p, err), "计划 JSON 编译成功");
        CHECK(p.ops.size() == 4, "算子数 = 4");
        CHECK(!p.slow_path, "slow_path = false");
        CHECK(p.ops[0].kind == OpKind::Emitter, "算子 0 = Emitter");
        CHECK(p.ops[0].emitter.cfg.mode == 1 &&
                  p.ops[0].emitter.cfg.v_base == 500.0,
              "发射器参数透传");
        CHECK(p.ops[1].kind == OpKind::Step && p.ops[1].step.kernel == "boris",
              "算子 1 = Step(boris)");
        CHECK(p.ops[1].step.dt == 0.02 && p.ops[1].step.substeps == 4,
              "步进参数透传(dt/substeps)");
        CHECK(p.ops[1].step.enable_gravity && p.ops[1].step.gravity_mult == 2.0,
              "引力开关与倍率透传");
        CHECK(p.ops[1].step.b_slot == "B" && p.ops[1].step.e_slot == "E" &&
                  p.ops[1].step.drag_slot == "",
              "槽位绑定(null → 空串)");
        CHECK(p.ops[2].step.kernel == "rk4" && p.ops[2].step.substeps == 5,
              "算子 2 = Step(rk4,默认子步数)");
        CHECK(p.ops[3].kind == OpKind::Encode, "算子 3 = Encode");
    }

    std::printf("=== 2) 异常输入 ===\n");
    {
        Plan p;
        std::string err;
        // 复杂 JSON 构造移出宏:初始化器内逗号会劈开 CHECK 宏参数
        json bad = {{"ops", json::array({json{{"kind", "warp_drive"}}})}};
        CHECK(!plancomp::plan_from_json(bad, p, err), "未知算子类型被拒绝");
        CHECK(!err.empty(), "错误信息非空");
        CHECK(!plancomp::plan_from_json(json::object(), p, err),
              "缺 ops 字段被拒绝");
    }

    std::printf("=== 3) 默认后备计划(无粒子域节点,legacy 兼容) ===\n");
    {
        EmitterConfig ec;
        ec.mode = 0;
        ec.v_base = 400.0;
        ec.types = {{1.0, 0.1, 1.0, 1.0, 0xff3333}};
        IntegratorConfig icfg;
        icfg.dt = 0.01;
        icfg.max_range = 90.0;
        Plan p = plancomp::make_default_plan(ec, 5, icfg);
        CHECK(p.ops.size() == 3, "后备计划 = 3 算子");
        CHECK(p.ops[0].kind == OpKind::Emitter &&
                  p.ops[0].node_id == "__default",
              "后备 Emitter 算子");
        CHECK(p.ops[0].emitter.cfg.types.size() == 1, "粒子类型列表透传");
        CHECK(p.ops[1].kind == OpKind::Step && p.ops[1].step.kernel == "boris" &&
                  p.ops[1].step.dt == 0.01 && p.ops[1].step.substeps == 5 &&
                  p.ops[1].step.max_range == 90.0,
              "后备 Step 算子(boris/legacy 参数)");
        CHECK(p.ops[1].step.b_slot == "B" && p.ops[1].step.e_slot == "E" &&
                  p.ops[1].step.drag_slot == "drag",
              "后备槽位绑定 B/E/drag");
        CHECK(p.ops[2].kind == OpKind::Encode, "后备 Encode 算子");
    }

    std::printf("=== 4) 内核注册一致性 ===\n");
    {
        CHECK(native_builtins().size() == 6, "原生节点 6 类型");
        // 每个 *_integrator 类型都有同名内核(去后缀)
        for (const auto& n : native_builtins()) {
            std::string t = n.type;
            if (t.size() < 11 || t.substr(t.size() - 11) != "_integrator")
                continue;
            CHECK(find_advancer(t.substr(0, t.size() - 11)) != nullptr,
                  (t + " 有对应内核").c_str());
        }
    }

    std::printf(failures ? "\n[%d 项失败]\n" : "\n全部通过 ✅\n", failures);
    return failures ? 1 : 0;
}
