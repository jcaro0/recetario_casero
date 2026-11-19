"""Prueba integral con Chromium y una BD temporal (requiere Playwright solo para pruebas).

    PYTHONPATH=backend python3 tests/browser_recipes.py
    CHROMIUM_PATH=/usr/bin/chromium PYTHONPATH=backend python3 tests/browser_recipes.py
"""
import os
import re
import shutil
import struct
import tempfile
import threading
from pathlib import Path

from flask import Response, request
from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server
import database as db
from main import app


def capture(page, path):
    page.evaluate("async () => { await document.fonts.ready; }")
    page.wait_for_function("() => !document.getAnimations().some(animation => animation.playState === 'running')")
    page.screenshot(path=str(path), full_page=True, animations="disabled")


def check_pwa(browser, base, results, next_release):
    context = browser.new_context(viewport={"width": 375, "height": 812})
    page = context.new_page()
    page.goto(base + "/")
    expect(page.get_by_role("heading", name="Tu menú de esta semana")).to_be_visible()
    page.wait_for_function("() => Boolean(navigator.serviceWorker.controller)")
    icon = page.locator(".nav-link .material-symbols-rounded").first
    assert icon.evaluate("""async element => {
        await document.fonts.ready;
        return getComputedStyle(element).fontFamily.includes("Material Symbols Rounded")
            && document.fonts.check('24px "Material Symbols Rounded"')
            && element.scrollWidth <= element.clientWidth + 1;
    }"""), "La fuente local debe renderizar la ligadura del icono"
    assert page.locator('link[rel="manifest"]').get_attribute("href") == "/manifest.webmanifest"
    manifest = page.request.get(base + "/manifest.webmanifest")
    assert manifest.headers["content-type"].startswith("application/manifest+json")
    config = manifest.json()
    assert (config["name"], config["start_url"], config["scope"], config["display"]) == (
        "Recetario", "/", "/", "standalone")
    icons = [(icon["src"], int(icon["sizes"].split("x")[0])) for icon in config["icons"]]
    icons.append((page.locator('link[rel="apple-touch-icon"]').get_attribute("href"), 180))
    for path, size in icons:
        response = page.request.get(base + path)
        assert response.ok and response.headers["content-type"] == "image/png"
        assert struct.unpack(">II", response.body()[16:24]) == (size, size)
    assert page.request.get(base + "/sw.js").headers["cache-control"] == "no-cache"
    for path in ("recetas.html", "lista_compra.html", "agregar_recetas.html", "menu.html"):
        page.locator(f'nav a[href="{path}"]').click()
        expect(page.locator(".nav-link.active")).to_have_attribute("href", path)
    capture(page, results / "pwa-mobile.png")

    # Simula publicar un worker y recursos nuevos sin escribir archivos de la app.
    next_release.set()
    try:
        page.evaluate("""async () => {
            window.testRegistration = await navigator.serviceWorker.ready;
            await window.testRegistration.update();
        }""")
        page.wait_for_function("() => Boolean(window.testRegistration.waiting)")
        storage = page.evaluate("""async () => {
            const names = await caches.keys();
            const cached = await caches.match(location.origin + "/style/menu.css",
                { cacheName: "recetario-shell-test-release" });
            return { names, updated: Boolean(cached && (await cached.text()).includes("release de prueba")) };
        }""")
        assert storage["updated"], storage
        page.close()
        page = context.new_page()
        page.goto(base + "/")
        assert page.evaluate("""async () => {
            for (let attempt = 0; attempt < 50; attempt++) {
                const keys = (await caches.keys()).filter(key => key.startsWith("recetario-shell-"));
                if (keys.length === 1 && keys[0] === "recetario-shell-test-release") return true;
                await new Promise(resolve => setTimeout(resolve, 100));
            }
            return false;
        }"""), "La versión nueva no se activó después de cerrar la anterior"
    finally:
        next_release.clear()
        context.close()
    print("OK: manifest, iconos, Service Worker, navegación móvil y actualización de recursos")


