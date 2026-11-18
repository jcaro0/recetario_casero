"""Copias SQLite independientes del esquema y sin dependencias externas."""
import os
import hashlib
import sqlite3
import time
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


def connect_existing(path, readonly=False):
    path = Path(path)
    if not path.is_absolute():
        raise ValueError('DB_PATH debe ser una ruta absoluta.')
    if not path.is_file():
        raise FileNotFoundError(f'Base ausente: {path}. No se creará automáticamente.')
    return sqlite3.connect(path.as_uri() + ('?mode=ro' if readonly else '?mode=rw'), uri=True, timeout=10)


def verify(path):
    with closing(connect_existing(path, True)) as conn:
        result = conn.execute('PRAGMA integrity_check').fetchall()
        if result != [('ok',)]:
            raise ValueError(f'Copia/base dañada: {path}: {result}')
        if conn.execute('PRAGMA foreign_key_check').fetchone():
            raise ValueError(f'Relaciones inconsistentes en {path}')
        return {'path': str(Path(path).resolve()),
                'version': conn.execute('PRAGMA user_version').fetchone()[0],
                'recipes': conn.execute('SELECT count(*) FROM recipes').fetchone()[0]}


def backup(source, directory, label='manual', retain=None):
    directory = Path(directory)
    if not directory.is_absolute():
        raise ValueError('BACKUP_DIR debe ser absoluto y estar fuera del repositorio.')
    code_dir = Path(__file__).resolve().parent
    protected = code_dir.parent if (code_dir.parent / 'script.sh').is_file() else code_dir
    if directory.resolve().is_relative_to(protected):
        raise ValueError('BACKUP_DIR debe estar fuera del directorio del código, no dentro del repositorio.')
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    source_id = hashlib.sha256(str(Path(source).resolve()).encode()).hexdigest()[:12]
    prefix = f'recetario-{label}-{source_id}-'
    target = directory / f'{prefix}{stamp}-{uuid.uuid4().hex[:8]}.sqlite3'
    partial = target.with_suffix('.partial')
    started = time.monotonic()
    def progress(status, remaining, total):
        if time.monotonic() - started > 120:
            raise TimeoutError('SQLite ocupado: copia cancelada tras 120 segundos; reintenta.')
    try:
        fd = os.open(partial, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        with closing(connect_existing(source, True)) as src, closing(sqlite3.connect(partial)) as dst:
            src.backup(dst, pages=128, progress=progress, sleep=0.1)
            dst.execute('PRAGMA journal_mode=DELETE')
        verify(partial)
        with partial.open('rb') as stream:
            os.fsync(stream.fileno())
        os.replace(partial, target)
        fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        partial.unlink(missing_ok=True)
    # Solo las copias manuales y programadas participan en retención; las de migración
    # y prerrestauración se conservan hasta revisión manual.
    if retain is not None and label in ('manual', 'daily', 'weekly'):
        keep = max(1, int(retain))
        valid = []
        for candidate in directory.glob(f'{prefix}*.sqlite3'):
            try:
                verify(candidate)
                valid.append(candidate)
            except (sqlite3.Error, ValueError, OSError):
                continue
        for candidate in sorted(valid, reverse=True)[keep:]:
            if candidate != target:
                candidate.unlink()
    return target


def restore(source, active, directory, *, stopped=False, confirm=None):
    active = Path(active)
    if not stopped or confirm != str(active):
        raise ValueError('Detén todos los escritores y confirma la ruta activa exacta. Se perderán cambios posteriores a la copia.')
    if Path(source).resolve() == active.resolve():
        raise ValueError('El respaldo debe ser distinto de la base activa.')
    verify(source)
    # Respalda antes de tocar nada. No reemplaza archivos ni separa un WAL.
    saved = backup(active, directory, label='before-restore')
    with closing(connect_existing(source, True)) as src, closing(connect_existing(active)) as dst:
        src.backup(dst)
    verify(active)
    return saved
