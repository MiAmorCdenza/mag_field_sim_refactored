// 预设保存(#45 前端)—— 「💾 保存预设」按钮 + 覆盖/另存对话框。
//
// 自包含实验/附加件(与 splitter.js 同风格):回滚 = 删掉 index.html 里这一行
//   <script src="/preset_save.js"></script>
// 其余(按钮、对话框、样式)都由本文件自己注入。
//
// 服务端契约(已验收):
//   POST /api/preset {mode:"overwrite"|"saveas", id?, preset:{name,desc,sort}, graph, force?}
//   200 → {ok, id, mode, validate, path}   400 → {ok:false, stage:"validate", detail:{errors,warnings}}
//   403 → 只读(MF_PRESETS_READONLY)       500 → 校验调用/写盘失败
//
// 注意:画布 → 图 doc 用 window.editor.exportGraph()(与「⬆ 应用图到服务器」同一函数),
// 保证"保存的内容 = 你在画布上看到的内容"。
(function () {
    "use strict";
    const NEW = "__new__";

    function injectStyle() {
        if (document.getElementById("mf-save-style")) return;
        const s = document.createElement("style");
        s.id = "mf-save-style";
        s.textContent = `
            #mf-save-mask {
                position: fixed; inset: 0; z-index: 60; display: none;
                background: rgba(0,0,0,.45); align-items: center; justify-content: center;
            }
            #mf-save-mask.open { display: flex; }
            #mf-save-box {
                width: 380px; background: #0f141b; border: 1px solid var(--border);
                border-radius: 6px; padding: 14px 16px; color: var(--text);
                font-size: .82rem; box-shadow: 0 8px 30px rgba(0,0,0,.5);
            }
            #mf-save-box h3 { margin: 0 0 10px; font-size: .9rem; color: var(--accent); }
            #mf-save-box label { display: block; margin: 8px 0 3px; color: var(--dim); }
            #mf-save-box select, #mf-save-box input {
                width: 100%; box-sizing: border-box; padding: 4px 6px;
                background: #0b0f14; color: var(--text);
                border: 1px solid var(--border); border-radius: 4px; font-size: .82rem;
            }
            #mf-save-msg { margin-top: 8px; font-size: .76rem; min-height: 1em; }
            #mf-save-msg.err { color: #ff8a8a; }
            #mf-save-msg.ok { color: #7ee787; }
            #mf-save-actions { margin-top: 12px; display: flex; gap: 8px; justify-content: flex-end; }
            #mf-save-actions button { padding: 4px 10px; }
        `;
        document.head.appendChild(s);
    }

    function ensureButton() {
        if (document.getElementById("btn-preset-save")) return;
        const bar = document.querySelector(".toolbar") || document.getElementById("toolbar");
        const up = document.getElementById("btn-upload");
        const b = document.createElement("button");
        b.id = "btn-preset-save";
        b.textContent = "💾 保存预设";
        b.title = "把当前画布保存为预设(可覆盖已有预设或另存为新预设)";
        if (up && up.parentElement) up.parentElement.insertBefore(b, up.nextSibling);
        else if (bar) bar.appendChild(b);
        b.onclick = open;
    }

    function ensureDialog() {
        if (document.getElementById("mf-save-mask")) return;
        const mask = document.createElement("div");
        mask.id = "mf-save-mask";
        mask.innerHTML =
            '<div id="mf-save-box">' +
            '<h3>💾 保存预设</h3>' +
            '<label>目标</label><select id="mf-save-target"></select>' +
            '<label>名称(显示在引导页卡片上)</label>' +
            '<input id="mf-save-name" type="text" placeholder="例如:我的教学版">' +
            '<label>说明(可选)</label>' +
            '<input id="mf-save-desc" type="text" placeholder="一句话说明这张图看什么">' +
            '<div id="mf-save-msg"></div>' +
            '<div id="mf-save-actions">' +
            '<button id="mf-save-cancel">取消</button>' +
            '<button id="mf-save-ok" class="primary">保存</button>' +
            '</div></div>';
        document.body.appendChild(mask);
        mask.addEventListener("click", (e) => { if (e.target === mask) close(); });
        document.getElementById("mf-save-cancel").onclick = close;
        document.getElementById("mf-save-ok").onclick = save;
        document.getElementById("mf-save-target").onchange = syncFields;
        document.addEventListener("keydown", (e) => {
            if (e.key === "Escape" && mask.classList.contains("open")) close();
        });
    }

    function presets() {
        try { return (window.launcher && window.launcher.presets) ? window.launcher.presets() : []; }
        catch (e) { return []; }
    }

    function fillTargets() {
        const sel = document.getElementById("mf-save-target");
        const list = presets() || [];
        sel.innerHTML = "";
        const oNew = document.createElement("option");
        oNew.value = NEW;
        oNew.textContent = "另存为新预设";
        sel.appendChild(oNew);
        for (const p of list) {
            const o = document.createElement("option");
            o.value = p.id;
            o.textContent = "覆盖:" + (p.name || p.id);
            sel.appendChild(o);
        }
        sel.value = NEW;
    }

    function syncFields() {
        const sel = document.getElementById("mf-save-target");
        const name = document.getElementById("mf-save-name");
        const desc = document.getElementById("mf-save-desc");
        const hit = (presets() || []).find(p => p.id === sel.value);
        name.value = hit ? (hit.name || hit.id) : "";
        desc.value = hit ? (hit.desc || "") : "";
        setMsg("", "");
    }

    function setMsg(text, cls) {
        const m = document.getElementById("mf-save-msg");
        m.textContent = text || "";
        m.className = cls || "";
    }

    function open() {
        ensureDialog();
        fillTargets();
        syncFields();
        document.getElementById("mf-save-mask").classList.add("open");
        document.getElementById("mf-save-name").focus();
    }
    function close() {
        const m = document.getElementById("mf-save-mask");
        if (m) m.classList.remove("open");
    }

    async function save() {
        const sel = document.getElementById("mf-save-target").value;
        const name = document.getElementById("mf-save-name").value.trim();
        const desc = document.getElementById("mf-save-desc").value.trim();
        if (!name) { setMsg("请填写名称", "err"); return; }
        let doc;
        try {
            doc = window.editor.exportGraph();
        } catch (e) {
            setMsg("无法读取画布:" + e, "err");
            return;
        }
        const body = { mode: sel === NEW ? "saveas" : "overwrite",
                       preset: { name: name, desc: desc, sort: 50 },
                       graph: doc };
        if (sel !== NEW) body.id = sel;
        const btn = document.getElementById("mf-save-ok");
        btn.disabled = true;
        setMsg("保存中…(写盘前会在服务器上跑一次图校验)", "");
        try {
            const r = await fetch("/api/preset", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body),
            });
            const j = await r.json().catch(() => ({}));
            if (r.ok && j.ok) {
                setMsg("已保存 ✓ id=" + j.id + "(校验:" + (j.validate && j.validate.slots || []).join("/") + ")", "ok");
                if (window.uiLog) window.uiLog("info", "preset_save", "已保存预设 " + j.id,
                                               { id: j.id, mode: j.mode });
                // 列表刷新(launcher 导出 fetchPresets;没有就下次打开时自然重取)
                if (window.launcher && window.launcher.fetchPresets) {
                    try { await window.launcher.fetchPresets(); } catch (e) { /* 忽略 */ }
                }
                setTimeout(close, 900);
            } else {
                const d = j.detail || {};
                const why = j.error ||
                    [].concat(d.errors || [], d.warnings || []).join("; ") || "保存被拒绝";
                setMsg("未保存:" + why, "err");
                if (window.uiLog) window.uiLog("warn", "preset_save_rejected", why, d);
            }
        } catch (e) {
            setMsg("请求失败:" + e, "err");
        } finally {
            btn.disabled = false;
        }
    }

    function init() {
        injectStyle();
        ensureButton();
        ensureDialog();
    }
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else { init(); }
    window.addEventListener("load", () => setTimeout(init, 400));
    window.presetSave = { open, close, save };     // 供自动化测试调用
})();
