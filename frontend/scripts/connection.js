const READ_ONLY = "Esta acción requiere conexión con Recetario.";
const MISSING_COPY = "Estos datos aún no están disponibles sin conexión.";
const SNAPSHOT_KEYS = {
    "/recipes": "recipes", "/menu": "menu", "/shopping-list": "shopping",
    "/days": "days", "/menu/status": "status", "/menu/people": "people"
};

let snapshot = null;
let access = "checking";
let loss = 0;
let initialized;
let refreshing;
let retryTimer;
let bannerTimer;

function canWrite() {
    return access === "online" && navigator.onLine !== false;
}

function applyWriteAccess() {
    const locked = !canWrite();
    document.documentElement.toggleAttribute("data-readonly", locked);
    document.querySelectorAll("[data-write]").forEach(element => {
        const hasDisabled = "disabled" in element;
        // Los controles nativos deshabilitados siguen exponiendo su texto y valor.
        element.toggleAttribute("inert", locked && (!hasDisabled || element.matches("fieldset")));
        if (locked) element.setAttribute("aria-disabled", "true");
        else element.removeAttribute("aria-disabled");
        if (!hasDisabled) return;
        if (locked && !element.disabled) {
            element.disabled = true;
            element.dataset.connectionDisabled = "";
        } else if (!locked && element.hasAttribute("data-connection-disabled")) {
            element.disabled = false;
            delete element.dataset.connectionDisabled;
        }
    });
    document.querySelectorAll("[data-write-drag]").forEach(element => { element.draggable = !locked; });
}

function setAccess(next) {
    if (access === next) return;
    const recovered = next === "online" && access !== "checking";
    access = next;
    applyWriteAccess();
    const banner = byId("connectionStatus");
    clearTimeout(bannerTimer);
    banner.classList.remove("fading");
    banner.classList.toggle("hidden", next === "online" && !recovered);
    if (next === "online") {
        if (recovered) {
            banner.textContent = "Ya tienes conexión";
            bannerTimer = setTimeout(() => {
                banner.classList.add("fading");
                bannerTimer = setTimeout(() => banner.classList.add("hidden"), 250);
            }, 2500);
        }
    } else {
        loss++;
        banner.textContent = next === "offline"
            ? "Sin conexión · Modo de solo lectura"
            : "No se pudieron actualizar los datos · Modo de solo lectura";
        document.dispatchEvent(new Event("recetario:locked"));
    }
    scheduleConnectionCheck();
}

function snapshotStorage(value) {
    return new Promise((resolve, reject) => {
        const writing = value !== undefined;
        const request = indexedDB.open("recetario-lectura", 1);
        request.onupgradeneeded = () => {
            if (writing) request.result.createObjectStore("snapshot");
            else request.transaction.abort();
        };
        request.onerror = () => reject(request.error);
        request.onsuccess = () => {
            const db = request.result;
            const transaction = db.transaction("snapshot", writing ? "readwrite" : "readonly");
            const store = transaction.objectStore("snapshot");
            const operation = writing ? store.put(value, "latest") : store.get("latest");
            transaction.oncomplete = () => { db.close(); resolve(operation.result); };
            transaction.onabort = () => { db.close(); reject(transaction.error); };
        };
    });
}

async function requestJson(url, method = "GET", body, timeout = 6000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    const options = { method, cache: "no-store", signal: controller.signal };
    if (body !== undefined) {
        options.headers = { "Content-Type": "application/json" };
        options.body = JSON.stringify(body);
    }
    try {
        const response = await fetch(url, options);
        const data = await response.json().catch(() => null);
        if (!response.ok || data === null) {
            const error = new Error(data?.error || "Error del servidor");
            error.status = response.status;
            throw error;
        }
        return data;
    } finally {
        clearTimeout(timer);
    }
}

function isSnapshot(data) {
    return data && Array.isArray(data.recipes) && Array.isArray(data.shopping) && Array.isArray(data.days)
        && data.menu && typeof data.status?.enough === "boolean" && Number.isInteger(data.people);
}

