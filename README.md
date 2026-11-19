# Mantener Recetario sin perder recetas

Para una visión general breve, consulta [Resumen de cambios](RESUMEN_CAMBIOS.md).

El código y los datos se actualizan por separado. Cada instalación tiene su propia
base: **nunca copies la base del ordenador sobre la de la Raspberry**. Los cambios
que estaban sin confirmar en recetas, raciones, preparación, notas y menú se mantienen.
No se ha accedido a la Raspberry ni migrado la base real del ordenador.

## Scripts de despliegue y pruebas

Los tres lanzadores se pueden ejecutar desde cualquier directorio y tienen `--help`:

```sh
# Ordenador: construir, comprobar la base existente y arrancar en el puerto 8000.
./despliegue_docker.sh
# También admite: build, stop, status y logs.

# Raspberry: preparar dependencias una vez; reinstalar si cambia requirements.txt.
./despliegue_raspberry.sh install
# Arranque con configuración cargada (puerto 80; usar systemd para ese puerto).
./despliegue_raspberry.sh start

# Solo en el ordenador de desarrollo: preparar herramientas de prueba una vez.
./ejecutar_test.sh install
# Ejecutar backend, arranque/reinicio y navegador, siempre con bases temporales.
./ejecutar_test.sh
# También permite ejecutar por separado: backend, startup o browser.
```

Los lanzadores de despliegue no inicializan ni migran bases automáticamente.
No instalan herramientas de prueba en Raspberry. `ejecutar_test.sh install` crea
`.venv-tests` e instala Playwright y su Chromium; si ya tienes un Chromium, indica
`CHROMIUM_PATH=/ruta/chromium` para omitir la descarga. No modifica Python del sistema.
Los siguientes tests no instalan nada. Para aprovechar otro entorno de desarrollo,
usa `TEST_PYTHON=/ruta/venv/bin/python ./ejecutar_test.sh`.
Los resultados se guardan en `tests/results/` (excluido de Git).

Si ya tienes el servicio Raspberry instalado con el nombre anterior del lanzador,
actualiza `ExecStart` a `/RUTA/AL/recetario/despliegue_raspberry.sh start` en la unidad
instalada y ejecuta `sudo systemctl daemon-reload` antes de reiniciarlo. El ejemplo
`deploy/recetario.service` ya está actualizado; conserva tu usuario y rutas propios.

## Rutas y comportamiento

| Entorno | Puerto | Base activa |
| --- | --- | --- |
| Docker Compose | 8000 | `./backend/data/recetario.db` en el ordenador, montada como `/app/data/recetario.db` |
| Raspberry: `despliegue_raspberry.sh` sin configurar | 80 | `<repositorio>/data/recetario.db` |
| Backend Python sin `DB_PATH` | 8000 por defecto | `<repositorio>/backend/data/recetario.db` |
| Raspberry: instalación recomendada | 80 | `/home/pi/.local/share/recetario/recetario.db`, después de copiar y verificar la base activa |

`DB_PATH` tiene prioridad y debe ser absoluto. No se busca automáticamente otra base
si falta el archivo: el arranque falla. Una base vacía, incompleta o demasiado nueva
también detiene el arranque. No hay restauraciones ni migraciones automáticas.

El script antiguo elegía `data/recetario.db`, mientras el backend y Docker elegían
`backend/data/recetario.db`. **Si existen ambas, no elijas solo por fecha o tamaño**:
comprueba qué ruta usaba el proceso y qué recetas contiene cada una. No se fusionan
ni se trasladan silenciosamente. `despliegue_raspberry.sh` conserva esa ruta histórica.

Para comprobar una instalación configurada:

```sh
# Raspberry, desde el repositorio y con un archivo propio de confianza:
set -a
. /home/pi/.config/recetario/recetario.env
set +a
.venv/bin/python backend/manage.py info
# Docker (si ya está arrancado):
docker compose exec backend python manage.py info
# Docker detenido:
docker compose run --rm --no-deps backend python manage.py info
```

