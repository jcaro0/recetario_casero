"""Prueba integral con Chromium y una BD temporal (requiere Playwright solo para pruebas).

    PYTHONPATH=backend python3 tests/browser_recipes.py
    CHROMIUM_PATH=/usr/bin/chromium PYTHONPATH=backend python3 tests/browser_recipes.py
"""
import os
import tempfile
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server
import database as db
from main import app


def run():
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
                browser = pw.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH", "/usr/bin/chromium"), headless=True)
                page = browser.new_page(viewport={"width": 1280, "height": 900})
                # Los recursos externos no son necesarios para comprobar la aplicación.
                page.route("https://fonts.googleapis.com/**", lambda route: route.abort())
                errors = []
                # Chromium puede cancelar una transición CSS al navegar rápidamente.
                page.on("pageerror", lambda error: errors.append(str(error))
                        if str(error) != "Transition was skipped" else None)
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
                card = page.locator(f'.recipe-card[data-id="{rich["id"]}"]')
                card.locator(".recipe-card-header").click()
                expect(card.locator(".ingredients-panel")).to_be_visible()
                expect(card.locator("ol")).to_have_text("Cocer")
                assert "🍲" not in page.locator("body").inner_text()
                card.locator(".editRecipe").click()
                expect(page.locator("#recipeName")).to_have_value("Lentejas completas")
                expect(page.locator("#recipeNotes")).to_have_value("Tapar")
                page.locator("#recipeName").fill("Cambio cancelado")
                page.locator(".ingredient-qty").first.fill("999")
                page.locator(".cancel-recipe").click()
                assert page.request.get(base + f'/recipes/{rich["id"]}').json() == rich
                print("OK: consulta numerada sin emoji y cancelar edición conserva datos")

                page.goto(base + f'/agregar_recetas.html?id={rich["id"]}')
                expect(page.locator("#recipeFields")).to_be_enabled()
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

                page.set_viewport_size({"width": 375, "height": 812})
                page.goto(base + f'/agregar_recetas.html?id={rich["id"]}')
                expect(page.locator("#recipeFields")).to_be_enabled()
                page.screenshot(path="/tmp/recetario-form-mobile.png", full_page=True)
                overflow = page.evaluate("""Array.from(document.querySelectorAll('body *')).filter(el => {
                    const rect = el.getBoundingClientRect(); return rect.width && rect.right > innerWidth;
                }).map(el => ({tag: el.tagName, class: el.className, width: el.getBoundingClientRect().width}))""")
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), overflow
                assert not errors, errors
                assert not errors, errors
                browser.close()
                print("OK: formulario móvil sin desbordamiento; sin errores JavaScript")
        finally:
            server.shutdown()
            thread.join()
            db.DB_PATH = original_path
            db._ready = False


if __name__ == "__main__":
    run()
