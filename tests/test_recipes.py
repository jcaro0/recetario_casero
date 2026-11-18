"""Regresiones de API, migraciones y compra; usa exclusivamente bases temporales.

    PYTHONPATH=backend python3 -m unittest discover -s tests -v
"""
import os
from contextlib import closing
import sqlite3
import tempfile
import unittest

import database as db
from main import app


class RecipeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp.name, "recipes.db")
        db._ready = False
        self.old_backup = os.environ.get('BACKUP_DIR')
        os.environ['BACKUP_DIR'] = os.path.join(self.temp.name, 'backups')
        import set_up
        set_up.initialize()
        self.client = app.test_client()

    def tearDown(self):
        db.DB_PATH = self.old_path
        db._ready = False
        if self.old_backup is None:
            os.environ.pop('BACKUP_DIR', None)
        else:
            os.environ['BACKUP_DIR'] = self.old_backup
        self.temp.cleanup()

    def create(self, **changes):
        data = {"name": "Arroz con pollo", "ingredients": [
            {"name": "arroz", "qty": 200, "unit": "g"},
            {"name": "pollo", "qty": 400, "unit": "g"},
            {"name": "cebolla", "qty": 1, "unit": None},
        ]}
        data.update(changes)
        response = self.client.post("/recipes", json=data)
        self.assertEqual(response.status_code, 201, response.json)
        return response.json

    def plan(self, recipe, day="lunes", meal="comida", people=None):
        response = self.client.post(f"/menu/{day}/{meal}", json={"recipe_id": recipe["id"], "people": people})
        self.assertEqual(response.status_code, 200, response.json)

    def quantities(self):
        return {(i["name"], i["unit"]): i["qty"] for i in self.client.get("/shopping-list").json}

    def test_optional_fields_and_persistence(self):
        plain = self.create()
        self.assertEqual((plain["servings"], plain["preparation"], plain["notes"]), (2, [], ""))
        rich = self.create(preparation=["Cortar\nla cebolla", "Cocinar", "  "], notes="Variar las verduras", servings=3)
        db._ready = False  # reabre conexiones e inicialización como tras un reinicio
        self.assertEqual(self.client.get(f'/recipes/{rich["id"]}').json, rich)
        self.assertEqual(rich["preparation"], ["Cortar\nla cebolla", "Cocinar"])

    def test_edit_same_id_and_recompute(self):
        recipe = self.create()
        self.plan(recipe, people=4)
        recipe.update(name="Arroz editado", ingredients=[{"name": "arroz", "qty": 300, "unit": "g"}],
                      preparation=["Hervir"], notes="Tapar")
        edited = self.client.put(f'/recipes/{recipe["id"]}', json=recipe)
        self.assertEqual(edited.status_code, 200)
        self.assertEqual(edited.json["id"], recipe["id"])
        self.assertEqual(len(self.client.get("/recipes").json), 1)
        self.assertEqual(self.quantities(), {("Arroz", "g"): 600})
        self.assertEqual(self.client.get("/menu").json["lunes"]["comida"]["name"], "Arroz editado")

    def test_scaling_defaults_and_original_quantities(self):
        recipe = self.create()
        self.plan(recipe, people=4)
        self.assertEqual(self.quantities(), {("Arroz", "g"): 400, ("Pollo", "g"): 800, ("Cebolla", "uds"): 2})
        self.assertEqual(self.client.get(f'/recipes/{recipe["id"]}').json, recipe)
        self.plan(recipe)
        self.assertEqual(self.quantities()[("Arroz", "g")], 200)
        recipe["servings"] = 4
        self.client.put(f'/recipes/{recipe["id"]}', json=recipe)
        self.assertEqual(self.quantities()[("Arroz", "g")], 200)
        self.plan(recipe, people=2)
        self.assertEqual(self.quantities()[("Arroz", "g")], 100)

    def test_combine_convert_separate_and_free_text(self):
        a = self.create(ingredients=[{"name": "arroz", "qty": .1, "unit": "kg"},
                                    {"name": "arroz", "qty": "al gusto", "unit": None}])
        b = self.create(ingredients=[{"name": "ARROZ", "qty": 200, "unit": "g"},
                                    {"name": "arroz", "qty": 1, "unit": "taza"}])
        self.plan(a, people=4)
        self.plan(b, day="martes", people=3)
        self.assertEqual(self.quantities(), {("Arroz", "g"): 500, ("Arroz", "taza"): 1.5,
                                             ("Arroz", None): "al gusto"})

    def test_fractional_rounding_and_repeated_recipes(self):
        recipe = self.create(servings=3, ingredients=[{"name": "huevo", "qty": 1}])
        self.plan(recipe, people=2)
        self.plan(recipe, day="martes", people=4)
        self.assertEqual(self.quantities(), {("Huevo", "uds"): 2})

    def test_validation_does_not_modify_saved_recipe(self):
        recipe = self.create()
        for value in [0, -1, 1.5, "2", True, None]:
            with self.subTest(value=value):
                response = self.client.put(f'/recipes/{recipe["id"]}', json=dict(recipe, servings=value))
                self.assertEqual(response.status_code, 400)
                response = self.client.post("/menu/lunes/comida", json={"recipe_id": recipe["id"], "people": value})
                self.assertEqual(response.status_code, 200 if value is None else 400)
        for changes in [{"name": " "}, {"ingredients": []}, {"preparation": "texto"}, {"notes": []}]:
            self.assertEqual(self.client.put(f'/recipes/{recipe["id"]}', json=dict(recipe, **changes)).status_code, 400)
        self.assertEqual(self.client.get(f'/recipes/{recipe["id"]}').json, recipe)
        self.assertEqual(self.client.put('/recipes/999', json=recipe).status_code, 404)

    def test_menu_swap_delete_and_checked(self):
        a = self.create()
        b = self.create(name="Otro arroz")
        self.plan(a, people=4)
        self.plan(b, meal="cena", people=1)
        self.assertEqual(self.client.post("/menu/swap", json={"day1": "lunes", "meal1": "comida", "day2": "lunes", "meal2": "cena"}).status_code, 200)
        menu = self.client.get("/menu").json["lunes"]
        self.assertEqual((menu["cena"]["id"], menu["cena"]["people"]), (a["id"], 4))
        self.client.post("/shopping-list/check", json={"name": "arroz", "unit": "g", "checked": True})
        self.assertTrue(next(i for i in self.client.get("/shopping-list").json if i["name"] == "Arroz")["checked"])
        self.client.delete(f'/recipes/{a["id"]}')
        self.assertIsNone(self.client.get("/menu").json["lunes"]["cena"]["name"])
        self.assertEqual(self.quantities()[("Arroz", "g")], 100)
        db.replace_menu({("lunes", "comida"): b["id"]})
        self.assertIsNone(self.client.get("/menu").json["lunes"]["comida"]["people"])

    def test_random_menu_and_edit_type(self):
        for index in range(len(db.DAYS) * 2):
            self.create(name=f"Receta {index}")
        self.assertEqual(self.client.post("/menu/generate").status_code, 200)
        menu = self.client.get("/menu").json
        slots = [recipe for meals in menu.values() for recipe in meals.values()]
        self.assertEqual(len({recipe["id"] for recipe in slots}), len(db.DAYS) * 2)
        self.assertTrue(all(recipe["people"] == 2 for recipe in slots))
        recipe = menu["lunes"]["cena"]
        recipe["type"] = "comida"
        self.assertEqual(self.client.put(f'/recipes/{recipe["id"]}', json=recipe).status_code, 200)
        self.assertIsNone(self.client.get("/menu").json["lunes"]["cena"]["name"])
        self.assertIsNotNone(self.client.get("/menu").json["lunes"]["comida"]["name"])

    def test_week_people_generate_bulk_persist_and_empty_slots(self):
        self.assertEqual(self.client.get('/menu/people').json, {'people': 2})
        for index in range(len(db.DAYS) * 2):
            self.create(name=f'Plato {index}')
        for value in [0, -1, 1.5, True, "3", None]:
            self.assertEqual(self.client.post('/menu/people', json={'people': value}).status_code, 400)
            self.assertEqual(self.client.post('/menu/generate', json={'people': value}).status_code, 400)
        self.assertEqual(self.client.post('/menu/generate', json={'people': 3}).status_code, 200)
        before = self.client.get('/menu').json
        self.assertTrue(all(r['people'] == 3 for meals in before.values() for r in meals.values()))
        self.assertEqual(self.client.post('/menu/people', json={'people': 5}).status_code, 200)
        after = self.client.get('/menu').json
        for day in before:
            for meal in db.MEALS:
                self.assertEqual(before[day][meal]['id'], after[day][meal]['id'])
                self.assertEqual(after[day][meal]['people'], 5)
        db._ready = False
        self.assertEqual(self.client.get('/menu/people').json['people'], 5)
        recipe = after['lunes']['comida']
        self.plan(recipe, people=1)
        self.assertEqual(self.client.get('/menu/people').json['people'], 5)
        # Sin people, una nueva asignación hereda la preferencia semanal.
        self.client.post('/menu/lunes/cena', json={'recipe_id': recipe['id']})
        self.assertEqual(self.client.get('/menu').json['lunes']['cena']['people'], 5)
        self.client.post('/menu/generate')
        self.assertTrue(all(r['people'] == 5 for meals in self.client.get('/menu').json.values() for r in meals.values()))

    def test_empty_slots_inactive_days_and_unit_boundaries(self):
        recipe = self.create(ingredients=[{'name':'Leche','qty':'1,5','unit':'l'},
                                          {'name':'leche','qty':500,'unit':'ml'},
                                          {'name':'leche','qty':1,'unit':'cucharada'},
                                          {'name':'leche','qty':1,'unit':'cucharadita'}])
        db.set_menu_slot('sábado', 'comida', recipe['id'], 100)
        self.assertEqual(db.get_shopping_list(), [])
        self.client.post('/menu/people', json={'people': 6})
        self.assertFalse(any(row['recipe_id'] for row in db.read_menu() if row['day'] != 'sábado'))
        self.client.post('/menu/lunes/comida', json={'recipe_id':recipe['id']})
        self.assertEqual(self.quantities(), {('Leche','ml'):6000, ('Leche','cda'):3, ('Leche','cdta'):3})
        self.assertEqual(db.get_recipe(recipe['id']), recipe)

    def test_week_bulk_rolls_back_on_sql_failure(self):
        import sqlite3
        with db.connection() as conn:
            conn.execute("CREATE TRIGGER fail_people BEFORE UPDATE OF people ON menu "
                         "WHEN NEW.day='martes' BEGIN SELECT RAISE(ABORT, 'test failure'); END")
        before = db.read_menu()
        with self.assertRaises(sqlite3.IntegrityError):
            db.set_week_people(7)
        self.assertEqual(db.read_menu(), before)
        self.assertEqual(db.get_week_people(), 2)

    def test_aliases_fraction_units_and_original_names(self):
        a = self.create(ingredients=[{'name': 'Tomate', 'qty': '500', 'unit': 'g'},
                                    {'name': 'Huévos', 'qty': '1 1/2', 'unit': 'unidades'},
                                    {'name': 'Aceite de oliva', 'qty': '¼', 'unit': 'cucharadas'}])
        b = self.create(ingredients=[{'name': 'tomates', 'qty': '0,5', 'unit': 'kg'},
                                    {'name': 'huevo', 'qty': '½', 'unit': 'ud'},
                                    {'name': ' ACEITE  DE OLIVA ', 'qty': '3/4', 'unit': 'cda'},
                                    {'name': 'tomate triturado', 'qty': 1, 'unit': 'l'},
                                    {'name': 'tomate frito', 'qty': 1, 'unit': 'cdta'}])
        self.plan(a)
        self.plan(b, meal='cena')
        quantities = self.quantities()
        self.assertEqual(quantities[('Tomate', 'g')], 1000)
        self.assertEqual(quantities[('Huevo', 'uds')], 2)
        self.assertEqual(quantities[('Aceite de oliva', 'cda')], 1)
        self.assertEqual(quantities[('Tomate triturado', 'ml')], 1000)
        self.assertIn(('Tomate frito', 'cdta'), quantities)
        self.assertEqual(self.client.get(f"/recipes/{a['id']}").json['ingredients'][1]['name'], 'Huévos')

    def test_parse_conservative_unknown_and_marks_compatibility(self):
        from normalize import parse_quantity, ingredient_key
        from decimal import Decimal
        for value, expected in [('1', '1'), ('1,5', '1.5'), ('1.5', '1.5'), ('1/2', '.5'),
                                ('1 1/2', '1.5'), ('½', '.5'), ('¼', '.25'), ('¾', '.75')]:
            self.assertEqual(parse_quantity(value), Decimal(expected))
        for value in ['al gusto', 'una pizca', 'cantidad necesaria', '1/0']:
            self.assertIsNone(parse_quantity(value))
        for a, b in [('tomates', 'tomate'), ('dientes de ajo', 'diente de ajo'), ('cebollas', 'cebolla'),
                     ('patatas', 'patata'), ('pimientos', 'pimiento')]:
            self.assertEqual(ingredient_key(a), ingredient_key(b))
        for a, b in [('tomate', 'tomate frito'), ('sal', 'salsa'), ('pimiento', 'pimienta'), ('anis', 'ani')]:
            self.assertNotEqual(ingredient_key(a), ingredient_key(b))
        recipe = self.create(ingredients=[{'name': 'Tomates', 'qty': 1, 'unit': 'kg'},
                                          {'name': 'Tomate', 'qty': None},
                                          {'name': 'Tomate', 'qty': 'al gusto'},
                                          {'name': 'Tomate', 'qty': 'una pizca'}])
        self.plan(recipe)
        with db.connection() as conn:
            conn.execute("INSERT INTO shopping_checked VALUES ('Tomates','kg')")
        items = self.client.get('/shopping-list').json
        self.assertTrue(next(i for i in items if i['unit'] == 'g')['checked'])
        self.assertEqual({i['qty'] for i in items}, {1000, None, 'al gusto', 'una pizca'})
        self.client.post('/shopping-list/check', json={'name':'Tomate', 'unit':'g', 'checked':False})
        self.assertFalse(next(i for i in self.client.get('/shopping-list').json if i['unit']=='g')['checked'])
        self.client.post('/shopping-list/check', json={'name':'Tomate', 'unit':'cdta', 'checked':True})
        self.assertFalse(next(i for i in self.client.get('/shopping-list').json if i['unit']=='g')['checked'])

    def test_migrate_v4_with_verified_backup(self):
        recipe = self.create()
        self.plan(recipe, people=4)
        self.client.post('/shopping-list/check', json={'name':'arroz','unit':'g','checked':True})
        with db.connection() as conn:
            conn.execute('DROP TABLE settings')
            conn.execute('PRAGMA user_version=4')
        db._ready = False
        with self.assertRaises(RuntimeError):
            db.get_all_recipes()
        import set_up
        set_up.create_tables()
        self.assertEqual(db.get_recipe(recipe['id']), recipe)
        self.assertEqual(db.get_week_people(), 2)
        self.assertEqual(db.get_menu()['lunes']['comida']['people'], 4)
        self.assertTrue(next(i for i in db.get_shopping_list() if i['name']=='Arroz')['checked'])
        self.assertTrue(os.listdir(os.environ['BACKUP_DIR']))

    def test_migrate_v3_preserves_data_and_is_idempotent(self):
        os.unlink(db.DB_PATH)  # exclusivamente el archivo de TemporaryDirectory
        with closing(sqlite3.connect(db.DB_PATH)) as conn:
            conn.executescript("""
                CREATE TABLE recipes (id INTEGER PRIMARY KEY, name TEXT, type TEXT);
                CREATE TABLE ingredients (id INTEGER PRIMARY KEY, recipe_id INTEGER, position INTEGER, name TEXT, qty REAL, unit TEXT);
                CREATE TABLE menu (day TEXT, meal TEXT, recipe_id INTEGER, PRIMARY KEY(day, meal));
                CREATE TABLE shopping_checked (name TEXT, unit TEXT, PRIMARY KEY(name, unit));
                INSERT INTO recipes VALUES (41, 'Antigua', 'ambos');
                INSERT INTO ingredients VALUES (7, 41, 0, 'Arroz', 200, 'g');
                INSERT INTO menu VALUES ('lunes', 'comida', 41);
                INSERT INTO shopping_checked VALUES ('Arroz', 'g');
                PRAGMA user_version=3;
            """)
        import set_up
        set_up.create_tables()
        recipe = self.client.get('/recipes/41').json
        self.assertEqual((recipe["servings"], recipe["preparation"], recipe["notes"]), (2, [], ""))
        self.assertEqual(self.quantities(), {("Arroz", "g"): 200})
        self.assertTrue(self.client.get("/shopping-list").json[0]["checked"])
        import set_up
        set_up.create_tables()
        self.assertEqual(self.client.get('/recipes/41').json, recipe)
        with db.connection() as conn:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], db.SCHEMA_VERSION)
            self.assertEqual(conn.execute("SELECT id FROM ingredients").fetchone()[0], 7)


if __name__ == "__main__":
    unittest.main()
