"""Smart School Bell – Management System (Flask + SQLite)."""
import os
import re
import secrets
import sqlite3
from datetime import date, datetime, timedelta, timezone, time as dtime
from functools import wraps

from flask import (Flask, g, jsonify, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import database as dbm
from i18n import I18N

try:
    from zoneinfo import ZoneInfo
    TZ_NAME = os.environ.get('SSB_TZ', 'Asia/Jakarta')
    TZ = ZoneInfo(TZ_NAME)
except Exception:  # tzdata tidak terpasang (Windows) -> WIB tetap
    TZ_NAME = 'Asia/Jakarta'
    TZ = timezone(timedelta(hours=7))

DAYS = ['sen', 'sel', 'rab', 'kam', 'jum', 'sab', 'min']
SCHOOL_DAYS = DAYS[:5]
BELL_TYPES = ('masuk', 'regular', 'istirahat', 'pulang', 'khusus')
VOLUME_TYPES = ('masuk', 'istirahat', 'pulang', 'khusus')
DEFAULT_SOUND = {'masuk': 'bel/bel_masuk.wav', 'regular': 'bel/bel_masuk.wav',
                 'istirahat': 'bel/bel_istirahat.wav', 'pulang': 'bel/bel_pulang.wav',
                 'khusus': 'bel/bel_masuk.wav'}
STEP3_DELAY = 2      # menit setelah waktu bel
STEP4_DELAY = 3      # menit setelah waktu bel (diserahkan ke petugas lain)
GRACE_MIN = 30       # event dianggap terlewat setelah 30 menit
TIME_RE = re.compile(r'^([01]\d|2[0-3]):[0-5]\d$')
SOUNDS_DIR = os.path.join(dbm.BASE, 'static', 'sounds')

app = Flask(__name__)
os.makedirs(dbm.DATA_DIR, exist_ok=True)
_key_file = os.path.join(dbm.DATA_DIR, 'secret.key')
if not os.path.exists(_key_file):
    with open(_key_file, 'w') as f:
        f.write(secrets.token_hex(32))
with open(_key_file) as f:
    app.secret_key = f.read().strip()
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                  PERMANENT_SESSION_LIFETIME=timedelta(days=30),
                  MAX_CONTENT_LENGTH=5 * 1024 * 1024)
dbm.init_db()


# ------------------------------------------------------------------ helpers
def db():
    if 'db' not in g:
        g.db = dbm.connect()
    return g.db


@app.teardown_appcontext
def close_db(_):
    conn = g.pop('db', None)
    if conn is not None:
        conn.close()


def get_setting(key, default='0'):
    row = db().execute('SELECT value FROM app_settings WHERE key=?', (key,)).fetchone()
    return row['value'] if row else default


