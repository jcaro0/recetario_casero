# Resumen de cambios de Recetario

Recetario mantiene su diseño y sus funciones, con mejoras para editar recetas,
adaptar las cantidades y actualizar el programa sin mezclar el código con los datos.
Este documento ofrece una visión general; los pasos de uso y despliegue están en
[README.md](README.md).

## Recetas y planificación

Se pueden editar recetas conservando su identificador y sus referencias del menú.
Cada receta incluye raciones originales, pasos de preparación y notas. El menú
permite indicar comensales y la lista de la compra ajusta las cantidades y convierte
unidades compatibles. Se ha mejorado la navegación por teclado del formulario y
su uso desde el móvil, manteniendo el diseño existente.

## Protección de las recetas

La aplicación deja de crear bases vacías automáticamente cuando falta el archivo
esperado. Las instalaciones nuevas se inicializan de forma explícita y las antiguas
se actualizan mediante migraciones con copia previa verificada y rollback ante fallos.
Se comprueba que el esquema sea compatible y se conservan los IDs y las relaciones.
Las rutas de datos no se cambian silenciosamente.

## Copias y recuperación

Hay comandos para consultar la base activa, hacer copias consistentes con SQLite WAL
y restaurar una copia por decisión explícita. Los respaldos se verifican, tienen nombres
únicos y una retención configurable que conserva al menos una copia válida. Antes de
restaurar se respalda el estado actual. La aplicación no restaura copias por sí sola.
Se incluye cron semanal con retención de las dos últimas copias válidas, sin un proceso Python permanente.

## Desarrollo y Raspberry Pi

Docker Compose sigue usando el puerto **8000** y su base persistente del ordenador.
La Raspberry sigue usando el puerto **80**, sin Docker. El script corrige las rutas,
funciona desde otros directorios y separa la instalación de dependencias del arranque.
Se usa Waitress con un proceso y dos hilos. El servicio systemd permite escuchar en
el puerto 80 con un usuario normal y una capacidad de red limitada.

Cada entorno conserva sus propios datos. Un auxiliar permite proteger una instalación
antigua antes de actualizar Git, creando una base y un respaldo externos sin borrar
el original ni sobrescribir destinos existentes.

## Acceso a las modificaciones

La autenticación es opcional y se activa mediante un archivo de configuración externo.
Usa contraseña hasheada, sesiones firmadas y protección CSRF validada por el backend.
Las consultas siguen abiertas y las llamadas JavaScript mantienen su funcionamiento.
Está desactivada hasta que se configuren las credenciales. HTTP no cifra el tráfico:
la protección de acceso no sustituye a HTTPS o una VPN en redes no confiables.

## Comprobaciones

Las pruebas usan exclusivamente bases temporales. Cubren operaciones de recetas,
persistencia, migraciones, IDs y menú, cantidades, copias WAL, restauración, retención,
autenticación y el escenario de conservar 25 recetas al desplegar. También se han
comprobado el recorrido de navegador y el arranque real desde otro directorio.
Los detalles y comandos están en [tests/README.md](tests/README.md).

## Estado y tareas manuales pendientes

- No se han migrado, borrado ni restaurado las bases reales durante este trabajo.
- No se ha accedido a la Raspberry ni comprobado allí el despliegue.
- Hay que configurar rutas externas permanentes de copias, el servicio de la Pi,
  la programación semanal y, si se desea, la autenticación.
- La base se ha retirado del seguimiento de Git tras crear una copia externa verificada.
  El archivo local se conserva; la Raspberry nueva inicializará su propia base.
  Otros clones con datos deben protegerlos antes de recibir la retirada.
- Los cambios se han organizado en commits locales. No se ha hecho push.

Antes del primer despliegue, sigue en orden el **PROCEDIMIENTO SEGURO PARA ACTUALIZAR
MI RASPBERRY PI** del [README.md](README.md). El código se actualiza por separado:
la base del ordenador nunca debe sustituir a la base actual de la Raspberry.
