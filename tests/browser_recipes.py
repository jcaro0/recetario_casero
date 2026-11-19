"""Prueba integral con Chromium y una BD temporal (requiere Playwright solo para pruebas).

    PYTHONPATH=backend python3 tests/browser_recipes.py
    CHROMIUM_PATH=/usr/bin/chromium PYTHONPATH=backend python3 tests/browser_recipes.py
"""
import os
import shutil
import tempfile
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server
import database as db
from main import app


def run():
    results = Path(os.environ.get("TEST_RESULTS_DIR", Path(__file__).parent / "results"))
    results.mkdir(exist_ok=True)
    original_path = db.DB_PATH
    with tempfile.TemporaryDirectory() as directory:
        db.DB_PATH = str(Path(directory) / "browser.db")
        db._ready = False
        import set_up
        set_up.initialize()
        server = make_server("127.0.0.1", 0, app, threaded=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with sync_playwright() as pw:
                chromium = os.environ.get("CHROMIUM_PATH") or shutil.which("chromium") or shutil.which("chromium-browser")
                browser = pw.chromium.launch(executable_path=chromium, headless=True)
                page = browser.new_page(viewport={"width": 1280, "height": 900})
                # Los recursos externos no son necesarios para comprobar la aplicación.
                page.route("https://fonts.googleapis.com/**", lambda route: route.fulfill(status=200, body="", content_type="text/css"))
                errors = []
                # Chromium puede cancelar una transición CSS al navegar rápidamente.
                page.on("pageerror", lambda error: errors.append(str(error))
                        if str(error) != "Transition was skipped" else None)
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
                expect(page.locator("#formStatus")).to_have_text("Receta guardada.")
                plain = page.request.get(base + "/recipes").json()[0]
                assert plain["preparation"] == []
                print("OK: Enter recorre nombre/raciones/ingrediente/cantidad/unidad sin guardar; creación sin pasos")

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
                expect(page.locator("#formStatus")).to_have_text("Receta guardada.")
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
                page.reload()
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
                expect(page.locator("#generatePeople")).to_have_value("2")
                page.locator("#generatePeople").fill("3")
                page.locator("#cancelModal").click()
                assert page.request.get(base + "/menu/people").json()["people"] == 2
                page.locator("#generateButton").click()
                expect(page.locator("#generatePeople")).to_have_value("2")
                page.locator("#generatePeople").fill("3")
                page.locator("#confirmModal").click()
                expect(page.locator("#modal")).to_be_hidden()
                expect(page.locator(".slot-people input")).to_have_count(len(db.DAYS) * 2)
                expect(page.locator("#weekPeople")).to_have_value("3")
                assert all(v == "3" for v in page.locator(".slot-people input").evaluate_all("els => els.map(e => e.value)"))
                before = page.request.get(base + "/menu").json()
                page.locator("#weekPeople").fill("4")
                page.locator("#weekPeopleForm button").click()
                expect(page.locator("#weekPeopleStatus")).to_have_text("Comensales actualizados")
                expect(page.locator(".slot-people input").first).to_have_value("4")
                after = page.request.get(base + "/menu").json()
                assert all(before[d][m]["id"] == after[d][m]["id"] for d in before for m in db.MEALS)
                assert all(r["people"] == 4 for meals in after.values() for r in meals.values())
                page.locator(".slot-people input").first.fill("7")
                page.locator(".slot-people input").first.press("Enter")
                expect(page.locator(".slot-people input").first).to_have_value("7")
                page.reload()
                expect(page.locator("#weekPeople")).to_have_value("4")
                expect(page.locator(".slot-people input").first).to_have_value("7")
                page.locator("#generateButton").click()
                expect(page.locator("#generatePeople")).to_have_value("4")
                page.locator("#cancelModal").click()
                page.screenshot(path=str(results / "menu-desktop.png"), full_page=True)
                print("OK: regeneración con confirmación/cancelación, comensales semanales, cambio masivo sin cambiar recetas e individual persistente")

                page.goto(base + "/lista_compra.html")
                tomato = page.locator(".shopping-item").filter(has=page.locator("strong", has_text="Tomate"))
                expect(tomato).to_have_count(1)
                # La suma y el escalado coinciden con el cálculo independiente del menú.
                expected = sum((750 if r["people"] == 3 else 500 * r["people"] / 2)
                               for meals in page.request.get(base + "/menu").json().values()
                               for r in meals.values() if r["name"].startswith("Plato de prueba"))
                expect(tomato).to_contain_text(f"{int(expected)} g")
                tomato.locator("input").check()
                expect(page.locator(".purchased-divider")).to_be_visible()
                expect(page.locator(".shopping-item").last.locator("strong")).to_have_text("Tomate")
                page.reload()
                expect(tomato.locator("input")).to_be_checked()
                tomato.locator("input").uncheck()
                expect(page.locator(".purchased-divider")).to_have_count(0)
                expect(tomato.locator("input")).not_to_be_checked()
                page.reload()
                expect(tomato.locator("input")).not_to_be_checked()
                tomato.locator("input").check()
                expect(page.locator(".purchased-divider")).to_be_visible()
                page.screenshot(path=str(results / "shopping-desktop.png"), full_page=True)
                # Todos comprados y vuelta a pendientes.
                while page.locator('.shopping-item:not(.checked) input').count():
                    page.locator('.shopping-item:not(.checked) input').first.check()
                    page.wait_for_timeout(100)
                expect(page.locator('.shopping-item:not(.checked)')).to_have_count(0)
                expect(page.locator('.purchased-divider')).to_have_count(1)
                page.locator('.shopping-item input').first.uncheck()
                expect(page.locator('.shopping-item:not(.checked)')).to_have_count(1)
                print("OK: suma de tomates con escalado, comprados al final, separador, desmarcado y persistencia")

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
                        expect(page.locator("#generatePeople")).to_be_visible()
                        bounds = page.locator("#modal .modal-content").bounding_box()
                        assert bounds["x"] >= 0 and bounds["y"] >= 0 and bounds["y"] + bounds["height"] <= 812
                        page.screenshot(path=str(results / "generate-mobile.png"), full_page=True)
                        page.locator("#cancelModal").click()
                        page.locator(".meal-slot .food").first.click()
                        expect(page.locator("#chooseRecipeModal")).to_be_visible()
                        page.screenshot(path=str(results / "choose-mobile.png"), full_page=True)
                        page.locator("#closeChooseModal").click()
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), filename
                    page.screenshot(path=str(results / (filename.replace('.html', '') + '-mobile.png')), full_page=True)
                assert not errors, errors
                assert not network_errors, network_errors
                assert not console_errors, console_errors
                browser.close()
                print("OK: formulario móvil sin desbordamiento; sin errores JavaScript")
        finally:
            server.shutdown()
            thread.join()
            db.DB_PATH = original_path
            db._ready = False


if __name__ == "__main__":
    run()