def check_offline(browser, base, results, unavailable_snapshot):
    admin_context = browser.new_context()
    admin = admin_context.request
    recipe = {"name": "Desde casa", "servings": 2, "preparation": ["Hornear"],
              "notes": "Una nota para leer", "ingredients": [{"name": "Pimiento", "qty": 2, "unit": "uds"}]}
    recipe_id = admin.post(base + "/recipes", data=recipe).json()["id"]
    recipe_url = f"/recipes/{recipe_id}"
    day = db.DAYS[0]
    admin.post(base + f"/menu/{day}/comida", data={"recipe_id": recipe_id, "people": 4})
    product_id = admin.post(base + "/shopping-list/manual", data={
        "name": "Papel de cocina", "qty": 1, "unit": "paquete"
    }).json()["manual_id"]
    product_url = f"/shopping-list/manual/{product_id}"
    admin.patch(base + product_url, data={"checked": True})

    context = browser.new_context(viewport={"width": 375, "height": 812})
    page = context.new_page()
    errors = []
    writes = []
    context.on("request", lambda req: writes.append((req.method, req.url))
               if req.method not in ("GET", "HEAD", "OPTIONS") else None)

    def observe_errors(tab):
        tab.on("pageerror", lambda error: errors.append(str(error)) if str(error) != "Transition was skipped" else None)
        tab.on("console", lambda message: errors.append(message.text) if message.type == "error"
               and not message.text.startswith("Failed to load resource:") else None)

    observe_errors(page)
    banner = page.locator("#connectionStatus")
    try:
        page.goto(base + "/")
        expect(page.locator(".meal-slot .food").first).to_contain_text("Desde casa")
        expect(page.locator("#generateButton")).to_be_enabled()
        page.wait_for_function("() => Boolean(navigator.serviceWorker.controller)")
        expect(page.locator("#connectionStatus")).to_be_hidden()
        page.locator("#generateButton").click()
        expect(page.locator("#actionDialog")).to_be_visible()
        context.set_offline(True)
        expect(banner).to_have_text("Sin conexión · Modo de solo lectura")
        expect(page.locator("#actionDialog")).to_be_hidden()
        page.reload()
        expect(banner).to_be_visible()
        expect(page.locator(".meal-slot .food").first).to_contain_text("Desde casa")
        person = page.locator(".slot-people input").first
        expect(person).to_have_value("4")
        expect(person).to_be_disabled()
        expect(page.locator("#weekPeople")).to_be_disabled()
        expect(page.locator("#generateButton")).to_be_disabled()
        expect(page.locator(".meal-slot").first).to_have_attribute("draggable", "false")
        expect(page.locator(".meal-slot .food").first).to_be_disabled()
        page.locator(".meal-slot .meal-label").first.click()
        expect(page.locator("#chooseRecipeModal")).to_be_hidden()
        page.evaluate("window.scrollTo(0, 600)")
        header = page.locator(".topbar").bounding_box()
        notice = banner.bounding_box()
        assert header["y"] + header["height"] <= notice["y"] < 812
        page.evaluate("window.scrollTo(0, 0)")
        capture(page, results / "offline-menu-mobile.png")

        page.locator('nav a[href="recetas.html"]').click()
        page.locator("#catalogSearch").fill("desde")
        card = page.locator(".recipe-card")
        expect(card).to_have_count(1)
        card.locator(".recipe-card-header").click()
        expect(card).to_contain_text("Hornear")
        expect(card).to_contain_text("Una nota para leer")
        expect(card).to_contain_text("Pimiento")
        expect(card.locator(".editRecipe")).to_be_disabled()
        expect(card.locator(".deleteRecipe")).to_be_disabled()
        capture(page, results / "offline-recetas-mobile.png")
        page.goto(base + f"/agregar_recetas.html?id={recipe_id}")
        expect(page.locator("#recipeName")).to_have_value("Desde casa")
        expect(page.locator("#recipeName")).to_be_disabled()
        expect(page.locator(".submitButton")).to_be_disabled()
        page.goto(base + "/agregar_recetas.html")
        expect(page.locator(".submitButton")).to_be_disabled()
        expect(page.locator("#addStep")).to_be_disabled()

        page.locator('nav a[href="lista_compra.html"]').click()
        product = page.locator(".shopping-item").filter(has_text="Papel de cocina")
        expect(product).to_contain_text("1 paquete")
        expect(product.locator("input")).to_be_checked()
        expect(product.locator("input")).to_be_disabled()
        expect(product.locator('[data-action="delete"]')).to_be_disabled()
        expect(product.locator('[data-action="edit"]')).to_be_disabled()
        expect(page.locator("#manualSubmit")).to_be_disabled()
        product.locator("input").evaluate("""box => {
            box.checked = false;
            box.dispatchEvent(new Event("change", {bubbles: true}));
        }""")
        expect(product.locator("input")).to_be_checked()
        capture(page, results / "offline-compra-mobile.png")
        before = page.evaluate("async () => await snapshotStorage()")

        # Intentos directos contra el mismo cliente de API que usan los controles.
        attempts = [
            ("/recipes", "POST", recipe), (recipe_url, "PUT", recipe), (recipe_url, "DELETE", None),
            ("/menu/generate", "POST", {"people": 6}), ("/menu/people", "POST", {"people": 5}),
            (f"/menu/{day}/comida", "POST", {"recipe_id": recipe_id, "people": 5}),
            ("/shopping-list/manual", "POST", {"name": "En cola"}),
            (product_url, "PATCH", {"checked": False}), (product_url, "DELETE", None)
        ]
        rejected = page.evaluate("""async attempts => {
            const rejections = [];
            for (const [path, method, data] of attempts) {
                try { await api(path, method, data); } catch (error) { rejections.push(error.message); }
            }
            return rejections;
        }""", attempts)
        assert rejected == ["Esta acción requiere conexión con Recetario."] * len(attempts)
        assert before == page.evaluate("async () => await snapshotStorage()")
        assert page.evaluate("async () => (await indexedDB.databases()).map(x => x.name)") == ["recetario-lectura"]
        assert page.evaluate("""async () => {
            const keys = await caches.keys();
            const requests = await (await caches.open(keys.find(key => key.startsWith("recetario-shell-")))).keys();
            return requests.every(request => request.method === "GET" &&
                !["/snapshot", "/recipes", "/menu", "/shopping-list"].includes(new URL(request.url).pathname));
        }""")
        assert not writes, writes

        # Una segunda instancia escribe en el servidor mientras esta pestaña está desconectada.
        assert admin.put(base + recipe_url, data={**recipe, "notes": "Actualizado desde casa"}).ok
        assert admin.put(base + product_url, data={"name": "Papel nuevo", "qty": 2, "unit": "paquetes"}).ok
        assert admin.patch(base + product_url, data={"checked": False}).ok

        # Cierra la página y arranca desde el icono (start_url) en el mismo perfil offline.
        page.close()
        page = context.new_page()
        observe_errors(page)
        banner = page.locator("#connectionStatus")
        page.goto(base + "/")
        expect(banner).to_have_text("Sin conexión · Modo de solo lectura")
        page.locator('nav a[href="lista_compra.html"]').click()
        expect(page.locator(".shopping-item").filter(has_text="Papel de cocina")).to_be_visible()

        unavailable_snapshot.set()
        context.set_offline(False)
        # Chromium no siempre emite online al restaurar la red después de reabrir.
        expect(banner).to_have_text("No se pudieron actualizar los datos · Modo de solo lectura", timeout=18000)
        expect(page.locator("#manualSubmit")).to_be_disabled()
        unavailable_snapshot.clear()

        with page.expect_response(lambda response: response.url.endswith("/snapshot") and response.ok):
            page.evaluate('window.dispatchEvent(new Event("online"))')
        expect(banner).to_have_text("Ya tienes conexión")
        updated = page.locator(".shopping-item").filter(has_text="Papel nuevo")
        expect(updated).to_contain_text("2 paquetes")
        expect(updated.locator("input")).not_to_be_checked()
        expect(page.locator("#manualSubmit")).to_be_enabled()
        expect(banner).to_be_hidden(timeout=4000)
        assert not writes, writes
        page.locator('nav a[href="recetas.html"]').click()
        card = page.locator(".recipe-card").filter(has_text="Desde casa")
        card.locator(".recipe-card-header").click()
        expect(card).to_contain_text("Actualizado desde casa")
        expect(card.locator(".editRecipe")).to_be_enabled()

        # Con Wi-Fi activo, la Pi puede no responder. El sondeo previo impide el POST.
        page.locator('nav a[href="lista_compra.html"]').click()
        page.route("**/connection", lambda route: route.abort())
        updated.locator("input").click()
        assert page.evaluate("navigator.onLine") is True
        expect(banner).to_have_text("Sin conexión · Modo de solo lectura")
        expect(updated.locator("input")).not_to_be_checked()
        assert not writes, writes
        actual = admin.get(base + "/shopping-list").json()
        assert [item for item in actual if item.get("manual_id") == product_id] == [{
            "manual_id": product_id, "name": "Papel nuevo", "qty": 2, "unit": "paquetes", "checked": False
        }]
        assert not errors, errors
    finally:
        unavailable_snapshot.clear()
        context.close()
        admin_context.close()
    print("OK: consulta y reapertura offline; bloqueo sin escrituras; recuperación y datos de SQLite actualizados")


