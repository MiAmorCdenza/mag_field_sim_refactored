// 窗口分割条(#43 附加件)—— 可拖拽调整"检查器/预览窗"高度。
//
// 为什么单独一个文件:这是一个**可整体回滚**的实验件 ——
//   回滚 = 删掉 index.html 里的 <script src="/splitter.js"></script> 这一行(其余自动消失)。
//
// 行为:
//   · 自动在 #inspector 前面插入一条分割条(自己注入样式,不污染 index.html)
//   · 上下拖动 → 改检查器高度(钳制 72px ~ 父容器 85%),3D 视口随之变高变矮
//   · 拖完记忆到 localStorage,刷新后恢复;双击分割条 = 恢复自动高度
//   · 拖动过程中派发 window resize 事件,让 three.js 重新适配画布尺寸
(function () {
    "use strict";
    const KEY = "mf.inspectorH";
    const MIN = 72;

    function css() {
        if (document.getElementById("mf-splitter-style")) return;
        const s = document.createElement("style");
        s.id = "mf-splitter-style";
        s.textContent = `
            #mf-splitter {
                flex: 0 0 6px; height: 6px; cursor: row-resize;
                background: linear-gradient(transparent, var(--border, #2a3340));
                position: relative; z-index: 7; user-select: none;
            }
            #mf-splitter:hover, #mf-splitter.mf-dragging {
                background: var(--accent, #4da6ff); opacity: 0.55;
            }
            #mf-splitter::after {
                content: ""; position: absolute; left: 50%; top: 1px;
                width: 46px; height: 3px; margin-left: -23px; border-radius: 2px;
                background: var(--dim, #55606e); opacity: 0.75;
            }`;
        document.head.appendChild(s);
    }

    function setup() {
        const insp = document.getElementById("inspector");
        if (!insp || document.getElementById("mf-splitter")) return false;
        const parent = insp.parentElement;
        if (!parent) return false;

        css();
        const bar = document.createElement("div");
        bar.id = "mf-splitter";
        bar.title = "拖动调整高度 · 双击恢复自动";
        parent.insertBefore(bar, insp);

        // 恢复上次高度
        const saved = parseFloat(localStorage.getItem(KEY) || "");
        if (isFinite(saved) && saved > MIN) apply(saved);

        function apply(h) {
            insp.style.flex = "0 0 auto";
            insp.style.height = h + "px";
            insp.style.maxHeight = "none";        // 手动模式下不受 46%/70% 限制
            window.dispatchEvent(new Event("resize"));   // 让 three.js 重新适配
        }
        function reset() {
            insp.style.flex = "";
            insp.style.height = "";
            insp.style.maxHeight = "";
            localStorage.removeItem(KEY);
            window.dispatchEvent(new Event("resize"));
        }
        function clamp(h) {
            const ph = parent.getBoundingClientRect().height || 600;
            return Math.max(MIN, Math.min(h, ph * 0.85));
        }

        let drag = null;
        bar.addEventListener("mousedown", (e) => {
            drag = { y: e.clientY, h: insp.getBoundingClientRect().height };
            bar.classList.add("mf-dragging");
            e.preventDefault();
        });
        window.addEventListener("mousemove", (e) => {
            if (!drag) return;
            const h = clamp(drag.h + (drag.y - e.clientY));   // 往上拖 = 变高
            apply(h);
            localStorage.setItem(KEY, String(Math.round(h)));
        });
        window.addEventListener("mouseup", () => {
            if (!drag) return;
            drag = null;
            bar.classList.remove("mf-dragging");
        });
        bar.addEventListener("dblclick", reset);
        return true;
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", setup);
    } else {
        setup();
    }
    // 检查器可能被别的脚本后建 → 兜底再试一次
    window.addEventListener("load", () => setTimeout(setup, 300));
})();
