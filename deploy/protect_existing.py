#!/usr/bin/env python3
"""Primer despliegue: copiar este archivo suelto a la Pi ANTES de git pull.
Solo biblioteca estándar. Aplicación detenida; nunca borra ni sobrescribe bases.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import uuid


def check(path):
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as conn:
        if conn.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise RuntimeError(f'Integridad incorrecta: {path}')
        if conn.execute('PRAGMA foreign_key_check').fetchone():
            raise RuntimeError(f'Relaciones incorrectas: {path}')
        return {table: conn.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
                for table in ('recipes', 'ingredients', 'menu')}


def publish(partial, target):
    with partial.open('rb') as stream:
        os.fsync(stream.fileno())
    os.link(partial, target)  # publicación exclusiva: falla si ya existe
    partial.unlink()
    fd = os.open(target.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def protect(source, target, directory):
    for path in (source, target, directory):
        if not path.is_absolute():
            raise ValueError('Las tres rutas deben ser absolutas.')
    if not source.is_file() or target.exists():
        raise ValueError('La fuente debe existir y el destino debe ser NUEVO. No se sobrescribe nada.')
    for destination in (target, directory):
        if any((parent / '.git').is_file() or (parent / '.git/HEAD').is_file()
               for parent in destination.resolve().parents):
            raise ValueError('El destino y las copias deben estar fuera del repositorio.')
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    saved = directory / f'pre-update-{stamp}-{uuid.uuid4().hex[:8]}.sqlite3'
    with tempfile.NamedTemporaryFile(dir=directory, suffix='.partial', delete=False) as stream:
        partial = Path(stream.name)
    try:
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=10)) as src, closing(sqlite3.connect(partial)) as dst:
            src.backup(dst)
            dst.execute('PRAGMA journal_mode=DELETE')
        counts = check(partial)
        publish(partial, saved)
    finally:
        try:
            partial.unlink()
        except FileNotFoundError:
            pass
    with tempfile.NamedTemporaryFile(dir=target.parent, suffix='.partial', delete=False) as stream:
        partial = Path(stream.name)
    try:
        shutil.copyfile(saved, partial)  # snapshot cerrado, verificado y sin WAL
        if check(partial) != counts:
            raise RuntimeError('Los recuentos no coinciden; no se publica el destino.')
        publish(partial, target)
    finally:
        try:
            partial.unlink()
        except FileNotFoundError:
            pass
    print('Original conservado:', source)
    print('Respaldo verificado:', saved)
    print('Base externa verificada:', target)
    print('Recuentos:', counts)
    print('Configura DB_PATH con la base externa antes de arrancar. No borres el original.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--target', required=True, type=Path)
    parser.add_argument('--backup-dir', required=True, type=Path)
    parser.add_argument('--writers-stopped', required=True, action='store_true')
    args = parser.parse_args()
    try:
        protect(args.source, args.target, args.backup_dir)
    except (OSError, sqlite3.Error, ValueError, RuntimeError) as exc:
        parser.exit(1, f'ERROR: {exc}\nNo actualices ni arranques hasta resolverlo.\n')
