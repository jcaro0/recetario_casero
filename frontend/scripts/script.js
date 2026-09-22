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

function shareText(text, type) {
    switch (type) {
        case "copy":
            navigator.clipboard.writeText(text);
            alert("Copiado al portapapeles");
            break;
        case "whatsapp":
            window.open("https://wa.me/?text=" + encodeURIComponent(text));
            break;
        case "email":
            window.location = "mailto:?subject=Menú Semanal&body=" + encodeURIComponent(text);
            break;
    }
}

// Formateador común para ingredientes
function formatQtyUnit(qty, unit) {
    if (qty === null || qty === undefined || qty === "") return "";
    return ` - ${qty}${unit ? " " + unit : ""}`;
}

// Inicialización de elementos comunes
document.addEventListener("DOMContentLoaded", () => {
    setupShareDropdown();
});