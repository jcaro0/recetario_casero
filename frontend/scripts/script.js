// =======================================================
// UTILIDADES GLOBALES Y TRANSICIONES
// =======================================================

// Evita saltos de scroll al navegar con View Transitions
document.addEventListener("click", (e) => {
    const link = e.target.closest("a[href]");
    if (!link) return;
    if (link.target === "_blank") return;
    let url;
    try {
        url = new URL(link.href, location.href);
    } catch {
        return;
    }
    if (url.origin !== location.origin) return;
    window.scrollTo(0, 0);
});

// Dropdown de compartir en la cabecera
function setupShareDropdown() {
    const button = document.getElementById("shareMenuButton");
    const dropdown = document.getElementById("shareDropdown");
    if (!button || !dropdown) return;

    button.onclick = () => {
        dropdown.classList.toggle("hidden");
    };

    document.addEventListener("click", (e) => {
        if (!dropdown.contains(e.target) && !button.contains(e.target)) {
            dropdown.classList.add("hidden");
        }
    });
}

function shareText(text, type, subject = "Menú Semanal") {
    switch (type) {
        case "copy":
            navigator.clipboard.writeText(text);
            alert("Copiado al portapapeles");
            break;
        case "whatsapp":
            window.open("https://wa.me/?text=" + encodeURIComponent(text));
            break;
        case "email":
            window.location = "mailto:?subject=" + encodeURIComponent(subject) +
                "&body=" + encodeURIComponent(text);
            break;
    }
}

// Formateador común para ingredientes
function formatQtyUnit(qty, unit) {
    if (qty === null || qty === undefined || qty === "") return "";
    return ` - ${qty}${unit ? " " + unit : ""}`;
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

// fetch + JSON que lanza un Error con el mensaje del servidor si la respuesta no es OK
async function api(url, options) {
    const res = await fetch(url, options);
    let data = null;
    try {
        data = await res.json();
    } catch {
        // respuesta sin cuerpo JSON
    }
    if (!res.ok) {
        throw new Error((data && data.error) || "Error del servidor");
    }
    return data;
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

// Inicialización de elementos comunes
document.addEventListener("DOMContentLoaded", () => {
    setupShareDropdown();
});