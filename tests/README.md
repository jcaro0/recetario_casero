Pruebas del recetario
====================

Las pruebas utilizan bases SQLite temporales. No abren ni modifican la base de datos de la aplicación.

Desde el ordenador de desarrollo, prepara las herramientas una sola vez:

```sh
./ejecutar_test.sh install
```

Crea `.venv-tests` (excluido de Git), instala las dependencias del backend,
Playwright y Chromium. No cambia las dependencias ni el entorno de producción.
Si ya tienes Chromium, usa `CHROMIUM_PATH=/usr/bin/chromium ./ejecutar_test.sh install`
para omitir su descarga. `TEST_VENV_DIR` permite cambiar la carpeta del entorno.
En Linux pueden ser necesarias las bibliotecas del sistema que indique Playwright;
el script no instala paquetes del sistema ni usa sudo.

Ejecutar las pruebas no instala nada:

```sh
./ejecutar_test.sh          # Todas: backend, arranque/reinicio y navegador real
./ejecutar_test.sh backend # API, SQLite, migraciones y operaciones
./ejecutar_test.sh startup # Lanzador Raspberry y Waitress con reinicio real
./ejecutar_test.sh browser # Interfaz con Chromium, escritorio y móvil de 375 px
```

Para reutilizar un entorno de desarrollo existente:

```sh
TEST_PYTHON=/tmp/recetario-tests/bin/python ./ejecutar_test.sh
```

El lanzador funciona desde cualquier directorio. Reemplaza la configuración de datos
heredada por rutas temporales y no carga `RECETARIO_ENV`. Cada prueba prepara su
propia base SQLite temporal. Ante cualquier fallo devuelve un código de error y no
continúa con las siguientes suites. Guarda registros y capturas en `tests/results/`
(excluido de Git); `TEST_RESULTS_DIR` permite elegir otra carpeta de resultados.

La prueba de navegador levanta un servidor local aislado y lo detiene al terminar.
Usa `CHROMIUM_PATH` si lo indicas; si no, busca Chromium en el sistema y después el
instalado por Playwright. No se añade Playwright ni Chromium a producción o Raspberry.

Comportamiento
-------------

- Enter recorre nombre, raciones y las columnas de ingredientes. Desde la unidad avanza a otra fila. Enter en una fila vacía pasa a preparación.
- En preparación, Enter avanza o añade un paso; un paso vacío lleva a notas. Mayús + Enter introduce una línea dentro del paso.
- En notas, Enter introduce una línea. Tab lleva al botón Guardar receta; Enter sobre ese botón guarda si los datos obligatorios son válidos.
- La edición guarda con PUT y conserva el identificador; Cancelar vuelve a recetas sin escribir.
- Los comensales se guardan por comida/cena. Las nuevas asignaciones heredan la preferencia semanal (2 inicialmente). Un `people: null` explícito usa las raciones originales. «Originales» elimina la selección explícita.
- La migración se ejecuta explícitamente con `manage.py migrate`, con el servicio detenido y BACKUP_DIR configurado; primero verifica una copia. El arranque rechaza bases pendientes de migración. Añade columnas sin borrar recetas, ingredientes, menú ni marcas de compra; las recetas antiguas parten de 2 raciones y sin pasos/notas.
- En la compra se convierten kilos a gramos, litros a mililitros y alias de unidades. Otras unidades se mantienen separadas. Se redondea el total a 6 decimales, sin ceros decimales innecesarios.
- Las cantidades de texto libre se conservan sin multiplicar ni sumar; se interpretan decimales, fracciones y fracciones Unicode. No se convierten tazas o cucharadas a gramos.

El proyecto no tiene configurados un linter ni un proceso de compilación del frontend. Se comprueba la sintaxis con `node --check` y `python3 -m compileall -q backend tests`, además de `git diff --check`.


Seguridad y despliegue
---------------------

`test_operations.py` verifica copias con WAL, restauración sobre bases temporales,
retención, fallo de backup, rollback de migraciones, bases ausentes, esquemas futuros,
rutas y puertos previstos, edición sin autenticación y comensales semanales.
`test_scripts.py` comprueba los lanzadores desde otro directorio, el fallo de la
comprobación de base antes de arrancar Docker (con Docker simulado), la selección
del lanzador en systemd y el aislamiento/propagación de errores del ejecutor de tests.

Para comprobar el script desde otro directorio y el servidor Waitress real:

```sh
./ejecutar_test.sh startup
```

Usa una base y una configuración temporal de venv; abre un puerto efímero, reinicia
el proceso, comprueba las recetas y confirma que una ruta ausente falla sin crearla.
No instala dependencias ni usa el puerto 80 o los datos del proyecto.

No se han ejecutado pruebas de despliegue contra la Raspberry ni contra el volumen
Docker real. Consulta README.md antes de actualizar cualquiera de esas instalaciones.

La copia semanal mediante `deploy/backup-weekly.sh` se prueba desde otro directorio,
con un archivo de configuración temporal. Tras tres ejecuciones quedan las dos
últimas copias válidas; si falta la base activa no se purgan los respaldos existentes.

## Compra manual, PWA y solo lectura

La suite de backend prueba la migración 5 → 6, la independencia de los productos
manuales y la instantánea de consulta de SQLite. El arranque comprueba la
persistencia tras reiniciar Waitress.

Chromium prueba en escritorio y móvil la compra manual y la PWA. Simula publicar
nuevos recursos, desconectar la red, reabrir con la caché, perder solo el acceso
al servidor y recuperar la conexión. Comprueba también que un fallo de descarga
mantiene bloqueada la escritura y que la reconexión muestra los cambios de otra
sesión. Se usan únicamente bases SQLite temporales. La instalación real en
Android e iPhone y el HTTPS de la Raspberry se comprueban por separado.
