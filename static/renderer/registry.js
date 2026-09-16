// 渲染项注册表:内置 items/*.js、user_render_items/*.js 文件插件、
// 以及内联 JS 代码编译注册(节点 params.code)。
//
// 渲染项插件形态:
//   registerRenderItem({
//       id, layer, subscribes: ["particles", ...],
//       setup(scene, three, api) { ... },   // 建几何/材质
//       onData(frame, meta) { ... },        // 数据帧到达
//       onParam(params) { ... },            // 节点参数变更
//       dispose() { ... },                  // 卸载释放
//   });
window.renderRegistry = (function () {
    "use strict";

    const templates = new Map();  // 模板 id(类型名)→ spec
    const instances = new Map();  // 节点 id → spec(实例)

    function register(spec) {
        if (!spec || !spec.id) throw new Error("渲染项必须提供 id");
        templates.set(spec.id, spec);
        // 已有实例(同模板)全部重建
        for (const [nodeId, inst] of instances) {
            if (inst._template === spec.id) instantiate(nodeId, spec.id, inst._params);
        }
        return spec;
    }

    // 图内渲染节点 → 渲染项实例(节点 id 唯一)
    // channels(#32):由编辑器按**接线**解析出的订阅通道数组;
    //   - 传了数组(可为空)→ 覆盖渲染项自带 subscribes(接线决定订阅)
    //   - 传 undefined → 用渲染项 JS 里的 subscribes(旧行为/无接线信息)
    function instantiate(nodeId, templateId, params, channels) {
        const tpl = templates.get(templateId);
        if (!tpl) {
            // 没有对应实现(如 render_item_diagnostics 尚未实现):
            // 必须显式告警,否则用户加了节点却什么都没发生
            const msg = `渲染项 ${nodeId}:没有实现模板 "${templateId}"` +
                        `(节点已忽略;可用内联代码或 items/*.js 插件实现)`;
            console.warn("[renderRegistry]", msg);
            window.uiLog && window.uiLog("warn", "render_item_missing", msg,
                                         { node: nodeId, template: templateId });
            window.toast && window.toast("⚠ " + msg);
            return null;
        }
        if (instances.has(nodeId)) {
            try { window.renderHost.unregisterItem(nodeId); } catch (e) { /* ignore */ }
        }
        const inst = Object.assign({}, tpl);
        inst.id = nodeId;
        inst._template = templateId;
        inst._params = params || {};
        if (Array.isArray(channels)) {
            inst.subscribes = channels.slice();
            inst._channelsFromWiring = true;
        }
        instances.set(nodeId, inst);
        window.renderHost.registerItem(inst);
        window.renderHost.applyParams(nodeId, inst._params);
        return inst;
    }

    function get(id) { return instances.get(id) || templates.get(id); }
    function templateIds() { return [...templates.keys()]; }

    // 编译内联代码为模板(安全:try/catch + 失败回滚旧实现)
    function compileInline(templateId, code) {
        const previous = templates.get(templateId);
        const registered = [];
        const localRegister = (spec) => { registered.push(spec); return spec; };
        const factory = new Function("three", "registerRenderItem", "host", code);
        factory(THREE, localRegister, window.renderHost);
        if (!registered.length) throw new Error("代码未调用 registerRenderItem(...)");
        const spec = Object.assign({}, registered[0], { id: templateId });
        try {
            register(spec);  // 注册新模板(内部重建所有实例)
        } catch (e) {
            if (previous) register(previous);  // 回滚
            throw e;
        }
        return spec;
    }

    return { register, instantiate, get, templateIds, compileInline };
})();

// 全局注册入口(插件文件与内联代码都调用它)
window.registerRenderItem = (spec) => window.renderRegistry.register(spec);
window.registerInspector = (spec) => window.renderHost.registerInspector(spec);   // #43 检查器插件