function refreshSnapshot(redraw = false) {
    if (refreshing) return refreshing;
    refreshing = (async () => {
        if (navigator.onLine === false) {
            setAccess("offline");
            return;
        }
        const attempt = loss;
        try {
            const data = await requestJson("/snapshot");
            if (attempt !== loss || navigator.onLine === false) return;
            if (!isSnapshot(data)) {
                setAccess("stale");
                return;
            }
            // La caché solo recibe lecturas válidas del servidor, incluso tras una escritura.
            await snapshotStorage(data).catch(() => {});
            if (attempt !== loss || navigator.onLine === false) return;
            snapshot = data;
            if (redraw || access === "offline" || access === "stale") {
                document.dispatchEvent(new CustomEvent("recetario:refreshed", {
                    detail: { recovered: access !== "online" }
                }));
            }
            setAccess("online");
        } catch (error) {
            if (attempt === loss) setAccess(error.status ? "stale" : "offline");
        }
    })().finally(() => { refreshing = null; });
    return refreshing;
}

function initializeSnapshot() {
    initialized ??= (async () => {
        const saved = await snapshotStorage().catch(() => null);
        if (isSnapshot(saved)) snapshot = saved;
        await refreshSnapshot();
    })();
    return initialized;
}

async function probeServer() {
    if (navigator.onLine === false) {
        setAccess("offline");
        return false;
    }
    try {
        if ((await requestJson("/connection", "GET", undefined, 2500)).ok === true) return true;
        setAccess("stale");
    } catch (error) {
        setAccess(error.status ? "stale" : "offline");
    }
    return false;
}

async function api(url, method = "GET", body) {
    if (method === "GET") {
        const key = SNAPSHOT_KEYS[url];
        const recipeId = url.match(/^\/recipes\/(\d+)$/)?.[1];
        if (key || recipeId) {
            await initializeSnapshot();
            if (!snapshot) throw new Error(MISSING_COPY);
            if (key) return url === "/menu/people" ? { people: snapshot.people } : snapshot[key];
            const recipe = snapshot.recipes.find(item => item.id === Number(recipeId));
            if (!recipe) throw new Error(canWrite() ? "Receta no encontrada" : MISSING_COPY);
            return recipe;
        }
        try {
            return await requestJson(url);
        } catch (error) {
            if (!error.status) setAccess("offline");
            throw error;
        }
    }

    // Una acción iniciada con el acceso bloqueado acaba aquí. No se aplaza ni
    // se repite. El sondeo detecta también la caída de la Pi con el Wi-Fi activo.
    const attempt = loss;
    if (refreshing && canWrite()) await refreshing;
    if (!canWrite() || attempt !== loss || !await probeServer() || !canWrite() || attempt !== loss) {
        throw new Error(READ_ONLY);
    }

    let result;
    try {
        result = await requestJson(url, method, body);
    } catch (error) {
        if (error.status) throw error;
        setAccess("offline");
        throw new Error("No se pudo confirmar la operación. Comprueba los datos al recuperar la conexión.");
    }
    if (url !== "/recipes/check-duplicate") {
        // Una lectura que empezó antes de esta escritura no puede confirmarla.
        if (refreshing) await refreshing;
        await refreshSnapshot();
    }
    return result;
}

function scheduleConnectionCheck() {
    clearTimeout(retryTimer);
    if (document.hidden) return;
    retryTimer = setTimeout(async () => {
        if (canWrite()) await probeServer();
        else await refreshSnapshot(true);
        scheduleConnectionCheck();
    }, canWrite() ? 45000 : 12000);
}

async function resumeConnection() {
    await initializeSnapshot();
    await refreshSnapshot(true);
    scheduleConnectionCheck();
}

document.addEventListener("DOMContentLoaded", () => {
    applyWriteAccess();
    initializeSnapshot().then(scheduleConnectionCheck);
});
window.addEventListener("offline", () => setAccess("offline"));
window.addEventListener("online", resumeConnection);
window.addEventListener("pageshow", event => { if (event.persisted) resumeConnection(); });
document.addEventListener("visibilitychange", () => {
    if (document.hidden) clearTimeout(retryTimer);
    else resumeConnection();
});

// Complementa la desactivación de controles y cubre enlaces y envíos sintéticos.
for (const eventName of ["click", "submit"]) {
    document.addEventListener(eventName, event => {
        if (!canWrite() && event.target.closest("[data-write], [data-write-drag]")) {
            event.preventDefault();
            event.stopImmediatePropagation();
        }
    }, true);
}
