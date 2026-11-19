# Cambios funcionales de Recetario

Se han implementado comensales semanales con confirmación al regenerar, actualización
masiva atómica y preferencia persistente. Cada hueco sigue siendo ajustable. La compra
se calcula con los días activos y no modifica las raciones originales.

Los ingredientes usan alias explícitos para agrupar singular/plural, decimales y
fracciones, y conversiones compatibles. Los nombres legibles se conservan en las
recetas. La compra mantiene cantidades textuales/desconocidas, reconoce marcas
antiguas y separa los productos comprados al final. El catálogo filtra en el navegador
por nombre e ingredientes ignorando mayúsculas y tildes.

Se han eliminado la página y scripts de acceso, sesiones, contraseña, CSRF asociado
y consultas de autenticación desde JavaScript. Cualquier dispositivo que acceda al
servicio puede escribir y borrar: no se debe exponer directamente a Internet.
Se conservan backups, herramientas SQLite, validaciones y migraciones explícitas.

La edición se ha comprobado realmente en Chromium: carga todos los campos, permite
cancelar, guarda con PUT sobre el mismo ID, no duplica y persiste al recargar.
El fallo original no se reprodujo en la revisión inicial del código disponible;
se ha retirado la dependencia de autenticación del guardado, aclarado el botón
«Guardar cambios» y reforzado la validación sin perder el formulario ante errores.

## Archivos modificados

- Backend: `backend/main.py`, `database.py`, `normalize.py`, `set_up.py`.
- Frontend: `frontend/templates/menu.html`, `recetas.html`; scripts `agregar_recetas.js`,
  `menu.js`, `recetas.js`, `lista_compra.js`, `script.js`; estilos `menu.css`,
  `recetas.css`, `lista_compra.css`.
- Configuración/documentación: `.gitignore`, `docker-compose.yaml`,
  `deploy/recetario.env.example`, `README.md`, este resumen y `tests/README.md`.
- Pruebas: `tests/test_recipes.py`, `test_operations.py`, `browser_recipes.py`,
  `smoke_startup.py`.
- Eliminados: `backend/security.py`, `frontend/login.html`,
  `frontend/scripts/login.js`.

## Validación ejecutada

- 34 pruebas automáticas de backend, operaciones y lanzadores: pasan. Incluyen reversión de
  actualización masiva por fallo SQL, migraciones con respaldo, preservación de IDs,
  marcas heredadas, cantidades desconocidas, unidades y días inactivos.
- Chromium real a 1280 × 900 y 375 × 812: creación, búsqueda, edición/cancelación,
  validación, persistencia, generación/cancelación, comensales semanales/individuales,
  compra, todos comprados y desmarcado. Sin errores JS ni errores de red de la app.
  Las fuentes externas se sustituyen por CSS vacío para aislar la prueba de Internet.
- Capturas: `tests/results/`, excluido de Git.
- Arranque/reinicio real con Waitress y `despliegue_raspberry.sh` desde otro directorio: pasa.
- Todas las bases utilizadas son temporales. No se han tocado las bases personales
  ni ejecutado migraciones reales. Los cambios se han organizado en commits por
  implementación, sin hacer push.

## Despliegue pendiente

Es necesaria la migración aditiva al esquema 5 (tabla `settings`). Sigue el README:
servicio detenido, base propia de cada instalación y `BACKUP_DIR` configurado para
que `manage.py migrate` cree y verifique primero el respaldo. Después reconstruye
y reinicia Docker o reinicia el servicio Raspberry. Siguen los puertos 8000 y 80;
no se añade Docker, Playwright, Node ni Chromium a las dependencias de Raspberry.

Se ha respetado el cambio local previo del usuario en Compose que retira el montaje
externo de `/backups`, manteniéndolo fuera de estos commits. Antes de migrar en Docker,
comprueba que `/backups` esté montado en un directorio persistente; declarar la ruta
sin montarla no conserva los respaldos. No se ha probado el despliegue sobre Docker o la Pi.

## Lanzadores separados

`despliegue_raspberry.sh` sustituye al lanzador anterior, conservando `install` y
`start`, el puerto 80 y la ruta de datos histórica. Se han actualizado la unidad
systemd, la ayuda del cron, la detección del directorio de código en los backups,
las pruebas y las instrucciones. Si ya hay una unidad instalada, hay que actualizar
su `ExecStart` y ejecutar `sudo systemctl daemon-reload` antes de reiniciar.

`despliegue_docker.sh` construye la imagen, crea la base si falta, valida su esquema y arranca
Compose en el puerto 8000. También admite `build`, `stop`, `status` y `logs`.
Las migraciones siguen siendo explícitas y los volúmenes se conservan.
Las pruebas del lanzador Docker simulan la orden Docker, sin tocar contenedores reales.

`ejecutar_test.sh` reúne backend, arranque/reinicio y Chromium; permite elegir una
suite. `install` prepara herramientas solo de desarrollo en `.venv-tests`.
Utiliza datos temporales y guarda registros/capturas en `tests/results/`.
Esta separación de scripts no requiere otra migración ni cambia los datos.
