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

    const registry = new Map();  // id -> spec(当前生效版)

    function register(spec) {
        if (!spec || !spec.id) throw new Error("渲染项必须提供 id");
        if (registry.has(spec.id)) {
            try { window.renderHost.unregisterItem(spec.id); }
            catch (e) { /* ignore */ }
        }
        registry.set(spec.id, spec);
        if (window.renderHost) window.renderHost.registerItem(spec);
        return spec;
    }

    function get(id) { return registry.get(id); }
    function ids() { return [...registry.keys()]; }

    // 编译内联代码为渲染项(安全:try/catch + 失败回滚旧实现)
    function compileInline(itemId, code) {
        const previous = registry.get(itemId);
        const registered = [];
        const localRegister = (spec) => { registered.push(spec); return spec; };
        const factory = new Function("three", "registerRenderItem", "host", code);
        factory(THREE, localRegister, window.renderHost);
        if (!registered.length) throw new Error("代码未调用 registerRenderItem(...)");
        const spec = Object.assign({}, registered[0], { id: itemId });
        try {
            register(spec);  // 注册新实现(内部会先卸载旧实现)
        } catch (e) {
            if (previous) register(previous);  // 回滚
            throw e;
        }
        return spec;
    }

    return { register, get, ids, compileInline };
})();

// 全局注册入口(插件文件与内联代码都调用它)
window.registerRenderItem = (spec) => window.renderRegistry.register(spec);