`info` imprime ruta, versión del esquema y número de recetas, y comprueba integridad
y relaciones sin migrar. El arranque de Waitress también imprime la ruta seleccionada.
En una instalación antigua, identifica el PID de Python y su comando/directorio de
trabajo con `ps -eo pid,user,args` y `readlink /proc/PID/cwd`. Puedes ver únicamente su
variable de base (sin imprimir otros secretos) así:

```sh
python3 - PID <<'PY'
import sys
from pathlib import Path
for value in Path('/proc/' + sys.argv[1] + '/environ').read_bytes().split(b'\0'):
    if value.startswith(b'DB_PATH='):
        print(value.decode())
PY
```

Si no hay variable, revisa cómo se arrancó: el lanzador de Raspberry exporta su propia ruta.
En Docker la ruta del contenedor se corresponde con el montaje de Compose.

## Ordenador: Docker Compose

Se conservan puerto, frontend y montaje de datos. Se excluye `data/` del contexto de
la imagen: reconstruirla no incorpora una base procedente de Git. El montaje del
host sigue siendo la fuente de verdad. No borres ese directorio ni sus auxiliares WAL.

1. Crea un directorio de copias **permanente y externo al repositorio**:

   ```sh
   mkdir -p "$HOME/.local/share/recetario-docker-backups"
   export RECETARIO_BACKUP_DIR="$HOME/.local/share/recetario-docker-backups"
   ```

   Guarda esa asignación con ruta absoluta en un `.env` local si quieres que
   Compose la recuerde. Ese archivo no se versiona. No utilices `/tmp` para copias permanentes.

2. Detén la aplicación antes de actualizar el esquema y construye la imagen:

   ```sh
   ./despliegue_docker.sh stop
   ./despliegue_docker.sh build
   docker compose run --rm --no-deps backend python manage.py info
   docker compose run --rm --no-deps backend python manage.py backup
   docker compose run --rm --no-deps backend python manage.py migrate
   docker compose run --rm --no-deps backend python manage.py info
   ./despliegue_docker.sh
   ```

   La base existente del ordenador necesita la migración explícita al esquema actual (6).
   `migrate` crea además su propia copia previa verificada. Si falla, no arranques
   hasta resolver la causa. No sustituyas los datos para forzar el arranque.

3. Abre `http://localhost:8000`. Para otros equipos: `http://IP_DEL_ORDENADOR:8000`.

**Solo instalación completamente nueva:** si nunca has tenido recetas ni una base
que conservar, ejecuta `docker compose run --rm --no-deps backend python manage.py init`
tras construir la imagen. `init` falla si ya existe un archivo; no lo borres para repetirlo.
Un clon antiguo puede traer una base versionada: no la confundas con una instalación vacía.
No se ha probado aquí un despliegue contra el volumen real para evitar migrarlo.

## Raspberry Pi Zero W: Python sin Docker

Requiere Python 3.9 o superior (ver `python3 --version`) y `python3-venv`. No reemplaces
el Python del sistema a mano. Si tu Raspberry Pi OS es antiguo, prepara su actualización
con una copia externa de los datos antes de continuar. Waitress es un servidor WSGI de
Python puro: un proceso, dos hilos, sin Nginx ni contenedores.

Los ejemplos usan usuario `pi` y repositorio `/home/pi/recetario`. **Sustitúyelos por
los tuyos** en archivos de configuración, servicios y comandos.

1. Si ya hay recetas, completa primero «Primer despliegue seguro» más abajo,
   **antes de actualizar Git**. No ejecutes `init` sobre una instalación existente.
2. Prepara las dependencias como usuario normal:

   ```sh
   sudo apt-get install python3 python3-venv
   cd /home/pi/recetario
   ./despliegue_raspberry.sh install
   mkdir -p /home/pi/.config/recetario
   chmod 700 /home/pi/.config/recetario
   cp deploy/recetario.env.example /home/pi/.config/recetario/recetario.env
   chmod 600 /home/pi/.config/recetario/recetario.env
   ```

   Edita ese archivo: `DB_PATH` debe indicar la base **ya verificada**,
   `BACKUP_DIR` un directorio externo permanente y `PORT=80`.
   Las opciones se respetan desde el entorno. Para un arranque manual puedes usar
   `RECETARIO_ENV=/home/pi/.config/recetario/recetario.env ./despliegue_raspberry.sh start`.
   El archivo se interpreta como shell: úsalo solo si es tuyo y de confianza.
   En systemd se usa `EnvironmentFile`; usa asignaciones simples con rutas absolutas.

