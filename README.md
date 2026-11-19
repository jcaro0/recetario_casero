# Mantener Recetario sin perder recetas

Para una visión general breve, consulta [Resumen de cambios](RESUMEN_CAMBIOS.md).

El código y los datos se actualizan por separado. Cada instalación tiene su propia
base: **nunca copies la base del ordenador sobre la de la Raspberry**. Los cambios
que estaban sin confirmar en recetas, raciones, preparación, notas y menú se mantienen.
No se ha accedido a la Raspberry ni migrado la base real del ordenador.

## Scripts de despliegue y pruebas

Los tres lanzadores se pueden ejecutar desde cualquier directorio y tienen `--help`:

```sh
# Ordenador: construir, preparar la base y arrancar en el puerto 8000.
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

Docker Compose inicializa la base cuando falta el archivo. En Raspberry, la
inicialización se hace con `manage.py init`. Las migraciones siguen siendo explícitas.
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
| Raspberry: instalación recomendada | 80 | `/home/pizero/.local/share/recetario/recetario.db`, después de copiar y verificar la base activa |

`DB_PATH` tiene prioridad y debe ser absoluto. Si falta el archivo, Docker Compose
crea una base nueva en esa ruta. En Raspberry, el arranque avisa de la ausencia.
Una base existente vacía, incompleta o demasiado nueva detiene el arranque.
Las restauraciones y migraciones se ejecutan por separado.

El script antiguo elegía `data/recetario.db`, mientras el backend y Docker elegían
`backend/data/recetario.db`. **Si existen ambas, no elijas solo por fecha o tamaño**:
comprueba qué ruta usaba el proceso y qué recetas contiene cada una. No se fusionan
ni se trasladan silenciosamente. `despliegue_raspberry.sh` conserva esa ruta histórica.

Para comprobar una instalación configurada:

```sh
# Raspberry, desde el repositorio y con un archivo propio de confianza:
set -a
. /home/pizero/.config/recetario/recetario.env
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

**Instalación nueva:** tras configurar las copias, ejecuta `./despliegue_docker.sh start`.
Si falta `backend/data/recetario.db`, el arranque crea una base sin recetas con el
esquema actual. Si esperabas encontrar recetas, revisa primero el montaje y las
copias. Si falta la base pero quedan archivos WAL, SHM o journal con el mismo
nombre, el arranque espera a que revises esos archivos.

## Raspberry Pi Zero W: Python sin Docker

Requiere Python 3.9 o superior (ver `python3 --version`) y `python3-venv`. No reemplaces
el Python del sistema a mano. Si tu Raspberry Pi OS es antiguo, prepara su actualización
con una copia externa de los datos antes de continuar. Waitress es un servidor WSGI de
Python puro: un proceso, dos hilos, sin Nginx ni contenedores.

Los ejemplos usan usuario `pizero` y repositorio `/home/pizero/recetario`. **Sustitúyelos por
los tuyos** en archivos de configuración, servicios y comandos.

1. Si ya hay recetas, completa primero «Primer despliegue seguro» más abajo,
   **antes de actualizar Git**. No ejecutes `init` sobre una instalación existente.
2. Prepara las dependencias como usuario normal:

   ```sh
   sudo apt-get install python3 python3-venv
   cd /home/pizero/recetario
   ./despliegue_raspberry.sh install
   mkdir -p /home/pizero/.config/recetario
   chmod 700 /home/pizero/.config/recetario
   cp deploy/recetario.env.example /home/pizero/.config/recetario/recetario.env
   chmod 600 /home/pizero/.config/recetario/recetario.env
   ```

   Edita ese archivo con `nano /home/pizero/.config/recetario/recetario.env`.
   Para una instalación nueva, esta es la configuración del ejemplo:

   ```ini
   DB_PATH=/home/pizero/.local/share/recetario/recetario.db
   BACKUP_DIR=/home/pizero/.local/share/recetario-backups
   BACKUP_RETAIN=2
   PORT=80
   ```

   Si ya tienes datos, `DB_PATH` debe apuntar a la base verificada de esa instalación.
   Las opciones se respetan desde el entorno. Para un arranque manual puedes usar
   `RECETARIO_ENV=/home/pizero/.config/recetario/recetario.env ./despliegue_raspberry.sh start`.
   El archivo se interpreta como shell: úsalo solo si es tuyo y de confianza.
   En systemd se usa `EnvironmentFile`; usa asignaciones simples con rutas absolutas.