def check_offline_without_data(browser, base, unavailable_snapshot):
    context = browser.new_context()
    page = context.new_page()
    unavailable_snapshot.set()
    try:
        page.goto(base + "/")
        page.wait_for_function("() => Boolean(navigator.serviceWorker.controller)")
        expect(page.locator("#connectionStatus")).to_contain_text("No se pudieron actualizar los datos")
        context.set_offline(True)
        page.locator('nav a[href="recetas.html"]').click()
        expect(page.locator("#connectionStatus")).to_contain_text("Sin conexión")
        expect(page.locator("#recipesContainer")).to_have_text("Estos datos aún no están disponibles sin conexión.")
    finally:
        unavailable_snapshot.clear()
        context.close()
    print("OK: interfaz disponible sin conexión incluso si aún no hay copia de recetas")


def run():
    results = Path(os.environ.get("TEST_RESULTS_DIR", Path(__file__).parent / "results"))
    results.mkdir(exist_ok=True)
    original_path = db.DB_PATH
    with tempfile.TemporaryDirectory() as directory:
        db.DB_PATH = str(Path(directory) / "browser.db")
        db._ready = False
        import set_up
        set_up.initialize()
        next_release = threading.Event()
        unavailable_snapshot = threading.Event()
        frontend = Path(__file__).resolve().parents[1] / "frontend"

        @app.before_request
        def serve_test_release():
            if unavailable_snapshot.is_set() and request.path == "/snapshot":
                return Response("Instantánea no disponible", status=503, mimetype="text/plain")
            if not next_release.is_set():
                return
            if request.path == "/sw.js":
                script = (frontend / "sw.js").read_text()
                return Response(re.sub(r"recetario-shell-v\d+", "recetario-shell-test-release", script),
                                mimetype="application/javascript", headers={"Cache-Control": "no-cache"})
            if request.path == "/style/menu.css":
                style = (frontend / "style/menu.css").read_text()
                return Response(style + "\n/* release de prueba */", mimetype="text/css")

        server = make_server("127.0.0.1", 0, app, threaded=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with sync_playwright() as pw:
                chromium = os.environ.get("CHROMIUM_PATH") or shutil.which("chromium") or shutil.which("chromium-browser")
                browser = pw.chromium.launch(executable_path=chromium, headless=True)
                page = browser.new_page(viewport={"width": 1280, "height": 900})
                page.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=base)
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)) if str(error) != "Transition was skipped" else None)
                network_errors = []
                console_errors = []
                page.on("response", lambda response: network_errors.append(f"{response.status} {response.url}")
                        if response.url.startswith(base) and response.status >= 400 and not response.url.endswith("favicon.ico") else None)
                page.on("requestfailed", lambda req: network_errors.append(req.url + " " + str(req.failure))
                        if req.url.startswith(base) and req.failure != "net::ERR_ABORTED" else None)
                page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" and "404" not in message.text else None)
                writes = []
                page.on("request", lambda req: writes.append(req.url) if req.method in ("POST", "PUT") and "/recipes" in req.url else None)

                page.goto(base + "/agregar_recetas.html")
                expect(page.locator("#recipeName")).to_be_enabled()
                page.locator("#recipeName").fill("Arroz simple")
                page.locator("#recipeName").press("Enter")
                expect(page.locator("#recipeServings")).to_be_focused()
                page.locator("#recipeServings").press("Enter")
                names = page.locator(".ingredient-name")
                expect(names.first).to_be_focused()
                names.first.fill("arroz")
                names.first.press("Enter")
                expect(page.locator(".ingredient-qty").first).to_be_focused()
                page.locator(".ingredient-qty").first.fill("200")
                page.locator(".ingredient-qty").first.press("Enter")
                units = page.locator(".ingredient-unit")
                expect(units.first).to_be_focused()
                units.first.select_option("g")
                units.first.press("Enter")
                expect(names.nth(1)).to_be_focused()
                assert not writes, writes
                page.locator(".submitButton").click()
                expect(page.locator("#toastMessage")).to_have_text("Receta añadida correctamente")
                plain = page.request.get(base + "/recipes").json()[0]
                assert plain["preparation"] == []
                print("OK: Enter recorre nombre/raciones/ingrediente/cantidad/unidad sin guardar; creación sin pasos")

                page.locator("#recipeName").fill("Arroz repetido")
                names.first.fill("Arroz")
                page.locator(".submitButton").click()
                expect(page.locator("#actionDialog")).to_be_visible()
                page.keyboard.press("Escape")
                expect(page.locator("#actionDialog")).to_be_hidden()
                assert len(page.request.get(base + "/recipes").json()) == 1
                page.reload()
                expect(page.locator("#recipeName")).to_be_enabled()
                print("OK: la detección de duplicados se puede cancelar con Escape sin guardar")

                page.locator("#recipeName").fill("Lentejas completas")
                names.first.fill("lentejas")
                page.locator(".ingredient-qty").first.fill("150")
                units.first.select_option("g")
                names.nth(1).press("Enter")
                expect(page.locator("#addStep")).to_be_focused()
                page.locator("#addStep").press("Enter")
                steps = page.locator(".preparation-step")
                expect(steps.first).to_be_focused()
                steps.first.fill("Lavar")
                steps.first.press("Shift+Enter")
                steps.first.press("End")
                steps.first.press("Enter")
                expect(steps.nth(1)).to_be_focused()
                steps.nth(1).fill("Cocer")
                page.locator(".move-up").nth(1).click()
                expect(steps.first).to_have_value("Cocer")
                page.locator(".preparation-row .deleteIngredient").nth(1).click()
                page.locator("#recipeNotes").fill("Tapar")
                page.locator("#recipeNotes").press("Enter")
                expect(page.locator("#recipeNotes")).to_have_value("Tapar\n")
                page.locator("#recipeNotes").press("Tab")
                expect(page.locator(".submitButton")).to_be_focused()
                page.locator(".submitButton").press("Enter")
                expect(page.locator("#toastMessage")).to_have_text("Receta añadida correctamente")
                rich = page.request.get(base + "/recipes").json()[1]
                assert rich["preparation"] == ["Cocer"] and rich["notes"] == "Tapar"
                print("OK: pasos opcionales, añadir/eliminar/reordenar, multilínea y guardar desde último control")

                page.goto(base + "/recetas.html")
                page.locator("#catalogSearch").fill("LÉNTEJAS")
                expect(page.locator(".recipe-card")).to_have_count(1)
                page.locator("#catalogSearch").fill("imposible sin coincidencias")
                expect(page.locator("#recipesContainer")).to_contain_text("No hay recetas que coincidan")
                page.locator("#catalogSearch").fill("arroz")
                expect(page.locator(".recipe-card")).to_have_count(1)
                page.locator("#catalogSearch").fill("")
                expect(page.locator(".recipe-card")).to_have_count(2)
                page.screenshot(path=str(results / "catalog-desktop.png"), full_page=True)
                print("OK: búsqueda inmediata, tildes, sin coincidencias y limpiar búsqueda")
                card = page.locator(f'.recipe-card[data-id="{rich["id"]}"]')
                card.locator(".recipe-card-header").click()
                expect(card.locator(".ingredients-panel")).to_be_visible()
                expect(card.locator("ol")).to_have_text("Cocer")
                assert "🍲" not in page.locator("body").inner_text()
                card.locator(".editRecipe").click()
                expect(page.locator("#recipeName")).to_have_value("Lentejas completas")
                expect(page.locator("#recipeNotes")).to_have_value("Tapar")
                expect(page.locator("#recipeServings")).to_have_value("2")
                expect(page.locator("#type-ambos")).to_be_checked()
                expect(page.locator(".ingredient-name").first).to_have_value("lentejas")
                expect(page.locator(".ingredient-qty").first).to_have_value("150")
                expect(page.locator(".ingredient-unit").first).to_have_value("g")
                expect(page.locator(".preparation-step")).to_have_value("Cocer")
                expect(page.locator(".submitButton")).to_contain_text("Guardar cambios")
                page.locator("#recipeName").fill("Cambio cancelado")
                page.locator(".ingredient-qty").first.fill("999")
                page.locator(".cancel-recipe").click()
                assert page.request.get(base + f'/recipes/{rich["id"]}').json() == rich
                print("OK: consulta numerada sin emoji y cancelar edición conserva datos")

                page.goto(base + f'/agregar_recetas.html?id={rich["id"]}')
                expect(page.locator("#recipeFields")).to_be_enabled()
                # Un error de validación mantiene lo escrito.
                page.locator("#recipeServings").fill("0")
                page.locator(".submitButton").click()
                expect(page.locator("#recipeNotes")).to_have_value("Tapar")
                assert page.url.endswith(f"id={rich['id']}")
                page.locator("#recipeServings").fill("4")
                page.locator(".ingredient-qty").first.fill("300")
                names.nth(1).fill("sal")
                page.locator("#recipeNotes").fill("Nueva nota")
                page.locator(".submitButton").click()
                page.wait_for_url("**/recetas.html")
                expect(page.locator("#toastMessage")).to_have_text("Cambios de la receta guardados")
                page.reload()
                expect(page.locator("#toast")).to_be_hidden()
                recipes = page.request.get(base + "/recipes").json()
                assert len(recipes) == 2
                edited = next(r for r in recipes if r["id"] == rich["id"])
                assert edited["servings"] == 4 and edited["notes"] == "Nueva nota"
                assert len(edited["ingredients"]) == 2 and edited["ingredients"][0]["qty"] == 300
                print("OK: editar guarda el mismo ID y persiste tras recargar")

                page.request.post(base + "/menu/lunes/comida", data={"recipe_id": rich["id"], "people": None})
                page.goto(base + "/menu.html")
                slot = page.locator('.meal-slot[data-day="lunes"][data-meal="comida"]')
                expect(slot.locator("input")).to_have_value("4")
                slot.locator("input").fill("8")
                slot.locator("input").press("Enter")
                expect(slot.locator("input")).to_be_enabled()
                expect(slot.locator("input")).to_have_value("8")
                page.goto(base + "/lista_compra.html")
                expect(page.locator("#shoppingList")).to_contain_text("600 g")
                page.goto(base + "/menu.html")
                slot.locator(".reset-people").click()
                expect(slot.locator("input")).to_have_value("4")
                slot.locator(".food").click()
                expect(page.locator(f'.choose-recipe-item[data-id="{rich["id"]}"]')).to_be_visible()
                page.locator("#slotPeople").fill("2")
                page.locator(f'.choose-recipe-item[data-id="{rich["id"]}"]').click()
                expect(slot.locator("input")).to_have_value("2")
                page.goto(base + "/lista_compra.html")
                expect(page.locator("#shoppingList")).to_contain_text("150 g")
                page.reload()
                expect(page.locator("#shoppingList")).to_contain_text("150 g")
                print("OK: cambiar/restablecer comensales y elegir receta actualiza compra y persiste")

                # Completa el catálogo de prueba para generar una semana sin repetición.
                for index in range(len(db.DAYS) * 2 - 2):
                    db.save_recipe(f"Plato de prueba {index}", [
                        {"name": "tomate" if index % 2 else "tomates", "qty": 500 if index % 2 else .5,
                         "unit": "g" if index % 2 else "kg"}], servings=2)
                page.goto(base + "/menu.html")
                page.locator("#generateButton").click()
                expect(page.locator("#actionNumber")).to_have_value("2")
                page.locator("#actionNumber").fill("3")
                page.locator("#actionDialog [data-dialog-close]").click()
                assert page.request.get(base + "/menu/people").json()["people"] == 2
                page.locator("#generateButton").click()
                expect(page.locator("#actionNumber")).to_have_value("2")
                page.locator("#actionNumber").fill("3")
                page.locator("#actionConfirm").click()
                expect(page.locator("#actionDialog")).to_be_hidden()
                expect(page.locator(".slot-people input")).to_have_count(len(db.DAYS) * 2)
                expect(page.locator("#weekPeople")).to_have_value("3")
                assert all(v == "3" for v in page.locator(".slot-people input").evaluate_all("els => els.map(e => e.value)"))
                before = page.request.get(base + "/menu").json()
                page.locator("#weekPeople").fill("4")
                page.locator("#weekPeopleForm button").click()
                expect(page.locator("#toastMessage")).to_have_text("Comensales actualizados")
                expect(page.locator(".slot-people input").first).to_have_value("4")
                after = page.request.get(base + "/menu").json()
                assert all(before[d][m]["id"] == after[d][m]["id"] for d in before for m in db.MEALS)
                assert all(r["people"] == 4 for meals in after.values() for r in meals.values())
                page.locator(".slot-people input").first.fill("7")
                with page.expect_response(lambda response: response.request.method == "POST"
                                          and response.url.endswith(f"/menu/{db.DAYS[0]}/comida")) as updated_slot:
                    page.locator(".slot-people input").first.press("Enter")
                assert updated_slot.value.ok
                expect(page.locator(".slot-people input").first).to_be_enabled()
                page.reload()
                expect(page.locator("#weekPeople")).to_have_value("4")
                expect(page.locator(".slot-people input").first).to_have_value("7")
                page.locator("#generateButton").click()
                expect(page.locator("#actionNumber")).to_have_value("4")
                page.locator("#actionDialog [data-dialog-close]").click()
                page.screenshot(path=str(results / "menu-desktop.png"), full_page=True)
                print("OK: regeneración con confirmación/cancelación, comensales semanales, cambio masivo sin cambiar recetas e individual persistente")

                monday = page.locator(f'.day-card[data-day="{db.DAYS[0]}"]')
                monday.evaluate('card => card.scrollIntoView({block: "center", behavior: "instant"})')
                slots = monday.locator(".meal-slot")
                first, second = [slots.nth(index).locator(".food").inner_text() for index in range(2)]
                source, target = [slots.nth(index).locator(".meal-label").bounding_box() for index in range(2)]
                with page.expect_response(lambda response: response.url.endswith("/menu/swap")) as swap:
                    page.mouse.move(source["x"] + 10, source["y"] + source["height"] / 2)
                    page.mouse.down()
                    page.mouse.move(target["x"] + 10, target["y"] + target["height"] / 2, steps=12)
                    page.mouse.up()
                assert swap.value.ok
                assert swap.value.request.post_data_json == {
                    "day1": db.DAYS[0], "meal1": "comida", "day2": db.DAYS[0], "meal2": "cena",
                }, swap.value.request.post_data
                expect(slots.nth(0).locator(".food")).to_have_text(second)
                expect(slots.nth(1).locator(".food")).to_have_text(first)
                expect(slots.nth(1).locator("input")).to_have_value("7")

                page.locator("#shareMenuButton").click()
                page.locator('[data-share="copy"]').click()
                expect(page.locator("#toastMessage")).to_have_text("Texto copiado al portapapeles")
                assert page.evaluate('async () => (await navigator.clipboard.readText()).includes("MENÚ SEMANAL")')
                page.locator('nav a[href="lista_compra.html"]').click()
                tomato = page.locator(".shopping-item").filter(has=page.locator("strong", has_text="Tomate"))
                expect(tomato).to_have_count(1)
                # La suma y el escalado coinciden con el cálculo independiente del menú.
                expected = sum((750 if r["people"] == 3 else 500 * r["people"] / 2)
                               for meals in page.request.get(base + "/menu").json().values()
                               for r in meals.values() if r["name"].startswith("Plato de prueba"))
                expect(tomato).to_contain_text(f"{int(expected)} g")
                tomato.locator("input").click()
                expect(page.locator(".purchased-divider")).to_be_visible()
                expect(page.locator(".shopping-item").last.locator("strong")).to_have_text("Tomate")
                page.reload()
                expect(tomato.locator("input")).to_be_checked()
                tomato.locator("input").click()
                expect(page.locator(".purchased-divider")).to_have_count(0)
                expect(tomato.locator("input")).not_to_be_checked()
                page.reload()
                expect(tomato.locator("input")).not_to_be_checked()
                tomato.locator("input").click()
                expect(page.locator(".purchased-divider")).to_be_visible()
                page.screenshot(path=str(results / "shopping-desktop.png"), full_page=True)
                page.locator("#shareMenuButton").click()
                page.locator('[data-share="copy"]').click()
                expect(page.locator("#toastMessage")).to_have_text("Texto copiado al portapapeles")
                assert page.evaluate('async () => (await navigator.clipboard.readText()).includes("✅ Tomate")')
                # Todos comprados y vuelta a pendientes.
                pending = page.locator('.shopping-item:not(.checked) input')
                for remaining in reversed(range(pending.count())):
                    pending.first.click()
                    expect(pending).to_have_count(remaining)
                expect(page.locator('.shopping-item:not(.checked)')).to_have_count(0)
                expect(page.locator('.purchased-divider')).to_have_count(1)
                page.locator('.shopping-item input').first.click()
                expect(page.locator('.shopping-item:not(.checked)')).to_have_count(1)
                print("OK: suma de tomates con escalado, comprados al final, separador, desmarcado y persistencia")
                print("OK: intercambio al arrastrar, navegación y copia al portapapeles de menú y compra")

                page.set_viewport_size({"width": 375, "height": 812})
                page.goto(base + f'/agregar_recetas.html?id={rich["id"]}')
                expect(page.locator("#recipeFields")).to_be_enabled()
                page.screenshot(path=str(results / "form-mobile.png"), full_page=True)
                overflow = page.evaluate("""Array.from(document.querySelectorAll('body *')).filter(el => {
                    const rect = el.getBoundingClientRect(); return rect.width && rect.right > innerWidth;
                }).map(el => ({tag: el.tagName, class: el.className, width: el.getBoundingClientRect().width}))""")
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), overflow
                assert not errors, errors
                for filename in ["recetas.html", "lista_compra.html", "menu.html"]:
                    page.goto(base + "/" + filename)
                    expect(page.locator("main")).to_be_visible()
                    if filename == "menu.html":
                        page.locator("#generateButton").click()
                        expect(page.locator("#actionNumber")).to_be_visible()
                        bounds = page.locator("#actionDialog .modal-content").bounding_box()
                        assert bounds["x"] >= 0 and bounds["y"] >= 0 and bounds["y"] + bounds["height"] <= 812
                        page.screenshot(path=str(results / "generate-mobile.png"))
                        page.locator("#actionDialog [data-dialog-close]").click()
                        page.locator(".meal-slot .food").first.click()
                        expect(page.locator("#chooseRecipeModal")).to_be_visible()
                        page.screenshot(path=str(results / "choose-mobile.png"))
                        page.locator("#closeChooseModal").click()
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), filename
                    page.screenshot(path=str(results / (filename.replace('.html', '') + '-mobile.png')), full_page=True)

                page.goto(base + "/lista_compra.html")
                form = page.locator("#manualForm")
                form.locator('[name="name"]').fill("Detergente")
                form.locator('[name="qty"]').fill("2")
                form.locator("#manualUnit").select_option("__custom__")
                expect(form.locator(".custom-unit")).to_be_focused()
                form.locator(".custom-unit").fill("botellas")
                form.get_by_role("button", name="Añadir producto").click()
                product = page.locator(".shopping-item").filter(has_text="Detergente")
                expect(product).to_contain_text("2 botellas")
                product.get_by_role("button", name="Editar Detergente").click()
                expect(form.locator(".custom-unit")).to_have_value("botellas")
                form.locator('[name="qty"]').fill("3")
                form.get_by_role("button", name="Guardar producto").click()
                expect(product).to_contain_text("3 botellas")
                product.get_by_role("checkbox").click()
                expect(product).to_have_class("shopping-item checked")
                page.reload()
                expect(product.get_by_role("checkbox")).to_be_checked()
                page.locator("#shareMenuButton").click()
                page.locator('[data-share="copy"]').click()
                expect(page.locator("#toastMessage")).to_have_text("Texto copiado al portapapeles")
                assert page.evaluate('async () => (await navigator.clipboard.readText()).includes("✅ Detergente (3 botellas)")')
                product.get_by_role("checkbox").click()
                expect(product).to_have_class("shopping-item")
                page.evaluate("window.scrollTo(0, 0)")
                capture(page, results / "manual-shopping-mobile.png")
                product.get_by_role("button", name="Eliminar Detergente").click()
                expect(page.locator("#actionDialog")).to_contain_text("«Detergente»")
                page.keyboard.press("Escape")
                expect(product).to_have_count(1)
                product.get_by_role("button", name="Eliminar Detergente").click()
                page.get_by_role("button", name="Eliminar producto").click()
                expect(product).to_have_count(0)
                print("OK: productos manuales en móvil, edición, marcas, recarga, compartir y borrado")
                assert not errors, errors
                assert not network_errors, network_errors
                assert not console_errors, console_errors
                check_pwa(browser, base, results, next_release)
                check_offline(browser, base, results, unavailable_snapshot)
                check_offline_without_data(browser, base, unavailable_snapshot)
                browser.close()
                print("OK: formulario móvil sin desbordamiento; sin errores JavaScript")
        finally:
            server.shutdown()
            thread.join()
            db.DB_PATH = original_path
            db._ready = False


if __name__ == "__main__":
    run()
