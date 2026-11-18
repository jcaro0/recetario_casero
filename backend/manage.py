"""Administración explícita. Nunca restaura por iniciativa propia."""
import argparse
import json
import os
import sys
from pathlib import Path
import backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default=os.environ.get('DB_PATH'))
    parser.add_argument('--backup-dir', default=os.environ.get('BACKUP_DIR'))
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('info', 'init', 'migrate'):
        sub.add_parser(name)
    b = sub.add_parser('backup')
    b.add_argument('--retain', type=int, default=int(os.environ.get('BACKUP_RETAIN', '2')))
    b.add_argument('--label', choices=['manual', 'daily', 'weekly'], default='manual')
    r = sub.add_parser('restore', description='Pierdes las recetas posteriores a la copia. Detén primero la aplicación.')
    r.add_argument('source')
    r.add_argument('--writers-stopped', action='store_true')
    r.add_argument('--confirm-active-path', required=True)
    args = parser.parse_args()
    if not args.db or not Path(args.db).is_absolute():
        parser.error('Indica --db /ruta/absoluta/recetario.db o DB_PATH explícito.')
    import database as db
    db.DB_PATH = args.db
    if args.backup_dir:
        os.environ['BACKUP_DIR'] = args.backup_dir
    if args.command == 'info':
        print(json.dumps(backup.verify(args.db), ensure_ascii=False, indent=2))
    elif args.command == 'init':
        import set_up
        set_up.initialize()
        print(json.dumps(backup.verify(args.db)))
    elif args.command == 'migrate':
        import set_up
        set_up.create_tables()
        print(json.dumps(backup.verify(args.db)))
    else:
        if not args.backup_dir:
            parser.error('Indica BACKUP_DIR fuera del repositorio.')
        if args.command == 'backup':
            print(backup.backup(args.db, args.backup_dir, label=args.label, retain=args.retain))
        else:
            print('Estado anterior conservado en:', backup.restore(args.source, args.db, args.backup_dir,
                  stopped=args.writers_stopped, confirm=args.confirm_active_path))

if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, __import__('sqlite3').Error) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        sys.exit(1)