3. Carga la configuración desde el directorio de Recetario, con el servicio detenido.

   ```sh
   set -a
   . /home/pizero/.config/recetario/recetario.env
   set +a
   ```

   **Instalación nueva sin datos anteriores.** `manage.py info` solo inspecciona
   archivos existentes y muestra «Base ausente» hasta que crees la base. Ejecuta
   estos comandos como usuario normal. `init` crea la carpeta y una base con el
   esquema actual, lista para añadir recetas.

   ```sh
   .venv/bin/python backend/manage.py init
   .venv/bin/python backend/manage.py info
   ```

   **Instalación existente.** Comprueba la base configurada antes de migrar.

   ```sh
   .venv/bin/python backend/manage.py info &&
       .venv/bin/python backend/manage.py migrate &&
       .venv/bin/python backend/manage.py info
   ```

   Si `info` muestra «Base ausente» y ya tenías recetas en esta Raspberry, busca
   la base anterior con `find "$HOME" -type f -name recetario.db -print` y revisa
   el `DB_PATH` de la instalación anterior. Puedes comprobar un archivo encontrado
   con `.venv/bin/python backend/manage.py --db /ruta/absoluta/recetario.db info`.
   Cuando identifiques la base, sigue el procedimiento de actualización segura de
   este documento. Reserva `init` para instalaciones nuevas.

