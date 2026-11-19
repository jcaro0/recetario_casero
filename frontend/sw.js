// Cambia la versión al publicar recursos nuevos. El cambio se activa al cerrar
// las páginas anteriores, para evitar mezclar HTML y JavaScript de dos versiones.
const SHELL_CACHE = "recetario-shell-v2";
const SHELL_FILES = new Set([
    "/", "/menu.html", "/recetas.html", "/agregar_recetas.html", "/lista_compra.html",
    "/manifest.webmanifest", "/img/recetario-180.png", "/img/recetario-192.png",
    "/img/recetario-512.png", "/img/sin_recetas.png", "/fonts/material-symbols.woff2",
    "/style/style.css", "/style/menu.css", "/style/recetas.css", "/style/agregar_recetas.css",
    "/style/lista_compra.css", "/scripts/script.js", "/scripts/menu.js", "/scripts/recetas.js",
    "/scripts/agregar_recetas.js", "/scripts/lista_compra.js", "/scripts/connection.js"
]);

self.addEventListener("install", event => {
    event.waitUntil(caches.open(SHELL_CACHE).then(cache =>
        cache.addAll([...SHELL_FILES].map(path => new Request(path, { cache: "reload" })))
    ));
});

self.addEventListener("activate", event => {
    event.waitUntil((async () => {
        for (const name of await caches.keys()) {
            if (name.startsWith("recetario-shell-") && name !== SHELL_CACHE) await caches.delete(name);
        }
        await self.clients.claim();
    })());
});

self.addEventListener("fetch", event => {
    const { request } = event;
    const url = new URL(request.url);
    if (request.method !== "GET" || url.origin !== self.location.origin || !SHELL_FILES.has(url.pathname)) return;
    event.respondWith((async () => {
        const cache = await caches.open(SHELL_CACHE);
        return await cache.match(url.pathname) || fetch(request);
    })());
});