3. Carga la configuración y comprueba/migra con el servicio detenido:

   ```sh
   set -a
   . /home/pi/.config/recetario/recetario.env
   set +a
   # SOLO si esta instalación empieza de cero, sin base ni datos anteriores:
   # .venv/bin/python backend/manage.py init
   .venv/bin/python backend/manage.py info
   .venv/bin/python backend/manage.py migrate
   .venv/bin/python backend/manage.py info
   ```

   **Solo instalación nueva sin datos anteriores:** `manage.py init`, en lugar de
   migrar una base ausente. Si no tienes certeza, detente y busca la base anterior.

4. Edita `deploy/recetario.service`: usuario, directorio, archivo de entorno y
   `ExecStart`. Instala el servicio:

   ```sh
   sudo cp deploy/recetario.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now recetario
   systemctl status recetario
   journalctl -u recetario -n 40 --no-pager
   ```

   El proceso usa `User=pi` y solo `CAP_NET_BIND_SERVICE` para escuchar en el
   puerto 80. El script rechaza root. No uses `sudo ./despliegue_raspberry.sh`, ni pongas capacidades
   sobre el intérprete global de Python. Comprueba que tu systemd admite
   `AmbientCapabilities`; si no, actualiza el sistema antes de instalar el servicio.
   El arranque manual sin esa capacidad puede fallar en el puerto 80 y lo explica.
   Otro servicio que ya ocupe el 80 debe resolverse antes de arrancar Recetario.

5. Abre `http://IP_DE_LA_RASPBERRY/` desde el móvil o el ordenador en la misma red.
   El servidor escucha en `0.0.0.0`; permite el puerto 80 en tu cortafuegos local
   si lo usas. Las dependencias solo se instalan con `./despliegue_raspberry.sh install`:
   los siguientes arranques no ejecutan pip. Si cambia requirements, vuelve a instalar.

## Copias semanales: conservar las dos últimas

```sh
# Raspberry, configuración cargada como arriba:
.venv/bin/python backend/manage.py backup
# Docker:
docker compose exec backend python manage.py backup
```

`BACKUP_DIR` es obligatorio y absoluto. Elige una carpeta externa al repositorio,
a la imagen y a los directorios de datos que podrías reemplazar. Cada máquina debe
tener su propia carpeta. Las copias usan la API de SQLite, incorporan cambios
confirmados en WAL, se verifican con `integrity_check` y `foreign_key_check`, y
se publican después de sincronizar el archivo y el directorio. Los nombres contienen
fecha/hora UTC, identificador de origen y sufijo aleatorio. Se puede respaldar mientras
se usa la aplicación; una copia no contiene las escrituras posteriores a su snapshot.

`BACKUP_RETAIN=2` conserva las últimas 2 copias válidas **de cada origen y clase**
(manual/semanal; también se mantiene compatibilidad con la clase diaria). También puedes pasar `--retain 7`. Cero o valores negativos conservan
al menos una válida. Las copias dañadas no cuentan como válidas y no se borran
silenciosamente. Las copias de antes de migrar o restaurar no se purgan automáticamente:
revísalas manualmente cuando ya hayas validado el cambio. Vigila el espacio libre.
Una copia en la misma tarjeta SD no protege frente a su avería: copia periódicamente
los respaldos verificados a otro dispositivo.

**Raspberry con cron (opción recomendada para esta instalación):**

1. En el archivo externo `recetario.env`, deja `BACKUP_RETAIN=2`. Comprueba que
   `DB_PATH` apunta a tu base activa y `BACKUP_DIR` a una carpeta permanente externa.
2. Ejecuta manualmente `/home/pi/recetario/deploy/backup-weekly.sh` y comprueba la
   ruta de la copia generada. Funciona desde cualquier directorio y carga el mismo
   archivo de configuración que la aplicación. Puedes cambiarlo con `RECETARIO_ENV`.
