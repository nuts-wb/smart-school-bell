import os
import sqlite3

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, 'data')
DB_PATH = os.path.join(DATA_DIR, 'smartbell.db')

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'petugas',          -- 'utama' | 'petugas'
    dark_mode INTEGER NOT NULL DEFAULT 0,
    language TEXT NOT NULL DEFAULT 'id',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sound_settings (
    bell_type TEXT PRIMARY KEY,                    -- masuk | istirahat | pulang | khusus
    volume INTEGER NOT NULL DEFAULT 80
);
CREATE TABLE IF NOT EXISTS special_bells (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    time TEXT NOT NULL,                            -- HH:MM
    days TEXT NOT NULL DEFAULT 'sen,sel,rab,kam,jum',
    sound_file TEXT NOT NULL DEFAULT 'bel/bel_masuk.wav',
    remind_before INTEGER NOT NULL DEFAULT 5,
    active INTEGER NOT NULL DEFAULT 0,
    icon TEXT NOT NULL DEFAULT 'bell'              -- flag | logo | mosque | bell
);
CREATE TABLE IF NOT EXISTS schedule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    time TEXT NOT NULL,
    activity TEXT NOT NULL,
    bell_type TEXT NOT NULL DEFAULT 'regular',     -- masuk | regular | istirahat | pulang | khusus
    special_id INTEGER REFERENCES special_bells(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS special_schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    start_date TEXT NOT NULL,                      -- YYYY-MM-DD
    end_date TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bell_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_key TEXT,
    bell_type TEXT NOT NULL,
    name TEXT,
    source TEXT NOT NULL,                          -- otomatis | manual
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_bell_log_event ON bell_log(event_key) WHERE event_key IS NOT NULL;
CREATE TABLE IF NOT EXISTS reminder_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_key TEXT NOT NULL,
    step INTEGER NOT NULL,                         -- 1..4
    status TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(event_key, step)
);
"""

# Daftar kegiatan khusus bawaan sesuai desain (bisa diubah di aplikasi).
DEFAULT_SPECIAL = [
    ('Indonesia Raya', 'lagu/indonesia_raya.mp3', 'flag'),
    ('Mars Telkom', 'lagu/mars_telkom.mp3', 'logo'),
    ('Telkom School', 'lagu/telkom_school.mp3', 'logo'),
    ('Sholat Dzuhur Berjamaah', 'bel/bel_masuk.wav', 'mosque'),
    ('Sholat Dhuha Berjamaah', 'bel/bel_masuk.wav', 'mosque'),
]


def connect():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    return conn


def init_db():
    conn = connect()
    conn.executescript(SCHEMA)
    if conn.execute('SELECT COUNT(*) FROM special_bells').fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO special_bells(name,time,sound_file,icon,active) VALUES(?, '10:00', ?, ?, 0)",
            DEFAULT_SPECIAL)
    for t in ('masuk', 'istirahat', 'pulang', 'khusus'):
        conn.execute('INSERT OR IGNORE INTO sound_settings(bell_type, volume) VALUES(?, 80)', (t,))
    conn.execute("INSERT OR IGNORE INTO app_settings(key,value) VALUES('bell_active','1')")
    conn.execute("INSERT OR IGNORE INTO app_settings(key,value) VALUES('notif_sound','1')")
    conn.commit()
    conn.close()