4. Instala el [servicio de arranque automático](#arranque-automático-tras-un-corte-de-luz).

5. Abre `http://IP_DE_LA_RASPBERRY/` desde el móvil o el ordenador en la misma red.
   El servidor escucha en `0.0.0.0`; permite el puerto 80 en tu cortafuegos local
   si lo usas. Las dependencias solo se instalan con `./despliegue_raspberry.sh install`:
   los siguientes arranques no ejecutan pip. Si cambia requirements, vuelve a instalar.

### Arranque automático tras un corte de luz

Cuando vuelva la corriente y arranque la Raspberry, systemd iniciará la versión
instalada de Recetario con la base indicada en `recetario.env`. La unidad también
vuelve a iniciar Waitress tras 10 segundos si el proceso falla.

1. Después de preparar las dependencias y comprobar la base en los pasos
   anteriores, instala la unidad desde el directorio de Recetario. Si ya tienes
   una unidad instalada, conserva esa copia y revisa su configuración en el paso 2.

   ```sh
   sudo install -m 0644 deploy/recetario.service /etc/systemd/system/recetario.service
   ```

2. Abre la unidad con `sudoedit /etc/systemd/system/recetario.service` y adapta
   estos valores a tu instalación. Por ejemplo, si extrajiste el código en
   `/home/pizero/recetario-nuevo`, usa esa carpeta en `WorkingDirectory` y `ExecStart`.

   ```ini
   User=pizero
   WorkingDirectory=/home/pizero/recetario
   EnvironmentFile=/home/pizero/.config/recetario/recetario.env
   ExecStart=/home/pizero/recetario/despliegue_raspberry.sh start
   ```

   Usa el usuario normal que instaló las dependencias y tiene acceso de escritura
   a la base y su carpeta. Conserva `AmbientCapabilities=CAP_NET_BIND_SERVICE` y
   `CapabilityBoundingSet=CAP_NET_BIND_SERVICE` de la plantilla para escuchar en el
   puerto 80. Si otro servicio ocupa ese puerto, resuelve el conflicto antes de
   iniciar Recetario.

3. Habilita el arranque automático e inicia el servicio ahora.

   ```sh
   sudo systemctl daemon-reload
   sudo systemctl enable --now recetario.service
   systemctl is-enabled recetario.service
   systemctl is-active recetario.service
   ```

   Espera `enabled` y `active`. Si ya estaba activo al editar la unidad, aplica
   los cambios con `sudo systemctl restart recetario.service`.

4. Para comprobarlo ahora, reinicia la Raspberry con `sudo reboot`. Cuando vuelva
   a estar disponible, abre `http://IP_DE_LA_RASPBERRY/` desde tu red y comprueba
   el registro de ese arranque.

   ```sh
   sudo journalctl -b -u recetario.service -n 40 --no-pager
   ```

   Si configuraste el [HTTPS local](#https-en-raspberry-pi-zero-w) con Nginx,
   verifica también `sudo nginx -t` y habilita su servicio con
   `sudo systemctl enable --now nginx` para recuperar el acceso por HTTPS.

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
2. Ejecuta manualmente `/home/pizero/recetario/deploy/backup-weekly.sh` y comprueba la
   ruta de la copia generada. Funciona desde cualquier directorio y carga el mismo
   archivo de configuración que la aplicación. Puedes cambiarlo con `RECETARIO_ENV`.
3. Comprueba que cron está instalado y activo (`systemctl status cron`). En Raspberry
   Pi OS, si falta: `sudo apt-get install cron` y `sudo systemctl enable --now cron`.
4. Como propietario de Recetario, abre `crontab -e` y añade esta línea, sustituyendo
   usuario y rutas (también disponible en `deploy/recetario.crontab.example`):

```cron
0 3 * * 0 /home/pizero/recetario/deploy/backup-weekly.sh >> /home/pizero/.local/share/recetario-backup.log 2>&1
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
     --target /home/pizero/.local/share/recetario/recetario.db \
     --backup-dir /home/pizero/.local/share/recetario-backups \
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
   cd /home/pizero/recetario
   set -a
   . /home/pizero/.config/recetario/recetario.env
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

Nginx sirve HTTPS en el puerto **443** de la IP local. Recetario sigue en el
puerto **80** con la misma base SQLite. Mantén ambos puertos en la red local,
sin redirecciones desde Internet.

Los comandos se ejecutan como usuario `pizero` en la Raspberry y usan
`/home/pizero/recetario` como carpeta del proyecto. Comprueba la IP con
`hostname -I` y reserva esa dirección en el router. Cambia el valor de
`RECETARIO_IP` si tu Pi usa otra dirección. Usa esa misma IP en la URL del móvil.

#### 1. Generar la CA y el certificado del servidor

En la **primera configuración**, crea una carpeta privada nueva fuera del
repositorio. Esto permite repetir un intento fallido sin sobrescribir archivos.

```sh
RECETARIO_IP=192.168.1.25
mkdir -p -m 0700 "$HOME/recetario-tls" &&
    cd "$(mktemp -d "$HOME/recetario-tls/emitir.XXXXXX")" &&
    umask 077 &&
    openssl genrsa -aes256 -out ca.key 2048
```

Cuando OpenSSL muestre `Enter PEM pass phrase`, escribe una frase de contraseña
larga y repítela para confirmar. La terminal no muestra los caracteres. Si
aparece `result too small` o `Could not find private key from ca.key`, vuelve a
ejecutar el bloque anterior y espera a que termine antes de continuar.

Desde esa misma carpeta y terminal, ejecuta el siguiente bloque. OpenSSL te
pedirá la misma frase para crear el certificado de la CA y para firmar el del
servidor. La IP del certificado se incluye en el SAN.

```sh
(
    set -eu
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
    openssl verify -CAfile ca.crt -purpose sslserver -verify_ip "$RECETARIO_IP" server.crt
    openssl x509 -in ca.crt -outform DER -out recetario-ca.cer
)
```

La verificación debe mostrar `server.crt: OK`. Guarda `ca.key` cifrada y su
frase en un lugar seguro, preferiblemente fuera de la Pi. Para renovar el
certificado de servidor antes de sus 365 días, usa esa misma CA para firmarlo,
instala el certificado nuevo y recarga Nginx. Los teléfonos conservarán la
confianza en esa CA.

#### 2. Instalar y configurar Nginx

Si aún no tienes Nginx, detén brevemente Recetario durante la instalación. El
sitio de ejemplo de Nginx puede usar el puerto 80 hasta que lo deshabilites.

```sh
sudo apt update &&
    sudo systemctl stop recetario.service &&
    sudo apt install nginx
```

Desde la carpeta de los certificados, instala los archivos y adapta la
[plantilla de Recetario](deploy/recetario.nginx.example) a tu IP. Si abriste otra
terminal, vuelve a la carpeta privada y define de nuevo `RECETARIO_IP`.

```sh
sudo install -d -m 0755 /etc/nginx/recetario
sudo install -m 0644 server.crt /etc/nginx/recetario/server.crt
sudo install -m 0600 server.key /etc/nginx/recetario/server.key

sed "s/192\.168\.1\.50/${RECETARIO_IP:?Define la IP de la Raspberry}/g" \
    /home/pizero/recetario/deploy/recetario.nginx.example > recetario.nginx &&
    sudo install -m 0644 recetario.nginx /etc/nginx/sites-available/recetario
```

Si el sitio Recetario aún no está habilitado, crea el enlace.

```sh
sudo ln -s /etc/nginx/sites-available/recetario /etc/nginx/sites-enabled/recetario
```

Si `/etc/nginx/sites-enabled/default` es el enlace al sitio de ejemplo de
Nginx, desactívalo con `sudo unlink /etc/nginx/sites-enabled/default` para
liberar el puerto 80. Valida la configuración y deja Nginx habilitado para
arrancar tras un corte de luz.

```sh
sudo nginx -t &&
    sudo systemctl enable --now nginx &&
    sudo systemctl reload nginx &&
    sudo systemctl start recetario.service
```

Comprueba que HTTPS devuelve el JSON de Recetario con la CA que acabas de crear.

```sh
curl -fsS --cacert ca.crt "https://${RECETARIO_IP}/manifest.webmanifest"
```

Si obtienes `502`, comprueba `systemctl status recetario.service --no-pager`.
Si Nginx falla al arrancar, revisa `sudo nginx -t` y
`sudo journalctl -u nginx -n 30 --no-pager`.
[Documentación de HTTPS en Nginx](https://nginx.org/en/docs/http/configuring_https_servers.html).

#### 3. Confiar en la CA desde el móvil

Transfiere al teléfono **solo el certificado público** `recetario-ca.cer` por un
medio de confianza. Ejecuta `realpath recetario-ca.cer` para obtener su ruta si
lo vas a copiar por SCP.

- **Android.** Busca **Instalar un certificado** en Ajustes y elige
  **Certificado de CA**. Selecciona el archivo y abre Chrome.
  [Ayuda de Android](https://support.google.com/pixelphone/answer/2844832?hl=es)
- **iPhone.** Abre el archivo e instala el perfil descargado en Ajustes. En
  **Ajustes → General → Información → Ajustes de confianza de los certificados**,
  activa la confianza completa en **Recetario CA local**.
  [Ayuda de Apple](https://support.apple.com/es-es/102390)

Con el móvil conectado a tu Wi-Fi, abre `https://192.168.1.25/` o la IP que
configuraste. Cuando cargue sin avisos de certificado, instala Recetario desde
esa URL. Abre la aplicación desde el icono y comprueba que carga con conexión
antes de probar el modo sin conexión.

### Consultar sin conexión

Abre Recetario al menos una vez con conexión en la **misma URL HTTPS y en la misma
aplicación o perfil de navegador** que usarás fuera de casa. Descarga una copia
de recetas, menú y compra, incluidos los productos manuales y sus marcas. En
iPhone es recomendable abrir la aplicación desde el icono con conexión antes
de salir, porque puede usar almacenamiento distinto al de Safari.

Al perder contacto con la Raspberry aparece **Sin conexión · Modo de solo
lectura** debajo de la cabecera. Puedes navegar, buscar y leer la última copia.
Si aún no la has descargado, la pantalla indica que faltan datos. Si el navegador
borra los datos del sitio, tendrás que descargar la copia de nuevo.

Al volver a la app o recuperar la red, Recetario comprueba el servidor y descarga
una lectura nueva de SQLite antes de habilitar las operaciones. Mientras la app
está visible, también comprueba periódicamente la respuesta del servidor. Si la
actualización de datos falla, la pantalla conserva la última copia y sigue en
solo lectura. Cuando la descarga termina, **Ya tienes conexión** aparece unos
segundos. Los cambios que hagan otras personas se leen del servidor.

Cache API conserva los recursos de la interfaz. IndexedDB guarda una sola copia
de consulta, generada únicamente con respuestas correctas del servidor. Recetario
comprueba la conexión antes de enviar una modificación y jamás aplaza ni reintenta
escrituras. SQLite es la única fuente de datos modificables.