3. Comprueba que cron está instalado y activo (`systemctl status cron`). En Raspberry
   Pi OS, si falta: `sudo apt-get install cron` y `sudo systemctl enable --now cron`.
4. Como propietario de Recetario, abre `crontab -e` y añade esta línea, sustituyendo
   usuario y rutas (también disponible en `deploy/recetario.crontab.example`):

```cron
0 3 * * 0 /home/pi/recetario/deploy/backup-weekly.sh >> /home/pi/.local/share/recetario-backup.log 2>&1
```

Se ejecuta cada **domingo a las 03:00, hora local de la Raspberry**. Confirma la zona
horaria con `timedatectl`. Revisa `crontab -l` y el log tras la primera ejecución.
Cron no recupera ejecuciones perdidas si la Pi está apagada en ese momento.

En la tercera copia semanal válida se elimina la semanal más antigua; quedan las
**dos últimas válidas**. Si falla la nueva copia, no se purgan las anteriores.
Las copias manuales y de antes de migrar/restaurar se gestionan por separado, por
lo que pueden existir más de dos archivos en la carpeta. No son bases activas.
Una copia semanal permite perder hasta una semana de cambios si falla la SD.

**Alternativa systemd (no activar junto a cron):** adapta usuario/rutas en los dos
archivos de backup y usa el mismo `EnvironmentFile` que la aplicación:

```sh
sudo cp deploy/recetario-backup.service deploy/recetario-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start recetario-backup.service
journalctl -u recetario-backup.service -n 30 --no-pager
sudo systemctl enable --now recetario-backup.timer
```

También está configurado para los domingos hacia las 03:00. `Persistent=true`
recupera una ejecución pendiente si estaba apagada. Para pasar de un timer anterior
a cron, primero ejecuta `sudo systemctl disable --now recetario-backup.timer`.
No queda ningún proceso Python de copias residente en ninguna de las dos opciones.

En el ordenador puedes programar una copia semanal con cron (Docker debe estar activo
 y Compose debe leer tu `.env` con `RECETARIO_BACKUP_DIR`):

```cron
0 3 * * 0 cd /RUTA/AL/recetario && /usr/bin/docker compose exec -T backend python manage.py backup --label weekly --retain 2 >> /RUTA/EXTERNA/backup-docker.log 2>&1
```

