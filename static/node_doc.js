// 节点说明 / 公式渲染(#54)—— 把节点自带的 docstring 与 LaTeX 公式显示在界面上。
//
// 设计:
//   · 内容来源:registry.describe() 已转发 doc(类 docstring)与 formula(规格里的 LaTeX)
//     —— 所以"写节点时顺手写的说明"直接就能显示,不用重复维护文案。
//   · 渲染:KaTeX 本地内置(static/vendor/katex/),离线可用;取不到就原样显示源码
//     (绝不白屏、不报错)。
//   · 挂载点:editor.js 的 buildParamsInto() 开头调一次 —— Dock(简化面板)与
//     属性面板(标准面板)共用同一个函数,所以**一处接通、两边都有**。
//   · 幂等:同一 body 只插一次(重复调用直接返回)。
//   · 纯文本优先、无 emoji(用户要求)。文字说明取 docstring 首段;公式单独一行居中。
(function () {
    "use strict";

    function injectStyle() {
        if (document.getElementById("mf-nodedoc-style")) return;
        const s = document.createElement("style");
        s.id = "mf-nodedoc-style";
        s.textContent = `
            .node-doc { border-left: 2px solid #1f6feb; padding: 6px 8px; margin: 0 0 10px;
                        background: #12171e; border-radius: 4px; }
            .node-doc .nd-title { color: #58a6ff; font-size: .72rem; font-weight: 700;
                                  margin-bottom: 4px; display: flex; gap: 6px; align-items: center; }
            .node-doc .nd-more { margin-left: auto; background: #21262d; color: #8b949e;
                                 border: 1px solid #30363d; border-radius: 4px;
                                 font-size: .68rem; padding: 0 6px; cursor: pointer; }
            .node-doc .nd-doc { color: #9aa7b4; font-size: .72rem; line-height: 1.5;
                                white-space: pre-wrap; }
            .node-doc .nd-doc.short { display: -webkit-box; -webkit-line-clamp: 3;
                                      -webkit-box-orient: vertical; overflow: hidden; }
            .node-doc .nd-formula { margin-top: 6px; padding: 5px 6px; background: #0d1117;
                                    border: 1px solid #21262d; border-radius: 4px;
                                    color: #c9d1d9; overflow-x: auto; }
            .node-doc .nd-formula .katex { font-size: 1.02em; }
            .node-doc .nd-raw { color: #d2a8ff; font-family: Consolas, monospace; font-size: .74rem;
                                white-space: pre-wrap; }
        `;
        document.head.appendChild(s);
    }

    // KaTeX 渲染;失败或未加载 → 原样显示 LaTeX 源码(可读、不中断)
    function renderTex(host, tex) {
        const raw = document.createElement("span");
        raw.className = "nd-raw";
        raw.textContent = tex;
        if (window.katex && typeof window.katex.render === "function") {
            try {
                host.textContent = "";
                window.katex.render(tex, host, { throwOnError: true, displayMode: false });
                return;
            } catch (e) {
                host.textContent = "";
            }
        }
        host.appendChild(raw);
    }

    function attach(node, body) {
        if (!node || !node._spec || !body) return false;
        if (body.querySelector(".node-doc")) return true;            // 幂等
        const spec = node._spec;
        const doc = String(spec.doc || "").trim();
        const tex = String(spec.formula || "").trim();
        if (!doc && !tex) return false;

        injectStyle();
        const box = document.createElement("div");
        box.className = "node-doc";

        const title = document.createElement("div");
        title.className = "nd-title";
        title.appendChild(document.createTextNode("说明"));
        box.appendChild(title);

        if (doc) {
            const p = document.createElement("div");
            p.className = "nd-doc short";
            p.textContent = doc;
            box.appendChild(p);
            if (doc.length > 90 || doc.indexOf("\n") >= 0) {
                const btn = document.createElement("button");
                btn.className = "nd-more";
                btn.textContent = "更多";
                btn.onclick = (e) => {
                    e.stopPropagation();
                    const on = p.classList.toggle("short");
                    btn.textContent = on ? "更多" : "收起";
                };
                title.appendChild(btn);
            }
        }

        if (tex) {
            const f = document.createElement("div");
            f.className = "nd-formula";
            renderTex(f, tex);
            box.appendChild(f);
        }

        body.insertBefore(box, body.firstChild);
        return true;
    }

    window.nodeDoc = { attach, renderTex };
})();
