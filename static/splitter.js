// 窗口分割条(#43 附加件·实验)—— 手动拖拽调整各面板尺寸。
//
// 可整体回滚的实验件:回滚 = 删掉 index.html 里的 <script src="/splitter.js"></script>。
//
// 四条分割条(自己注入样式与 DOM,不改 index.html 的 CSS):
//   1) #inspector 上方(横)      上下拖 → 检查器高度;           两种模式都可用
//   2) #dock 右侧(竖)           左右拖 → 参数栏宽度;           仅简化模式(Dock 可见时)
//   3) #right 左侧(竖,反向)     左右拖 → 右栏宽度(拖左=变宽);  仅标准模式
//   4) #viewport-wrap 上方(横)   上下拖 → 3D 视口高度 ↔ 画布;   仅标准模式
//
// 共同行为:悬停高亮 · 拖动时派发 window resize(three.js 重适配画布) ·
// 尺寸记忆在 localStorage · 双击恢复默认。
//
// ⚠ 关键修正:记忆值**只在对应分割条可见(即当前模式有效)时套用**。
//   曾经无条件套用 → 在标准模式测出的右栏宽度 720px 被套进简化模式的 #right,
//   把右侧撑成一条空列(#right 在简化模式里本应由内容决定宽度)。模式切换时会
//   重新"对账":该显示的套用记忆值,该隐藏的清掉内联尺寸(但**不**忘掉记忆值)。
(function () {
    "use strict";
    const RECON = [];        // 每条分割条的对账函数(切模式时重跑)

    function injectStyle() {
        if (document.getElementById("mf-splitter-style")) return;
        const s = document.createElement("style");
        s.id = "mf-splitter-style";
        s.textContent = `
            .mf-split { position: relative; z-index: 7; user-select: none; }
            .mf-split:hover, .mf-split.mf-dragging {
                background: var(--accent, #4da6ff); opacity: 0.55;
            }
            .mf-split-h { flex: 0 0 6px; height: 6px; cursor: row-resize;
                          background: linear-gradient(transparent, var(--border, #2a3340)); }
            .mf-split-h::after {
                content: ""; position: absolute; left: 50%; top: 1px;
                width: 46px; height: 3px; margin-left: -23px; border-radius: 2px;
                background: var(--dim, #55606e); opacity: 0.75;
            }
            .mf-split-v { flex: 0 0 6px; width: 6px; cursor: col-resize;
                          background: linear-gradient(90deg, transparent, var(--border, #2a3340)); }
            .mf-split-v::after {
                content: ""; position: absolute; top: 50%; left: 1px;
                width: 3px; height: 46px; margin-top: -23px; border-radius: 2px;
                background: var(--dim, #55606e); opacity: 0.75;
            }
            body:not(.simple-mode) #mf-split-dock { display: none; }
            body.simple-mode #mf-split-right,
            body.simple-mode #mf-split-view { display: none; }
        `;
        document.head.appendChild(s);
    }

    // target: 要调尺寸的元素;axis: "y"=高度 / "x"=宽度;invert: 拖反方向才变大
    function attach(barId, target, axis, min, max, key, insertAfter, invert) {
        const el = document.querySelector(target);
        if (!el || document.getElementById(barId)) return false;
        const parent = el.parentElement;
        if (!parent) return false;

        const bar = document.createElement("div");
        bar.id = barId;
        bar.className = "mf-split " + (axis === "y" ? "mf-split-h" : "mf-split-v");
        bar.title = (axis === "y" ? "拖动调整高度" : "拖动调整宽度") + " · 双击恢复默认";
        parent.insertBefore(bar, insertAfter ? el.nextSibling : el);

        const visible = () => getComputedStyle(bar).display !== "none";

        const apply = (v) => {
            if (axis === "y") {
                el.style.flex = "0 0 auto";
                el.style.height = v + "px";
                el.style.maxHeight = "none";
            } else {
                document.body.classList.remove("dock-collapsed");   // Dock:拖动即展开
                el.style.flex = "0 0 " + v + "px";
                el.style.maxWidth = "none";
            }
            window.dispatchEvent(new Event("resize"));
        };
        const clearInline = () => {          // 清内联尺寸,但**保留**记忆值
            ["flex", "height", "maxHeight", "maxWidth"].forEach(p => { el.style[p] = ""; });
            window.dispatchEvent(new Event("resize"));
        };
        const reset = () => { clearInline(); localStorage.removeItem(key); };

        // 对账:可见 → 套用记忆值;不可见 → 清掉(避免"标准模式的宽度污染简化模式")
        const reconcile = () => {
            const saved = parseFloat(localStorage.getItem(key) || "");
            if (visible() && isFinite(saved) && saved >= min) apply(saved);
            else if (!visible()) clearInline();
        };
        RECON.push(reconcile);

        let drag = null;
        bar.addEventListener("mousedown", (e) => {
            const r = el.getBoundingClientRect();
            drag = { x: e.clientX, y: e.clientY,
                     v: axis === "y" ? r.height : r.width };
            bar.classList.add("mf-dragging");
            e.preventDefault();
        });
        window.addEventListener("mousemove", (e) => {
            if (!drag) return;
            let raw;
            if (axis === "y") raw = drag.v + (drag.y - e.clientY);        // 上拖 = 变高
            else raw = drag.v + (invert ? drag.x - e.clientX              // 左拖 = 变宽
                                        : e.clientX - drag.x);
            const v = Math.max(min, Math.min(raw, max));
            apply(v);
            localStorage.setItem(key, String(Math.round(v)));
        });
        window.addEventListener("mouseup", () => {
            if (!drag) return;
            drag = null;
            bar.classList.remove("mf-dragging");
        });
        bar.addEventListener("dblclick", reset);
        return true;
    }

    function reconcileAll() { RECON.forEach(f => { try { f(); } catch (e) { /* 忽略 */ } }); }

    function setup() {
        injectStyle();
        attach("mf-split-insp", "#inspector", "y", 72, 4000, "mf.inspectorH", false);
        attach("mf-split-dock", "#dock", "x", 160, 560, "mf.dockW", true);
        attach("mf-split-right", "#right", "x", 260, 720, "mf.rightW", false, true);
        attach("mf-split-view", "#viewport-wrap", "y", 120, 4000, "mf.viewportH", false);
        reconcileAll();                                   // 首次:按当前模式套用/清理
        const mb = document.getElementById("btn-ui-mode");
        if (mb) mb.addEventListener("click", () => setTimeout(reconcileAll, 80));
        // 兜底:面板重建后也重新对账(简化模式下 Dock 由 simpleUI 渲染)
        window.addEventListener("load", () => setTimeout(reconcileAll, 500));
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", setup);
    } else {
        setup();
    }
    window.addEventListener("load", () => setTimeout(setup, 300));
    window.mfSplitters = { reconcileAll };
})();
