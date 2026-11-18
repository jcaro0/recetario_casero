Pruebas del recetario
====================

Las pruebas utilizan bases SQLite temporales. No abren ni modifican la base de datos de la aplicación.

API, migración de versión 3 a 4, persistencia y cálculos (solo requiere las dependencias actuales del backend):

```sh
PYTHONPATH=backend python3 -m unittest discover -s tests -v
```

Recorrido completo con navegador, incluidos cancelar, Enter, preparación, notas, comensales y un ancho móvil de 375 px:

```sh
# Herramientas de desarrollo opcionales, en un entorno temporal:
python3 -m venv /tmp/recetario-tests
/tmp/recetario-tests/bin/pip install -r backend/requirements.txt playwright
CHROMIUM_PATH=/usr/bin/chromium PYTHONPATH=backend /tmp/recetario-tests/bin/python tests/browser_recipes.py
```

La prueba de navegador arranca su propio servidor local y lo detiene al terminar. Requiere Chromium instalado; `CHROMIUM_PATH` permite indicar su ubicación. Guarda una captura móvil en `/tmp/recetario-form-mobile.png`. No se añade Playwright a las dependencias de producción.

Comportamiento
-------------

- Enter recorre nombre, raciones y las columnas de ingredientes. Desde la unidad avanza a otra fila. Enter en una fila vacía pasa a preparación.
- En preparación, Enter avanza o añade un paso; un paso vacío lleva a notas. Mayús + Enter introduce una línea dentro del paso.
- En notas, Enter introduce una línea. Tab lleva al botón Guardar receta; Enter sobre ese botón guarda si los datos obligatorios son válidos.
- La edición guarda con PUT y conserva el identificador; Cancelar vuelve a recetas sin escribir.
- Los comensales se guardan por comida/cena. Sin selección explícita se usan las raciones originales, también después de editar la receta. «Originales» elimina la selección explícita.
- La migración se ejecuta explícitamente con `manage.py migrate`, con el servicio detenido y BACKUP_DIR configurado; primero verifica una copia. El arranque rechaza bases pendientes de migración. Añade columnas sin borrar recetas, ingredientes, menú ni marcas de compra; las recetas antiguas parten de 2 raciones y sin pasos/notas.
- En la compra se convierten kilos a gramos, litros a mililitros y alias de unidades. Otras unidades se mantienen separadas. Se redondea el total a 3 decimales, sin ceros decimales innecesarios.
- Las cantidades de texto libre se conservan sin multiplicar ni sumar; no se interpretan fracciones como `1/2` ni conversiones entre tazas, cucharadas y gramos.

El proyecto no tiene configurados un linter ni un proceso de compilación del frontend. Se comprueba la sintaxis con `node --check` y `python3 -m compileall -q backend tests`, además de `git diff --check`.


Seguridad y despliegue
---------------------

`test_operations.py` verifica copias con WAL, restauración sobre bases temporales,
retención, fallo de backup, rollback de migraciones, bases ausentes, esquemas futuros,
sesiones, CSRF y rutas/puertos previstos. La prueba de navegador también inicia sesión,
edita una receta con CSRF y cierra sesión.

Para comprobar el script desde otro directorio y el servidor Waitress real:

```sh
PYTHONPATH=backend /tmp/recetario-tests/bin/python tests/smoke_startup.py
```

Usa una base y una configuración temporal de venv; abre un puerto efímero, reinicia
el proceso, comprueba las recetas y confirma que una ruta ausente falla sin crearla.
No instala dependencias ni usa el puerto 80 o los datos del proyecto.

No se han ejecutado pruebas de despliegue contra la Raspberry ni contra el volumen
Docker real. Consulta README.md antes de actualizar cualquiera de esas instalaciones.
