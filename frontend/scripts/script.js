const byId = id => document.getElementById(id);

if (window.isSecureContext && "serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js", { updateViaCache: "none" })
        .catch(error => console.warn("No se pudo preparar Recetario para instalar:", error));
}

const TOAST_KEY = "recetario-notice";
let toastTimer;
let toastTrigger;

function dismissToast(restoreFocus = false) {
    clearTimeout(toastTimer);
    byId("toast").hidden = true;
    byId("noticeStatus").textContent = "";
    byId("noticeError").textContent = "";
    if (restoreFocus && toastTrigger?.isConnected && !toastTrigger.matches("body")
        && !toastTrigger.closest("[inert], :disabled")) {
        toastTrigger.focus({ preventScroll: true });
    } else if (restoreFocus) {
        document.querySelector(".nav-link.active").focus({ preventScroll: true });
    }
}

function scheduleToastDismissal() {
    clearTimeout(toastTimer);
    const toast = byId("toast");
    if (!toast.matches(":hover, :focus-within")) {
        toastTimer = setTimeout(() => dismissToast(), toast.dataset.kind === "error" ? 11000 : 7000);
    }
}

function notify(message, kind = "info") {
    const toast = byId("toast");
    if (!toast.contains(document.activeElement)) toastTrigger = document.activeElement;
    toast.dataset.kind = kind;
    byId("toastIcon").textContent = { success: "✓", error: "!", info: "i" }[kind];
    byId("toastMessage").textContent = message;
    byId("noticeStatus").textContent = "";
    byId("noticeError").textContent = "";
    byId(kind === "error" ? "noticeError" : "noticeStatus").textContent = message;
    toast.hidden = false;
    scheduleToastDismissal();
}

function navigateWithNotice(destination, message) {
    try {
        sessionStorage.setItem(TOAST_KEY, JSON.stringify({
            path: new URL(destination, location.href).pathname, message, expires: Date.now() + 60000
        }));
    } catch {
        notify(message, "success");
        return;
    }
    location.assign(destination);
}

function consumeNotice() {
    try {
        const notice = JSON.parse(sessionStorage.getItem(TOAST_KEY));
        if (notice?.path === location.pathname) {
            sessionStorage.removeItem(TOAST_KEY);
            if (Date.now() < notice.expires) notify(notice.message, "success");
        }
    } catch {
        // La sesión puede estar deshabilitada por el navegador.
    }
}

document.addEventListener("DOMContentLoaded", () => {
    const toast = byId("toast");
    byId("dismissToast").onclick = () => dismissToast(true);
    toast.addEventListener("mouseenter", () => clearTimeout(toastTimer));
    toast.addEventListener("focusin", () => clearTimeout(toastTimer));
    toast.addEventListener("mouseleave", scheduleToastDismissal);
    toast.addEventListener("focusout", scheduleToastDismissal);
    consumeNotice();
});
window.addEventListener("pagehide", () => dismissToast());

const dialogTriggers = new WeakMap();

function fitDialogToViewport() {
    const dialog = document.querySelector(".modal[open]");
    if (!dialog || !window.visualViewport) return;
    const { height, offsetTop } = window.visualViewport;
    dialog.style.setProperty("--dialog-height", `${height}px`);
    dialog.style.setProperty("--dialog-top", `${offsetTop}px`);
    dialog.style.setProperty("--dialog-bottom", `${Math.max(0, innerHeight - height - offsetTop)}px`);
}

window.visualViewport?.addEventListener("resize", fitDialogToViewport);
window.visualViewport?.addEventListener("scroll", fitDialogToViewport);

function openDialog(dialog, trigger) {
    if (document.querySelector(".modal[open]")) return false;
    dialogTriggers.set(dialog, trigger);
    dialog.querySelectorAll(".dialog-error, .dialog-progress").forEach(node => { node.textContent = ""; });
    dialog.showModal();
    fitDialogToViewport();
    return true;
}

document.querySelectorAll(".modal").forEach(dialog => {
    const close = () => { if (!dialog.hasAttribute("aria-busy")) dialog.close(); };
    dialog.querySelectorAll("[data-dialog-close]").forEach(button => { button.onclick = close; });
    let backdropPress = false;
    dialog.addEventListener("pointerdown", event => { backdropPress = event.target === dialog; });
    dialog.addEventListener("click", event => {
        if (event.target === dialog && backdropPress) close();
        backdropPress = false;
    });
    dialog.addEventListener("cancel", event => {
        if (dialog.hasAttribute("aria-busy")) event.preventDefault();
    });
    dialog.addEventListener("keydown", event => {
        if (event.key !== "Tab") return;
        const controls = [...dialog.querySelectorAll("button, a[href], input, textarea")]
            .filter(control => !control.disabled && control.getClientRects().length);
        const edge = event.shiftKey ? controls.at(0) : controls.at(-1);
        if (edge && document.activeElement !== edge) return;
        event.preventDefault();
        (event.shiftKey ? controls.at(-1) : controls.at(0))?.focus();
    });
    dialog.addEventListener("close", () => {
        if (dialog.open) return;
        const trigger = dialogTriggers.get(dialog);
        if (trigger?.isConnected && !trigger.closest("[inert], :disabled") && trigger.getClientRects().length) {
            trigger.focus({ preventScroll: true });
        } else if (document.activeElement === document.body) {
            document.querySelector(".nav-link.active").focus({ preventScroll: true });
        }
    });
});