Referencia: [formato de crontab en Debian](https://manpages.debian.org/bookworm/cron/crontab.5.en.html).

## Restauración: solo por decisión explícita

**Restaurar puede perder recetas, menú y cambios posteriores a la fecha del respaldo.**
Nunca se hace para solucionar automáticamente un error de arranque. Primero revisa
`DB_PATH`: las recetas «desaparecidas» suelen indicar que estás mirando otra base.

1. Ejecuta `manage.py info` con la configuración de esa instalación y anota la ruta.
2. Detén **todos** los procesos que puedan escribir: `sudo systemctl stop recetario`
   o `docker compose stop backend`. Comprueba que no hay otro arranque manual.
   No basta con cerrar el navegador. No elimines archivos `-wal` ni `-shm`.
3. Identifica el respaldo correcto y compruébalo, sin restaurar:

   ```sh
   .venv/bin/python backend/manage.py --db /RUTA/AL/RESPALDO.sqlite3 info
   ```

4. Restaura solo si aceptas perder los cambios posteriores:

   ```sh
   .venv/bin/python backend/manage.py restore /RUTA/AL/RESPALDO.sqlite3 \
     --writers-stopped --confirm-active-path "$DB_PATH"
   ```

   La orden exige confirmar **la ruta exacta** y declarar que has parado los escritores.
   Esto no puede comprobar automáticamente aplicaciones externas: es tu responsabilidad
   detenerlas. Antes de escribir crea y verifica una copia del estado actual; si falla,
   no restaura. Usa la API de SQLite sobre el archivo existente, sin intercambiar
   archivos con un WAL pendiente. Si hay un fallo de E/S, mantén la aplicación parada,
   conserva ambas copias y revisa el error antes de reintentar.

   En Docker usa el contenedor puntual, con rutas **del contenedor**:

   ```sh
   docker compose run --rm --no-deps backend python manage.py --db /backups/NOMBRE.sqlite3 info
   docker compose run --rm --no-deps backend python manage.py restore /backups/NOMBRE.sqlite3 \
     --writers-stopped --confirm-active-path /app/data/recetario.db
   ```

5. Ejecuta `manage.py info` otra vez sobre la base activa. Si la copia era de un
   esquema antiguo, ejecuta `manage.py migrate` con el servicio aún detenido.
   Arranca y comprueba recetas concretas, ingredientes, notas y menú. No compares
   solamente el número total de recetas. Las restauraciones de prueba se hacen
   únicamente en bases temporales (ver `tests/test_operations.py`).

## Acceso desde la red local

La aplicación funciona sin cuentas, sesiones de autenticación ni contraseña.
Cualquier dispositivo con acceso a la red donde escucha puede realizar operaciones
de escritura, incluidas modificaciones y borrados. No expongas el servicio
directamente a Internet ni abras sus puertos en el router.

## Git: datos fuera del seguimiento

`backend/data/recetario.db` se ha retirado del seguimiento con `git rm --cached`,
**conservando físicamente la base local**. Antes se creó una copia consistente y
verificada fuera del repositorio, en `/home/jaime/.local/share/recetario-docker-backups`.
La Raspberry se instalará de cero: no necesita recibir la base del ordenador.
`.gitignore` excluye las bases y sus auxiliares; `.dockerignore` evita incluirlos en imágenes.

Un clon nuevo ya no trae una base antigua. En una instalación nueva configura
`DB_PATH` externo y ejecuta `manage.py init` una sola vez, sin copiar datos desde Git.
Docker sigue utilizando la base local existente mediante su montaje persistente.

**Otros clones existentes con datos reales:** antes de recibir este cambio, sigue el
procedimiento de protección al final de esta guía. Git puede eliminar el archivo que
antes estaba versionado al aplicar su retirada. No hagas pull antes de respaldarlo y
configurar una base externa verificada. No uses `git clean`, `reset --hard` o
`checkout` sobre datos. No se ha reescrito el historial: revisiones antiguas aún
pueden contener la antigua base y no deben desplegarse sobre datos actuales.

## Si después de actualizar parecen faltar recetas

Detén el servicio y no escribas nuevas recetas todavía. Revisa el log de arranque,
el `DB_PATH` del servicio y su directorio de trabajo. Comprueba la ruta con `info`.
No ejecutes `init`, no borres WAL y no restaures una copia antigua por impulso.
Busca las rutas históricas `data/recetario.db` y `backend/data/recetario.db`, y los
montajes Docker. Si la base correcta existe, vuelve a configurar **esa ruta**, respáldala,
y migra solo si hace falta. Si hay dos bases con recetas nuevas, conserva copias de
ambas: necesitarán una revisión de fusión, nunca sustituir una por la otra.

## Pruebas

```sh
./ejecutar_test.sh          # Backend, arranque/reinicio y navegador
./ejecutar_test.sh backend  # Solo backend y operaciones
```

Todas las bases se crean en directorios temporales. Hay pruebas de CRUD, persistencia,
raciones, unidades, lista de compra, migraciones 1, 3 y 4 a 5, conservación de IDs/menú,
rollback de DDL, fallo de backup, WAL, retención, restauración, archivos ausentes,
esquemas incompatibles y acceso sin autenticación. Las pruebas de navegador y arranque real
están en [tests/README.md](tests/README.md); requieren permisos para sockets locales.
No ejecutes `backend/meter_recetas_prueba.sh` contra datos reales.

Referencias técnicas: [API de backup SQLite](https://sqlite.org/backup.html),
[capacidades y usuarios en systemd](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html),
[Waitress](https://docs.pylonsproject.org/projects/waitress/en/stable/),
[seguridad de Flask](https://flask.palletsprojects.com/en/stable/web-security/).

## PROCEDIMIENTO SEGURO PARA ACTUALIZAR MI RASPBERRY PI

### Instalación nueva de esta Raspberry (sin datos anteriores)

Sigue la sección «Raspberry Pi Zero W: Python sin Docker»: instala dependencias,
crea el archivo externo `recetario.env` y carga sus variables. Ejecuta entonces
`.venv/bin/python backend/manage.py init` **una sola vez**. Instala el servicio
del puerto 80 y programa el cron semanal según la sección de copias. No transfieras
la base del ordenador. Desde entonces utiliza el procedimiento de actualizaciones
posteriores; no vuelvas a ejecutar `init`.

### Solo instalaciones existentes: antes del primer `git pull`

1. **Identifica la base activa** usando el proceso/configuración y las rutas de la
   tabla inicial. Anota recetas recientes reconocibles, IDs y número de recetas.
   Comprueba también ingredientes, raciones, preparación, notas y menú.
2. **Detén la aplicación antigua** (`sudo systemctl stop recetario`, o Ctrl+C si
   corre en una terminal). Comprueba que no queda otro Python escribiendo. Durante
   este mantenimiento no añadas recetas; las creadas hasta este momento deben entrar
   en la copia. No actualices Git todavía.
3. Desde el ordenador, copia **solo el auxiliar**, sin bases, a la Pi:

   ```sh
   scp deploy/protect_existing.py pi@IP_DE_LA_RASPBERRY:/tmp/recetario-protect.py
   ```

   Sustituye usuario/IP. Este archivo funciona con la biblioteca estándar, sin el
   código nuevo ni dependencias instaladas. También puedes trasladarlo por USB.
4. En la Raspberry, como el propietario de los datos, indicando **la fuente real**:

   ```sh
   python3 /tmp/recetario-protect.py \
     --source /RUTA/EXACTA/DE/LA/BASE/ACTIVA.db \
     --target /home/pi/.local/share/recetario/recetario.db \
     --backup-dir /home/pi/.local/share/recetario-backups \
     --writers-stopped
   ```

   Usa SQLite backup, verifica integridad/relaciones y recuentos, guarda una copia
   externa y publica una base externa sin borrar la original. **Falla si el destino
   ya existe**: no lo borres para repetir el comando; averigua si ya contiene datos
   más recientes. Si falla cualquier verificación, no sigas con la actualización.
   Anota el respaldo, revisa los recuentos y guarda otra copia fuera de la SD.
5. La base externa verificada pasa a ser la fuente de verdad. El fichero del
   repositorio se conserva como original, pero no se volverá a usar para arrancar.
   Ahora revisa `git status` y actualiza el código con `git pull --ff-only` cuando
   tus cambios locales estén resueltos. Si Git lo rechaza, conserva todo y resuelve
   los cambios sin forzar ni restaurar archivos de base de datos.
6. Instala dependencias (`./despliegue_raspberry.sh install`), configura `recetario.env` con
   **la base externa** y `PORT=80`, y adapta los servicios como se explica arriba.
7. Carga la configuración. Ejecuta `manage.py info`, después `manage.py migrate`
   (hace otra copia verificada) y de nuevo `manage.py info`, siempre con el servicio
   detenido. Si falla, mantén el servicio parado; no uses `init` ni una restauración automática.
8. Instala/arranca el servicio sin root, comprueba su log y su `DB_PATH`. Desde otro
   dispositivo revisa las recetas más recientes y sus detalles, así como el menú.
   Solo entonces vuelve a permitir uso normal y programa cron (o el timer alternativo).

### Actualizaciones posteriores

1. Antes de modificar Git, carga el archivo de configuración de **esa Pi**, ejecuta
   `manage.py info` y comprueba que la base está fuera del repositorio.
2. Deja de añadir recetas y detén el servicio. Crea una copia manual verificada de
   **la base actual**, no de la que había al empezar a desarrollar una versión:

   ```sh
   cd /home/pi/recetario
   set -a
   . /home/pi/.config/recetario/recetario.env
   set +a
   sudo systemctl stop recetario
   .venv/bin/python backend/manage.py info
   .venv/bin/python backend/manage.py backup
   ```

3. Si el backup falla, **no continúes**. Si funciona, revisa `git status` y ejecuta
   `git pull --ff-only`. No transfieras ninguna base desde el ordenador.
4. Ejecuta `./despliegue_raspberry.sh install` cuando cambien las dependencias. Ejecuta
   `.venv/bin/python backend/manage.py migrate`: comprueba la versión y crea una
   copia adicional si hace falta migrar. Luego repite `manage.py info`.
5. Arranca `sudo systemctl start recetario`, revisa `journalctl -u recetario -n 40`
   y comprueba desde el móvil las últimas recetas, notas y planificación.
6. Comprueba cron (o el timer si lo elegiste) y su último respaldo. Si algo falla, conserva los datos y
   las copias, mantén parado el servicio si hay dudas y revisa configuración/esquema.
   Volver a un código antiguo puede ser incompatible con el esquema nuevo:
   **no restaures una base antigua para que arranque**.

Así, si tenías 20 recetas y añadiste 5 durante el desarrollo, el respaldo y la
migración toman la base **actual con 25**, conservando sus IDs y relaciones.

## Comensales semanales, ingredientes y actualización del esquema 5

Al regenerar, la confirmación pide un entero positivo e inicia con el último valor
semanal o 2. Cancelar no escribe nada. «Aplicar a todo el menú» guarda la preferencia
y actualiza todos los huecos, incluidos los vacíos, en una sola transacción; no
cambia recetas ni sus raciones. Las nuevas asignaciones heredan la preferencia.
Puedes ajustar cada comida después; «Originales» vuelve a las raciones de la receta.
Los días inactivos siguen excluidos de la compra.

Los alias de ingredientes se definen explícitamente en `backend/normalize.py`.
Se aplican al cálculo y a las marcas, sin reescribir los nombres de las recetas.
Tomate, tomate frito y tomate triturado permanecen separados. Las cantidades de
texto y las desconocidas se conservan; solo las numéricas se escalan. Se suman
kg/g y l/ml, y los alias de unidades compatibles; cucharadas, cucharaditas y tazas
se mantienen separadas entre sí y de los gramos. Las marcas antiguas se reconocen
por nombre y unidad compatibles, y desmarcar elimina también sus alias antiguos.
Si se fusionan varias filas equivalentes, una marca existente del mismo ingrediente
y unidad compatible marca la fila resultante; unidades incompatibles nunca se cruzan.

Esta actualización requiere una migración aditiva a la versión 5: crea `settings`
para la preferencia semanal. No transforma recetas ni marcas existentes. En **cada
instalación**, detén la aplicación y ejecuta el procedimiento de migración ya
documentado con `DB_PATH` apuntando a su propia base y `BACKUP_DIR` configurado.
`manage.py migrate` crea y verifica el respaldo antes de modificar el esquema;
si falla, revierte la transacción. No ejecutes `init` sobre una base existente.
Después reconstruye/reinicia Docker (8000) o reinicia el servicio Raspberry (80).
No se necesitan dependencias adicionales de producción. Elimina las antiguas
variables de configuración de acceso si aún están en tu archivo de entorno.

Las pruebas de desarrollo y evidencias se describen en `tests/README.md`.


## Productos manuales en la compra

En **Compra**, escribe un nombre y, si hace falta, una cantidad o unidad. Puedes
editar el producto desde su fila, borrarlo o marcarlo como comprado. Se comparte
junto con los ingredientes del menú. Las filas manuales conservan su contenido y
sus marcas aunque regeneres el menú, incluso si coinciden por nombre con un
ingrediente calculado.

El esquema **6** añade únicamente la tabla `manual_products`. Si tu base usa
una versión anterior, detén el servicio y ejecuta `manage.py migrate` en esa
instalación según los pasos de Docker o Raspberry de este documento. El comando
crea y verifica primero una copia en `BACKUP_DIR`. No uses `init` en una base existente.

## Instalar Recetario como aplicación

Abre la **URL HTTPS de confianza** de tu instalación con el móvil conectado a tu
red local. En el propio ordenador, Chromium también admite el contexto seguro
de `http://localhost:8000`. Desde el móvil debes usar HTTPS si accedes por la IP
local del ordenador o de la Raspberry.

- **Android (Chrome).** Abre el menú ⋮, elige **Añadir a pantalla de inicio** y
  después **Instalar** si Chrome muestra ambas opciones.
- **iPhone (Safari).** Pulsa **Compartir → Añadir a pantalla de inicio**. Activa
  **Abrir como app web** si aparece esa opción y pulsa **Añadir**.

Consulta las guías de [Chrome para Android](https://support.google.com/chrome/answer/9658361?hl=es)
y [Safari en iPhone](https://support.apple.com/es-es/guide/iphone/iphea86e5236/ios).
Tras publicar cambios de interfaz, cierra todas las pestañas o ventanas instaladas
de Recetario y vuelve a abrirlo para que se active la nueva versión de recursos.

### HTTPS en Raspberry Pi Zero W

Puedes añadir Nginx únicamente para terminar TLS en el puerto **443** de la IP
local. Waitress conserva **80** y la misma base SQLite. Reserva una IP fija para
la Raspberry en el router para que el certificado siga coincidiendo con la URL.
Mantén ambos puertos en la red local y evita redirecciones desde Internet. Si
ya tienes un proxy local, puedes reutilizarlo. El siguiente ejemplo usa
`192.168.1.50`. Sustitúyela por la IP de tu Raspberry.

En un ordenador de confianza, crea una autoridad privada y un certificado de
servidor con esa IP en el SAN. Conserva `ca.key` cifrada en el ordenador.

```sh
mkdir -m 700 recetario-tls
cd recetario-tls
umask 077
RECETARIO_IP=192.168.1.50

openssl genrsa -aes256 -out ca.key 2048
openssl req -x509 -new -key ca.key -sha256 -days 3650 -out ca.crt \
  -subj '/CN=Recetario CA local' \
  -addext 'basicConstraints=critical,CA:TRUE,pathlen:0' \
  -addext 'keyUsage=critical,keyCertSign,cRLSign'

openssl req -new -newkey rsa:2048 -nodes -keyout server.key -out server.csr \
  -subj "/CN=$RECETARIO_IP"
cat > server.ext <<EOF_EXT
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=IP:$RECETARIO_IP
EOF_EXT
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -sha256 -days 365 -extfile server.ext -out server.crt
openssl x509 -in ca.crt -outform DER -out recetario-ca.cer
```

Copia solo `server.crt` y `server.key` a la Raspberry. Instálalos en
`/etc/nginx/recetario/` como root, con permiso `600` para la clave del servidor.
Instala el paquete `nginx` de Raspberry Pi OS. Si la instalación habilita el
sitio de ejemplo en el puerto 80, deshabilita **ese sitio de ejemplo** antes de
ejecutar ambos servidores. Puedes parar temporalmente Recetario mientras instalas
el paquete para evitar que el sitio de ejemplo intente ocupar el puerto.

Adapta [deploy/recetario.nginx.example](deploy/recetario.nginx.example), instálalo
como `/etc/nginx/sites-available/recetario` y enlázalo desde `sites-enabled`.
Comprueba la configuración con `sudo nginx -t`, arranca Recetario y recarga Nginx.
Desde el ordenador, verifica el certificado y el proxy con
`curl --cacert ca.crt https://192.168.1.50/manifest.webmanifest`. Renueva el
certificado de servidor antes de los 365 días y recarga Nginx.
Consulta la [documentación de HTTPS en Nginx](https://nginx.org/en/docs/http/configuring_https_servers.html).

Transfiere **solo el certificado público** `recetario-ca.cer` al móvil por un
medio de confianza. En Android, busca en Ajustes la opción **Instalar un
certificado → Certificado de CA**. En iPhone, abre e instala el perfil y activa
la confianza completa en **Ajustes → General → Información → Ajustes de confianza
de los certificados**. Comprueba que la URL HTTPS abra sin avisos antes de
instalar Recetario. [Apple y certificados instalados manualmente](https://support.apple.com/es-es/102390)

Las pruebas automatizadas comprueban Chromium en escritorio y resolución móvil.
En cada teléfono quedan por verificar la instalación, el icono, la apertura
desde la pantalla de inicio y el acceso al proxy por HTTPS.
