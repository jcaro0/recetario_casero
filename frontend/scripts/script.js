const byId = id => document.getElementById(id);

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
function setupShareDropdown(share) {
    const button = byId("shareMenuButton");
    const dropdown = byId("shareDropdown");
    button.onclick = () => dropdown.classList.toggle("hidden");
    dropdown.onclick = event => {
        const option = event.target.closest("[data-share]");
        if (option) share(option.dataset.share);
    };
    document.addEventListener("click", event => {
        if (!dropdown.contains(event.target) && !button.contains(event.target)) {
            dropdown.classList.add("hidden");
        }
    });
}

function dismissModalOnBackdropOrEscape(id, close) {
    const modal = byId(id);
    modal.addEventListener("click", event => {
        if (event.target === modal) close();
    });
    document.addEventListener("keydown", event => {
        if (event.key === "Escape" && !modal.classList.contains("hidden")) close();
    });
}

function shareText(text, type, subject) {
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
function formatQtyUnit(qty, unit, prefix = "") {
    if (qty === null || qty === undefined || qty === "") return "";
    return `${prefix}${qty}${unit ? " " + unit : ""}`;
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
async function api(url, method = "GET", body) {
    const options = { method };
    if (body !== undefined) {
        options.headers = { "Content-Type": "application/json" };
        options.body = JSON.stringify(body);
    }
    const res = await fetch(url, options);
    const data = await res.json().catch(() => null);
    if (!res.ok) throw new Error(data?.error || "Error del servidor");
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

// Estado vacío compartido (menú, compra, recetas): tu imagen y el mensaje centrado debajo.
// Guarda la imagen en frontend/img/sin_recetas.png (o cambia la ruta aquí).
const EMPTY_IMAGE = "img/sin_recetas.png";

function emptyStateHtml(message) {
    return `
        <div class="empty-state">
            <img src="${EMPTY_IMAGE}" alt="" onerror="this.style.display='none'">
            <p>${escapeHtml(message)}</p>
        </div>
    `;
}