document.addEventListener("recetario:locked", () => {
    document.querySelectorAll(".modal[data-write-dialog][open]:not([aria-busy])").forEach(dialog => dialog.close());
});

async function runDialogAction(dialog, action, trigger, progress, errorPrefix) {
    if (!dialog.open || dialog.hasAttribute("aria-busy")) return false;
    const error = dialog.querySelector(".dialog-error");
    const status = dialog.querySelector(".dialog-progress");
    if (!canWrite()) {
        error.textContent = READ_ONLY;
        return false;
    }
    const controls = [...dialog.querySelectorAll("button:enabled, input:enabled")];
    dialog.setAttribute("aria-busy", "true");
    error.textContent = "";
    status.textContent = progress;
    status.focus({ preventScroll: true });
    controls.forEach(control => { control.disabled = true; });
    try {
        await action();
        dialog.close();
        return true;
    } catch (failure) {
        const message = errorPrefix + failure.message;
        if (canWrite()) error.textContent = message;
        else {
            dialog.close();
            notify(message, "error");
        }
        return false;
    } finally {
        dialog.removeAttribute("aria-busy");
        controls.forEach(control => { control.disabled = false; });
        status.textContent = "";
        if (dialog.open) trigger?.focus({ preventScroll: true });
    }
}

function confirmAction({ title, message, label, trigger, destructive = false, number, action, onSuccess,
    progress = "Guardando…", errorPrefix = "No se pudo completar la operación. " }) {
    if (!canWrite()) return;
    const dialog = byId("actionDialog");
    if (document.querySelector(".modal[open]")) return;
    const input = byId("actionNumber");
    const confirm = byId("actionConfirm");
    byId("actionTitle").textContent = title;
    byId("actionDescription").textContent = message;
    confirm.textContent = label;
    confirm.className = destructive ? "danger" : "primary";
    byId("actionNumberField").hidden = !number;
    byId("actionNumberLabel").textContent = number?.label || "";
    input.disabled = !number;
    input.value = number?.value ?? "";
    byId("actionForm").onsubmit = event => {
        event.preventDefault();
        // Enter desde el campo numérico deja la decisión en el botón visible.
        if (number && document.activeElement === input) {
            confirm.focus();
            return;
        }
        runDialogAction(dialog, () => action(number ? Number(input.value) : undefined),
            confirm, progress, errorPrefix).then(success => { if (success) onSuccess?.(); });
    };
    openDialog(dialog, trigger);
}

let sharing = false;

async function shareContent(title, text, trigger) {
    if (sharing || byId("shareDialog").open) return;
    if (!text) {
        notify("Todavía no hay contenido para compartir.");
        return;
    }
    const data = { title, text };
    let hint = "";
    try {
        if (navigator.share && (!navigator.canShare || navigator.canShare(data))) {
            sharing = true;
            await navigator.share(data);
            return;
        }
    } catch (error) {
        if (error.name === "AbortError") return;
        hint = "Puedes compartir el texto con estas opciones.";
    } finally {
        sharing = false;
    }
    const dialog = byId("shareDialog");
    byId("shareTitle").textContent = title;
    const preview = byId("sharePreview");
    preview.value = text;
    byId("shareHint").textContent = hint;
    const whatsapp = dialog.querySelector('[data-share="whatsapp"]');
    whatsapp.href = "https://wa.me/?text=" + encodeURIComponent(text);
    const email = dialog.querySelector('[data-share="email"]');
    email.href = "mailto:?subject=" + encodeURIComponent(title) + "&body=" + encodeURIComponent(text);
    const copy = dialog.querySelector('[data-share="copy"]');
    copy.onclick = async () => {
        if (sharing) return;
        sharing = true;
        try {
            await navigator.clipboard.writeText(text);
            dialog.close();
            notify("Texto copiado al portapapeles", "success");
        } catch {
            if (dialog.open) {
                preview.focus();
                preview.select();
                byId("shareHint").textContent = "Texto seleccionado. Usa la opción Copiar de tu dispositivo.";
            }
        } finally {
            sharing = false;
        }
    };
    openDialog(dialog, trigger);
}

// Formateador común para ingredientes
function formatQtyUnit(qty, unit) {
    if (qty === null || qty === undefined || qty === "") return "";
    return `${qty}${unit ? " " + unit : ""}`;
}

// Escapa texto antes de meterlo en innerHTML (evita inyectar HTML desde nombres de recetas)
function escapeHtml(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

// Etiqueta visual del tipo de receta
const TYPE_LABELS = {
    ambos: "Ambos",
    comida: "Comida",
    cena: "Cena",
    extra: "Extra"
};

function typeBadge(type) {
    const t = TYPE_LABELS[type] ? type : "ambos";
    return `<span class="type-badge type-${t}">${TYPE_LABELS[t]}</span>`;
}

// Ilustración compartida de los estados vacíos.
const EMPTY_IMAGE = "img/sin_recetas.png";

function emptyStateHtml(message) {
    return `
        <div class="empty-state">
            <img src="${EMPTY_IMAGE}" alt="" onerror="this.style.display='none'">
            <p>${escapeHtml(message)}</p>
        </div>
    `;
}
