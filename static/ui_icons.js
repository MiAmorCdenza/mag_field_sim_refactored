// UI 像素图标替换层(#46)—— 把界面文字里的 Emoji 换成像素画(与节点图标同风格)。
//
// 自包含附加件:回滚 = 删掉 index.html 里的 <script src="/ui_icons.js"></script>。
// 图标来自 static/icons/ui/*.svg(tools/gen_ui_icons.py 生成,16×16 字符网格)。
//
// 做法:遍历**静态 DOM** 里的直接文本节点,把开头的 Emoji 换成 <img class="ui-ico">;
//   加载失败(onerror)自动回退成原来的 Emoji —— 与 #39 节点图标同一套回退策略。
// 注意:HUD 是每 250ms 重建的,这里**不动**它(要动得改 protocol.js 的拼接逻辑,
//   留作后续;此处只处理工具栏/面板标题/Dock 头部/引导页卡片)。
(function () {
    "use strict";

    // Emoji → 图标名(一个 Emoji 只映射一次;未列出的保持原样)
    const MAP = [
        ["⏸", "pause"], ["▶", "play"], ["⬆", "upload"], ["↺", "reset"],
        ["🔄", "refresh"], ["⟳", "refresh"], ["🧹", "broom"], ["☰", "menu"],
        ["➕", "plus"], ["◧", "split"], ["⊞", "split"], ["💾", "save"],
        ["🔍", "magnifier"], ["◀", "chevron-left"], ["⚠", "warn"], ["✖", "close"],
    ];
    const SELECTORS = [
        "button",                      // 工具栏/对话框/引导页所有按钮(不依赖容器类名)
        "#dock-head button", ".panel-title",
        ".insp-title", ".dock-group-head",
        "#launcher .card", "#launcher .card-title",
        "#sim-hud",                    // #46 HUD 每 250ms 重建 → 靠下面的定时补扫
    ];

    function injectStyle() {
        if (document.getElementById("mf-uiico-style")) return;
        const s = document.createElement("style");
        s.id = "mf-uiico-style";
        s.textContent = `
            img.ui-ico {
                width: 1em; height: 1em; margin-right: 4px;
                vertical-align: -0.15em; image-rendering: pixelated;
            }
        `;
        document.head.appendChild(s);
    }

    function iconImg(name, fallback) {
        const img = document.createElement("img");
        img.className = "ui-ico";
        img.alt = fallback || "";
        img.src = "/icons/ui/" + name + ".svg";
        img.onerror = function () {                       // 拿不到图标 → 回退 emoji
            const t = document.createTextNode((fallback || "") + " ");
            if (this.parentNode) this.parentNode.replaceChild(t, this);
        };
        return img;
    }

    function rewriteElement(el) {
        // 注意:**不能**给元素打"已处理"标记 —— 有些按钮文案是后来被代码重写的
        // (简化/标准面板切换会把 "⊞ 标准面板" 重新写回 textContent),标记会让
        // 复活的 emoji 永远处理不到。改写本身幂等(只动含映射 emoji 的文本节点),
        // 所以重复调用是安全的。
        if (!el) return;
        for (const node of Array.from(el.childNodes)) {
            if (node.nodeType !== 3) continue;            // 只看直接文本节点
            let text = node.nodeValue;
            if (!text) continue;
            for (const [emoji, name] of MAP) {
                // 兼容 emoji 变体选择符(U+FE0F):HTML 里常写成 "⬆️" 而 MAP 里是 "⬆"
                let at = -1, used = "";
                for (const v of [emoji + "\uFE0F", emoji]) {
                    at = text.indexOf(v);
                    if (at >= 0) { used = v; break; }
                }
                if (at < 0) continue;
                const before = text.slice(0, at);
                const after = text.slice(at + used.length);
                const img = iconImg(name, emoji);
                const tail = document.createTextNode(after.replace(/^\s+/, " "));
                if (before) el.insertBefore(document.createTextNode(before), node);
                el.insertBefore(img, node);
                el.insertBefore(tail, node);
                el.removeChild(node);
                text = after;                              // 继续找同一元素的其它 emoji
                rewriteElement(el);                        // 重新走一遍(结构已变)
                return;
            }
        }
    }

    // 递归版:HUD 的每个 bit 在**子元素**里(protocol.js 用 innerHTML 拼),
    // 只处理直接文本节点会一个都匹配不到 —— 所以对 HUD 这类容器要连子元素一起扫。
    function rewriteDeep(el) {
        if (!el) return;
        rewriteElement(el);
        const kids = el.querySelectorAll("*");
        for (const c of kids) {
            try { rewriteElement(c); } catch (e) { /* 单个失败不影响其它 */ }
        }
    }

    function rewrite(root) {
        const scope = root || document;
        for (const sel of SELECTORS) {
            scope.querySelectorAll(sel).forEach(el => {
                try { rewriteElement(el); } catch (e) { /* 单个元素失败不影响其它 */ }
            });
        }
    }

    function init() {
        injectStyle();
        rewrite();
        // 引导页卡片是异步渲染的 → 包装 show/toggle,显示后再替换一次
        const L = window.launcher;
        if (L && !L.__uiIco) {
            ["show", "toggle", "load"].forEach(k => {
                if (typeof L[k] !== "function") return;
                const orig = L[k];
                L[k] = function () {
                    const r = orig.apply(this, arguments);
                    setTimeout(() => rewrite(), 60);
                    return r;
                };
            });
            L.__uiIco = true;
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else { init(); }
    window.addEventListener("load", () => setTimeout(init, 400));
    // 有些按钮/标题是异步渲染或后续才改文案的 → 再补两次(幂等,已处理过会跳过)
    window.addEventListener("load", () => {
        setTimeout(() => rewrite(), 1500);
        setTimeout(() => rewrite(), 3500);
        // HUD 由 protocol.js 每 250ms 重写 innerHTML → 用低频补扫保持像素图标
        // (HUD 只有几行,成本可忽略;比改 protocol.js 的拼接逻辑更少侵入)
        setInterval(() => {
            const hud = document.getElementById("sim-hud");
            if (hud) rewriteDeep(hud);
        }, 1000);
    });
    // 字符串版:给 protocol.js 这类用 innerHTML 拼内容的场景直接嵌 <img>
    // (HUD 每 250ms 重建,靠事后 DOM 替换跑不过它 → 必须在源头就拼成图标)
    function html(name, alt) {
        return '<img class="ui-ico" src="/icons/ui/' + name + '.svg" alt="' +
               (alt || "") + '">';
    }

    window.uiIcons = { rewrite, rewriteDeep, iconImg, html, MAP };          // 供自动化测试/后续复用
})();
