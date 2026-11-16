"""Perintah pengelolaan akun.  Contoh:
    python manage.py create-user
    python manage.py reset-password
"""
import getpass
import sys

from werkzeug.security import generate_password_hash

import database as dbm


def create_user():
    dbm.init_db()
    conn = dbm.connect()
    username = input('Username: ').strip()
    full_name = input('Nama lengkap: ').strip()
    has_users = conn.execute('SELECT 1 FROM users LIMIT 1').fetchone()
    default_role = 'petugas' if has_users else 'utama'
    role = input(f'Peran (utama/petugas) [{default_role}]: ').strip() or default_role
    pw = getpass.getpass('Password (min. 6 karakter): ')
    if not username or not full_name or len(pw) < 6 or role not in ('utama', 'petugas'):
        sys.exit('Data tidak valid.')
    try:
        conn.execute('INSERT INTO users(username,password_hash,full_name,role) VALUES(?,?,?,?)',
                     (username, generate_password_hash(pw), full_name, role))
        conn.commit()
    except Exception as e:
        sys.exit(f'Gagal: {e}')
    print(f'Akun "{username}" ({role}) dibuat.')


def reset_password():
    conn = dbm.connect()
    username = input('Username: ').strip()
    pw = getpass.getpass('Password baru (min. 6 karakter): ')
    if len(pw) < 6:
        sys.exit('Password terlalu pendek.')
    cur = conn.execute('UPDATE users SET password_hash=? WHERE username=?', (generate_password_hash(pw), username))
    conn.commit()
    print('Password diperbarui.' if cur.rowcount else 'Username tidak ditemukan.')


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    {'create-user': create_user, 'reset-password': reset_password}.get(cmd, lambda: print(__doc__))()
