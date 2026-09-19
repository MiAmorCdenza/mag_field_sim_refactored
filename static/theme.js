// 主题切换(#55)—— 默认亮色(便于投影/阅读),可一键切回深色。
//
// 自包含附加件:自己注入 theme_light.css 与工具栏按钮 → index.html 只需一行 <script>。
//   回退 = 删掉那一行。
// 设计要点:
//   · 亮色只作用于**面板/文字**;3D 视口与 HUD 保持深色(线框对比度好、投影清楚)
//   · 选择记忆在 localStorage("mf.theme"),默认 "light"
//   · 切换后派发 window resize:面板宽度/高度变了,three.js 需要重新适配画布
(function () {
    "use strict";
    const KEY = "mf.theme";
    let mode = localStorage.getItem(KEY) || "light";      // 默认亮色

    function injectCss() {
        if (document.getElementById("mf-theme-css")) return;
        const l = document.createElement("link");
        l.id = "mf-theme-css";
        l.rel = "stylesheet";
        l.href = "/theme_light.css";
        document.head.appendChild(l);
    }

    function apply() {
        document.body.classList.toggle("light", mode === "light");
        const b = document.getElementById("btn-theme");
        if (b) {
            b.textContent = mode === "light" ? "深色" : "亮色";
            b.title = mode === "light" ? "切换到深色(暗环境更护眼)"
                                       : "切换到亮色(投影/打印/阅读更清楚)";
        }
    }

    function ensure() {
        injectCss();
        const bar = document.getElementById("topbar");
        if (bar && !document.getElementById("btn-theme")) {
            const b = document.createElement("button");
            b.id = "btn-theme";
            b.onclick = () => {
                mode = (mode === "light") ? "dark" : "light";
                localStorage.setItem(KEY, mode);
                apply();
                window.dispatchEvent(new Event("resize"));   // three.js 重新适配
            };
            // 放在「粒子数/烘焙进度」之前的显眼处:紧挨主题相关的按钮区
            const anchor = document.getElementById("btn-respawn") || null;
            if (anchor && anchor.parentElement === bar) bar.insertBefore(b, anchor.nextSibling);
            else bar.appendChild(b);
        }
        apply();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", ensure);
    } else { ensure(); }
    window.addEventListener("load", () => setTimeout(ensure, 400));
    window.theme = {
        get: () => mode,
        set: (m) => { mode = (m === "dark") ? "dark" : "light"; localStorage.setItem(KEY, mode); apply(); },
    };
})();