def set_setting(key, value):
    db().execute('INSERT INTO app_settings(key,value) VALUES(?,?) '
                 'ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, str(value)))
    db().commit()


def current_user():
    if 'user' not in g:
        uid = session.get('uid')
        g.user = db().execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone() if uid else None
    return g.user


def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not current_user():
            if request.path.startswith('/api/'):
                return jsonify(error='unauthorized'), 401
            return redirect(url_for('login'))
        return fn(*a, **kw)
    return wrapper


def now_local():
    return datetime.now(TZ)


def epoch_ms(d, hhmm):
    h, m = map(int, hhmm.split(':'))
    return int(datetime.combine(d, dtime(h, m), tzinfo=TZ).timestamp() * 1000)


def fmt_dot(hhmm):
    return hhmm.replace(':', '.')


def list_sounds():
    out = []
    for root, _, files in os.walk(SOUNDS_DIR):
        for f in sorted(files):
            if f.lower().endswith(('.mp3', '.wav', '.ogg')) and f != 'notif.wav':
                out.append(os.path.relpath(os.path.join(root, f), SOUNDS_DIR).replace(os.sep, '/'))
    return sorted(out)


def sound_exists(rel):
    return os.path.isfile(os.path.join(SOUNDS_DIR, rel))


def safe_sound(rel):
    rel = (rel or '').strip().replace('\\', '/')
    if not rel or '..' in rel or rel.startswith('/'):
        return None
    return rel


def fmt_range(s, e, lang):
    ds, de = date.fromisoformat(s), date.fromisoformat(e)
    mo = I18N[lang]['months']
    if ds == de:
        return f'{ds.day} {mo[ds.month - 1]} {ds.year}'
    if ds.year == de.year and ds.month == de.month:
        return f'{ds.day} - {de.day} {mo[de.month - 1]} {de.year}'
    if ds.year == de.year:
        return f'{ds.day} {mo[ds.month - 1]} - {de.day} {mo[de.month - 1]} {de.year}'
    return f'{ds.day} {mo[ds.month - 1]} {ds.year} - {de.day} {mo[de.month - 1]} {de.year}'


# ------------------------------------------------------------------ events
def events_for_date(d):
    """Semua bel pada tanggal d, berurutan menurut waktu."""
    conn = db()
    wd = d.weekday()
    evs = []
    ds = d.isoformat()
    sched_specials = set()
    if wd < 5:
        ss = conn.execute('SELECT * FROM special_schedules WHERE start_date<=? AND end_date>=? '
                          'ORDER BY id LIMIT 1', (ds, ds)).fetchone()
        if ss:
            evs.append(dict(time=ss['start_time'], type='masuk', label=ss['name'], ref=f"ss{ss['id']}",
                            sound=DEFAULT_SOUND['masuk'], remind=5))
            evs.append(dict(time=ss['end_time'], type='pulang', label=ss['name'], ref=f"ss{ss['id']}e",
                            sound=DEFAULT_SOUND['pulang'], remind=5))
        else:
            for r in conn.execute('SELECT s.*, b.sound_file, b.remind_before FROM schedule s '
                                  'LEFT JOIN special_bells b ON b.id=s.special_id'):
                typ = r['bell_type']
                sound = r['sound_file'] if typ == 'khusus' and r['sound_file'] else DEFAULT_SOUND[typ]
                if typ == 'khusus' and r['special_id']:
                    sched_specials.add((r['special_id'], r['time']))
                evs.append(dict(time=r['time'], type=typ, label=r['activity'], ref=f"s{r['id']}",
                                sound=sound, remind=r['remind_before'] or 5))
    dkey = DAYS[wd]
    for b in conn.execute('SELECT * FROM special_bells WHERE active=1'):
        if dkey in b['days'].split(',') and (b['id'], b['time']) not in sched_specials:
            evs.append(dict(time=b['time'], type='khusus', label=b['name'], ref=f"b{b['id']}",
                            sound=b['sound_file'], remind=b['remind_before']))
    for e in evs:
        e['date'] = ds
        e['key'] = f"{ds}|{e['time']}|{e['ref']}"
        e['epoch'] = epoch_ms(d, e['time'])
    evs.sort(key=lambda e: (e['time'], e['ref']))
    return evs


def upcoming(now, days=8):
    out = []
    for i in range(days):
        out += events_for_date(now.date() + timedelta(days=i))
    return out


def rung_keys(day_iso):
    rows = db().execute("SELECT event_key FROM bell_log WHERE event_key LIKE ?", (day_iso + '|%',))
    return {r['event_key'] for r in rows}


def relevant_event(now_ms, evs, rung):
    for e in evs:
        if e['key'] in rung:
            continue
        if now_ms <= e['epoch'] + GRACE_MIN * 60000:
            return e
    return None


def build_reminders(now_ms, ev, rung):
    if not ev:
        return None
    t = ev['epoch']
    steps = [
        dict(step=1, epoch=t - ev['remind'] * 60000, n=ev['remind']),
        dict(step=2, epoch=t),
        dict(step=3, epoch=t + STEP3_DELAY * 60000),
        dict(step=4, epoch=t + STEP4_DELAY * 60000),
    ]
    for s in steps:
        dt = datetime.fromtimestamp(s['epoch'] / 1000, TZ)
        s['time'] = dt.strftime('%H:%M')
        s['status'] = 'terkirim' if now_ms >= s['epoch'] and ev['key'] not in rung else 'menunggu'
        if s['status'] == 'terkirim' and ev['date'] == now_local().date().isoformat():
            db().execute('INSERT OR IGNORE INTO reminder_log(event_key,step,status) VALUES(?,?,?)',
                         (ev['key'], s['step'], 'terkirim'))
    db().commit()
    return dict(event=ev, steps=steps)


def public_event(e):
    return {k: e[k] for k in ('key', 'date', 'time', 'type', 'label', 'sound', 'epoch', 'remind')}


def make_state():
    now = now_local()
    now_ms = int(now.timestamp() * 1000)
    today = now.date()
    evs = upcoming(now)
    today_evs = [e for e in evs if e['date'] == today.isoformat()]
    rung = rung_keys(today.isoformat())
    nxt = next((e for e in evs if e['epoch'] > now_ms), None)
    nxt_info = None
    if nxt:
        diff = (date.fromisoformat(nxt['date']) - today).days
        nxt_info = dict(public_event(nxt), days_ahead=diff,
                        weekday=date.fromisoformat(nxt['date']).weekday())
    rem = build_reminders(now_ms, relevant_event(now_ms, evs, rung), rung)
    vols = {r['bell_type']: r['volume'] for r in db().execute('SELECT * FROM sound_settings')}
    user = current_user()
    return dict(
        server_ms=now_ms, tz=TZ_NAME,
        settings=dict(bell_active=get_setting('bell_active', '1') == '1',
                      notif_sound=get_setting('notif_sound', '1') == '1'),
        volumes=vols, today_events=[public_event(e) for e in today_evs], rung=sorted(rung),
        next=nxt_info,
        reminders=None if not rem else dict(event=public_event(rem['event']), steps=rem['steps']),
        user=dict(id=user['id'], role=user['role']),
    )


# ------------------------------------------------------------------ security
@app.before_request
def csrf_protect():
    if request.method in ('POST', 'PUT', 'DELETE'):
        token = request.headers.get('X-CSRF-Token') or request.form.get('csrf')
        if not token or token != session.get('csrf'):
            if request.path.startswith('/api/'):
                return jsonify(error='csrf'), 400
            return redirect(url_for('login'))


@app.after_request
def no_cache_api(resp):
    if request.path.startswith('/api/'):
        resp.headers['Cache-Control'] = 'no-store'
    return resp


@app.context_processor
def inject():
    session.setdefault('csrf', secrets.token_hex(16))
    user = current_user()
    lang = user['language'] if user else session.get('lang', 'id')
    T = I18N.get(lang, I18N['id'])
    return dict(t=lambda k, **kw: T[k].format(**kw) if kw else T[k], T=T, lang=lang,
                theme='dark' if (user and user['dark_mode']) else 'light', user=user,
                csrf=session['csrf'], bell_active=get_setting('bell_active', '1') == '1',
                tz_name=TZ_NAME, fmt_dot=fmt_dot)


# ------------------------------------------------------------------ pages
@app.route('/')
def splash():
    target = url_for('beranda') if current_user() else url_for('login')
    return render_template('splash.html', target=target)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        if current_user():
            return redirect(url_for('beranda'))
        return render_template('login.html', error=None)
    username = (request.form.get('username') or '').strip()
    password = request.form.get('password') or ''
    T = I18N['id']
    if not username or not password:
        return render_template('login.html', error=T['isi_semua']), 400
    row = db().execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
    if not row or not check_password_hash(row['password_hash'], password):
        return render_template('login.html', error=T['login_gagal']), 401
    csrf = secrets.token_hex(16)
    session.clear()
    session['uid'] = row['id']
    session['csrf'] = csrf
    session.permanent = bool(request.form.get('remember'))
    return redirect(url_for('beranda'))


@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify(ok=True, redirect=url_for('login'))


@app.route('/beranda')
@login_required
def beranda():
    conn = db()
    rows = conn.execute('SELECT s.*, b.name AS special_name FROM schedule s '
                        'LEFT JOIN special_bells b ON b.id=s.special_id ORDER BY s.time, s.id').fetchall()
    specials = conn.execute('SELECT id, name FROM special_bells ORDER BY id').fetchall()
    return render_template('beranda.html', rows=rows, specials=specials, page='beranda')


@app.route('/pengaturan')
@login_required
def pengaturan():
    return render_template('pengaturan.html', page='pengaturan')


@app.route('/bunyikan-bel')
@login_required
def bunyikan_bel():
    vols = {r['bell_type']: r['volume'] for r in db().execute('SELECT * FROM sound_settings')}
    return render_template('bunyikan_bel.html', page='beranda', vols=vols,
                           notif_sound=get_setting('notif_sound', '1') == '1')


def special_view(r):
    d = dict(r)
    d['days_list'] = r['days'].split(',')
    d['file_ok'] = sound_exists(r['sound_file'])
    return d


@app.route('/bel-khusus')
@login_required
def bel_khusus():
    items = [special_view(r) for r in db().execute('SELECT * FROM special_bells ORDER BY id')]
    return render_template('bel_khusus.html', items=items, page='beranda')


@app.route('/bel-khusus/baru')
@login_required
def bel_khusus_baru():
    item = dict(id=None, name='', time='07:00', days_list=list(SCHOOL_DAYS), sound_file='bel/bel_masuk.wav',
                remind_before=5, active=1, icon='bell', file_ok=True)
    sounds = list_sounds()
    return render_template('bel_khusus_detail.html', item=item, sounds=sounds, missing=[], page='beranda')


@app.route('/bel-khusus/<int:sid>')
@login_required
def bel_khusus_detail(sid):
    r = db().execute('SELECT * FROM special_bells WHERE id=?', (sid,)).fetchone()
    if not r:
        return redirect(url_for('bel_khusus'))
    sounds = list_sounds()
    if r['sound_file'] not in sounds:
        sounds.append(r['sound_file'])
    missing = [x for x in sounds if not sound_exists(x)]
    return render_template('bel_khusus_detail.html', item=special_view(r), sounds=sounds, missing=missing, page='beranda')


@app.route('/jadwal-khusus')
@login_required
def jadwal_khusus():
    lang = current_user()['language']
    rows = []
    for r in db().execute('SELECT * FROM special_schedules ORDER BY start_date DESC, id DESC'):
        d = dict(r)
        d['range'] = fmt_range(r['start_date'], r['end_date'], lang)
        rows.append(d)
    return render_template('jadwal_khusus.html', rows=rows, page='beranda')


@app.route('/status-pengingat')
@login_required
def status_pengingat():
    return render_template('status_pengingat.html', page='beranda', init=make_state())


# ------------------------------------------------------------------ API
def bad(msg='kesalahan', code=400):
    return jsonify(ok=False, error=msg), code


@app.route('/api/state')
@login_required
def api_state():
    return jsonify(make_state())


@app.route('/api/settings', methods=['POST'])
@login_required
def api_settings():
    data = request.get_json(silent=True) or {}
    if 'bell_active' in data:
        set_setting('bell_active', '1' if data['bell_active'] else '0')
    return jsonify(ok=True)


@app.route('/api/profile', methods=['POST'])
@login_required
def api_profile():
    data = request.get_json(silent=True) or {}
    name = (data.get('full_name') or '').strip()
    pw = data.get('password') or ''
    T = I18N[current_user()['language']]
    if not name or len(name) > 80:
        return bad(T['nama_kosong'])
    conn = db()
    uid = current_user()['id']
    conn.execute('UPDATE users SET full_name=? WHERE id=?', (name, uid))
    if pw:
        if len(pw) < 6:
            return bad(T['pw_pendek'])
        conn.execute('UPDATE users SET password_hash=? WHERE id=?', (generate_password_hash(pw), uid))
    conn.commit()
    return jsonify(ok=True)


@app.route('/api/preferences', methods=['POST'])
@login_required
def api_preferences():
    data = request.get_json(silent=True) or {}
    lang = data.get('language')
    if lang not in I18N:
        return bad()
    db().execute('UPDATE users SET dark_mode=?, language=? WHERE id=?',
                 (1 if data.get('dark_mode') else 0, lang, current_user()['id']))
    db().commit()
    return jsonify(ok=True)


@app.route('/api/sound-settings', methods=['POST'])
@login_required
def api_sound_settings():
    data = request.get_json(silent=True) or {}
    typ, vol = data.get('bell_type'), data.get('volume')
    if typ not in VOLUME_TYPES or not isinstance(vol, int) or not 0 <= vol <= 100:
        return bad()
    db().execute('UPDATE sound_settings SET volume=? WHERE bell_type=?', (vol, typ))
    db().commit()
    set_setting('notif_sound', '1' if data.get('notif_sound') else '0')
    return jsonify(ok=True)


@app.route('/api/ring', methods=['POST'])
@login_required
def api_ring():
    data = request.get_json(silent=True) or {}
    typ = data.get('bell_type')
    src = data.get('source')
    if typ not in BELL_TYPES or src not in ('otomatis', 'manual'):
        return bad()
    conn = db()
    now = now_local()
    now_ms = int(now.timestamp() * 1000)
    key = data.get('event_key') if src == 'otomatis' else None
    name = (data.get('name') or '')[:100]
    if src == 'manual':
        evs = upcoming(now, 2)
        rung = rung_keys(now.date().isoformat())
        ev = relevant_event(now_ms, evs, rung)
        if ev and ev['epoch'] - ev['remind'] * 60000 <= now_ms:
            key = ev['key']
            name = name or ev['label']
    if key:
        if conn.execute('SELECT 1 FROM bell_log WHERE event_key=?', (key,)).fetchone():
            return jsonify(ok=True, duplicate=True)
    try:
        conn.execute('INSERT INTO bell_log(event_key,bell_type,name,source,user_id) VALUES(?,?,?,?,?)',
                     (key, typ, name, src, current_user()['id']))
        conn.commit()
    except sqlite3.IntegrityError:
        return jsonify(ok=True, duplicate=True)
    return jsonify(ok=True, duplicate=False)


def validate_schedule(data):
    t = (data.get('time') or '').strip()
    act = (data.get('activity') or '').strip()
    typ = data.get('bell_type')
    sid = data.get('special_id')
    if not TIME_RE.match(t) or not act or len(act) > 100 or typ not in BELL_TYPES:
        return None
    if typ == 'khusus':
        row = db().execute('SELECT 1 FROM special_bells WHERE id=?', (sid,)).fetchone() if sid else None
        if not row:
            return None
    else:
        sid = None
    return t, act, typ, sid


@app.route('/api/schedule', methods=['POST'])
@login_required
def api_schedule_create():
    v = validate_schedule(request.get_json(silent=True) or {})
    if not v:
        return bad()
    db().execute('INSERT INTO schedule(time,activity,bell_type,special_id) VALUES(?,?,?,?)', v)
    db().commit()
    return jsonify(ok=True)


@app.route('/api/schedule/<int:sid>', methods=['PUT', 'DELETE'])
@login_required
def api_schedule_item(sid):
    conn = db()
    if request.method == 'DELETE':
        conn.execute('DELETE FROM schedule WHERE id=?', (sid,))
    else:
        v = validate_schedule(request.get_json(silent=True) or {})
        if not v:
            return bad()
        conn.execute('UPDATE schedule SET time=?, activity=?, bell_type=?, special_id=? WHERE id=?', v + (sid,))
    conn.commit()
    return jsonify(ok=True)


LINE_RE = re.compile(r'^\s*(\d{1,2})[.:](\d{2})\s+(.+?)(?:\s+(bel masuk|bel istirahat|bel pulang|regular))?\s*$', re.I)
TYPE_MAP = {'bel masuk': 'masuk', 'bel istirahat': 'istirahat', 'bel pulang': 'pulang', 'regular': 'regular'}


@app.route('/api/schedule/upload', methods=['POST'])
@login_required
def api_schedule_upload():
    f = request.files.get('file')
    if not f or not f.filename.lower().endswith('.pdf'):
        return bad()
    try:
        from pypdf import PdfReader
        text = '\n'.join((p.extract_text() or '') for p in PdfReader(f.stream).pages)
    except Exception:
        return bad()
    conn = db()
    existing = {(r['time'], r['activity'].lower()) for r in conn.execute('SELECT time, activity FROM schedule')}
    added = 0
    for line in text.splitlines():
        m = LINE_RE.match(line)
        if not m:
            continue
        h, mi, act, typ = int(m.group(1)), m.group(2), m.group(3).strip(), (m.group(4) or 'regular').lower()
        if h > 23 or int(mi) > 59 or not act:
            continue
        t = f'{h:02d}:{mi}'
        if (t, act.lower()) in existing:
            continue
        conn.execute('INSERT INTO schedule(time,activity,bell_type) VALUES(?,?,?)', (t, act[:100], TYPE_MAP[typ]))
        existing.add((t, act.lower()))
        added += 1
    conn.commit()
    return jsonify(ok=True, added=added)


def validate_special_bell(data):
    name = (data.get('name') or '').strip()
    t = (data.get('time') or '').strip()
    days = [d for d in SCHOOL_DAYS if d in (data.get('days') or [])]
    sound = safe_sound(data.get('sound_file'))
    remind = data.get('remind_before')
    if not name or len(name) > 100 or not TIME_RE.match(t) or not sound or remind not in (5, 10, 15):
        return None
    return name, t, ','.join(days), sound, remind, 1 if data.get('active') else 0


@app.route('/api/special-bells', methods=['POST'])
@login_required
def api_special_create():
    v = validate_special_bell(request.get_json(silent=True) or {})
    if not v:
        return bad()
    db().execute("INSERT INTO special_bells(name,time,days,sound_file,remind_before,active,icon) "
                 "VALUES(?,?,?,?,?,?, 'bell')", v)
    db().commit()
    return jsonify(ok=True)


@app.route('/api/special-bells/<int:bid>', methods=['PUT'])
@login_required
def api_special_update(bid):
    v = validate_special_bell(request.get_json(silent=True) or {})
    if not v:
        return bad()
    db().execute('UPDATE special_bells SET name=?, time=?, days=?, sound_file=?, remind_before=?, active=? '
                 'WHERE id=?', v + (bid,))
    db().commit()
    return jsonify(ok=True)


def validate_special_schedule(data):
    name = (data.get('name') or '').strip()
    st, et = (data.get('start_time') or ''), (data.get('end_time') or '')
    try:
        sd, ed = date.fromisoformat(data.get('start_date')), date.fromisoformat(data.get('end_date'))
    except Exception:
        return None
    if not name or len(name) > 100 or not TIME_RE.match(st) or not TIME_RE.match(et) or ed < sd or et <= st:
        return None
    return name, sd.isoformat(), ed.isoformat(), st, et


@app.route('/api/special-schedules', methods=['POST'])
@login_required
def api_ss_create():
    v = validate_special_schedule(request.get_json(silent=True) or {})
    if not v:
        return bad()
    db().execute('INSERT INTO special_schedules(name,start_date,end_date,start_time,end_time) VALUES(?,?,?,?,?)', v)
    db().commit()
    return jsonify(ok=True)


@app.route('/api/special-schedules/<int:sid>', methods=['PUT', 'DELETE'])
@login_required
def api_ss_item(sid):
    conn = db()
    if request.method == 'DELETE':
        conn.execute('DELETE FROM special_schedules WHERE id=?', (sid,))
    else:
        v = validate_special_schedule(request.get_json(silent=True) or {})
        if not v:
            return bad()
        conn.execute('UPDATE special_schedules SET name=?, start_date=?, end_date=?, start_time=?, end_time=? '
                     'WHERE id=?', v + (sid,))
    conn.commit()
    return jsonify(ok=True)


if __name__ == '__main__':
    if not dbm.connect().execute('SELECT 1 FROM users LIMIT 1').fetchone():
        print('\n[!] Belum ada akun. Jalankan dulu:  python manage.py create-user\n')
    app.run(host='127.0.0.1', port=5000, debug=False)
