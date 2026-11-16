/* Smart School Bell – skrip bersama (jam, penjadwal bel, pengingat, notifikasi). */
(function () {
  'use strict';
  var A = window.APP, T = A.T;
  var S = null, offset = 0, hooks = [], pending = null;
  var fired = new Set(JSON.parse(sessionStorage.getItem('ssb_fired') || '[]'));
  var shown = new Set(JSON.parse(localStorage.getItem('ssb_shown') || '[]'));
  var DEFAULT_SOUND = { masuk: 'bel/bel_masuk.wav', regular: 'bel/bel_masuk.wav', istirahat: 'bel/bel_istirahat.wav',
                        pulang: 'bel/bel_pulang.wav', khusus: 'bel/bel_masuk.wav' };

  function $(id) { return document.getElementById(id); }


  async function api(method, url, body) {
    var opt = { method: method, headers: { 'X-CSRF-Token': A.csrf } };
    if (body !== undefined) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
    try {
      var res = await fetch(url, opt);
      var data = await res.json().catch(function () { return {}; });
      if (res.status === 401) { location.href = '/login'; }
      return { ok: res.ok && data.ok !== false, status: res.status, data: data };
    } catch (e) { return { ok: false, status: 0, data: {} }; }
  }

  var flashTimer;
  function flash(msg) {
    var el = $('flash'); if (!el) return;
    el.textContent = msg; el.classList.add('show');
    clearTimeout(flashTimer); flashTimer = setTimeout(function () { el.classList.remove('show'); }, 2600);
  }

  function confirmDlg(title, desc, okLabel) {
    return new Promise(function (resolve) {
      var el = $('confirmModal'), modal = bootstrap.Modal.getOrCreateInstance(el), done = false;
      $('confirmTitle').textContent = title; $('confirmDesc').textContent = desc || '';
      $('confirmOk').textContent = okLabel || T.bunyikan;
      var ok = $('confirmOk');
      function finish(v) { if (done) return; done = true; ok.removeEventListener('click', onOk); el.removeEventListener('hidden.bs.modal', onHide); resolve(v); }
      function onOk() { finish(true); modal.hide(); }
      function onHide() { finish(false); }
      ok.addEventListener('click', onOk); el.addEventListener('hidden.bs.modal', onHide); modal.show();
    });
  }

  async function logout() {
    var r = await api('POST', '/logout');
    location.href = (r.data && r.data.redirect) || '/login';
  }

  /* ---------- waktu server ---------- */
  function serverNow() { return Date.now() + offset; }
  var fmt = new Intl.DateTimeFormat('en-GB', { timeZone: A.tz, hourCycle: 'h23', hour: '2-digit', minute: '2-digit', second: '2-digit',
                                               weekday: 'long', day: 'numeric', month: 'numeric', year: 'numeric' });
  var WD = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
  function parts(ms) {
    var o = {}; fmt.formatToParts(new Date(ms)).forEach(function (p) { o[p.type] = p.value; });
    return o;
  }
  function renderClock() {
    var c = $('clock'); if (!c) return;
    var p = parts(serverNow());
    c.textContent = p.hour + ':' + p.minute + ':' + p.second;
    $('dateLine').textContent = T.days_long[WD.indexOf(p.weekday)] + ', ' + parseInt(p.day, 10) + ' ' + T.months[parseInt(p.month, 10) - 1] + ' ' + p.year;
  }

  /* ---------- suara ---------- */
  function playBell(file, vol) {
    var a = new Audio('/static/sounds/' + file);
    a.volume = Math.max(0, Math.min(1, vol));
    var fallbackUsed = false;
    a.addEventListener('error', function () {
      if (fallbackUsed) return; fallbackUsed = true; flash(T.file_belum_ada + ' – ' + file.split('/').pop());
      var f = new Audio('/static/sounds/' + DEFAULT_SOUND.masuk); f.volume = a.volume; f.play().catch(function () {});
    });
    var p = a.play();
    if (p && p.catch) p.catch(function (e) {
      if (e && e.name === 'NotAllowedError') { pending = { file: file, vol: vol }; flash(T.tap_to_play); }
    });
    return a;
  }
  function volOf(type) { var t = type === 'regular' ? 'masuk' : type; return ((S && S.volumes[t]) != null ? S.volumes[t] : 80) / 100; }

  /* ---------- notifikasi ---------- */
  function notify(o) {
    var box = $('toasts');
    if (S && S.settings.notif_sound) { try { var n = new Audio('/static/sounds/bel/notif.wav'); n.volume = 0.7; n.play().catch(function () {}); } catch (e) {} }
    if (box) {
      var el = document.createElement('div'); el.className = 'ssb-toast';
      el.innerHTML = '<div class="t-main"><div class="t-ico' + (o.warn ? ' warn' : '') + '">' +
        (o.warn ? '<img src="/static/img/peringatan.png" alt="">' : '<i class="bi bi-bell"></i>') + '</div>' +
        '<div class="t-body"><div class="t-top"><span>Smart School Bell</span><em>' + T.sekarang + '</em></div><b></b><span class="t-l2"></span>' +
        (o.line3 ? '<span class="t-l3"></span>' : '') + '</div></div>' + (o.action ? '<a class="t-act" href="' + o.href + '"></a>' : '');
      el.querySelector('b').textContent = o.title; el.querySelector('.t-l2').textContent = o.line2;
      if (o.line3) el.querySelector('.t-l3').textContent = o.line3;
      if (o.action) el.querySelector('.t-act').textContent = o.action;
      box.appendChild(el); setTimeout(function () { el.classList.add('out'); setTimeout(function () { el.remove(); }, 400); }, 15000);
      el.addEventListener('click', function (e) { if (!e.target.closest('.t-act')) el.remove(); });
    }
    if (document.hidden && 'Notification' in window && Notification.permission === 'granted') {
      try { new Notification(o.title, { body: o.line2 + (o.line3 ? '\n' + o.line3 : ''), icon: '/static/img/lonceng.png' }); } catch (e) {}
    }
  }

  function typeName(ev) { return T['type_' + ev.type] || ''; }
  function handleReminders() {
    var R = S && S.reminders; if (!R) return;
    var ev = R.event, now = serverNow(), me = A.user;
    R.steps.forEach(function (st) {
      if (st.status !== 'terkirim' || now - st.epoch > 120000) return;
      var id = ev.key + '#' + st.step; if (shown.has(id)) return;
      var line2 = ev.time.replace(':', '.') + ' - ' + ev.label, show = true;
      if (st.step === 1) notify({ title: T.n1_title.replace('{type}', typeName(ev)).replace('{n}', st.n), line2: line2, line3: T.n1_body });
      else if (st.step === 2 && !S.settings.bell_active) notify({ title: T.n2_title.replace('{type}', typeName(ev)), line2: line2, line3: T.n2_body, action: T.buka_app, href: '/bunyikan-bel' });
      else if (st.step === 3 && me.role === 'utama') notify({ title: T.n3_title, line2: line2, line3: T.n3_body, action: T.bunyikan_bel, href: '/bunyikan-bel', warn: true });
      else if (st.step === 4 && me.role !== 'utama') notify({ title: T.n4_title, line2: T.n4_body, action: T.buka_app, href: '/bunyikan-bel' });
      else show = false;
      shown.add(id); if (show) localStorage.setItem('ssb_shown', JSON.stringify(Array.from(shown).slice(-200)));
    });
  }

  /* ---------- state & penjadwal ---------- */
  function updatePill() {
    var on = S && S.settings.bell_active;
    if ($('pillIcon')) { $('pillIcon').textContent = on ? '🔔' : '🔕'; $('pillText').textContent = on ? T.suara_aktif : T.suara_nonaktif; }
    if ($('modeText')) $('modeText').textContent = on ? T.otomatis : T.manual;
  }
  async function refresh() {
    try {
      var res = await fetch('/api/state', { headers: { 'X-CSRF-Token': A.csrf } });
      if (res.status === 401) { location.href = '/login'; return; }
      var d = await res.json();
      offset = d.server_ms - Date.now(); S = d; SSB.state = d;
      updatePill(); hooks.forEach(function (h) { h(d); }); handleReminders();
    } catch (e) { /* offline: coba lagi pada putaran berikutnya */ }
  }
  async function autoRing(ev) {
    var r = await api('POST', '/api/ring', { event_key: ev.key, bell_type: ev.type, source: 'otomatis', name: ev.label });
    if (r.ok && !r.data.duplicate) { S.rung.push(ev.key); playBell(ev.sound, volOf(ev.type)); refresh(); }
  }
  function tick() {
    renderClock();
    if (!S || !S.settings.bell_active) return;
    var now = serverNow();
    S.today_events.forEach(function (ev) {
      if (now >= ev.epoch && now - ev.epoch < 45000 && S.rung.indexOf(ev.key) < 0 && !fired.has(ev.key)) {
        fired.add(ev.key); sessionStorage.setItem('ssb_fired', JSON.stringify(Array.from(fired)));
        autoRing(ev);
      }
    });
  }

  /* ---------- UI umum ---------- */
  document.addEventListener('pointerdown', function first() {
    if ('Notification' in window && Notification.permission === 'default') { try { Notification.requestPermission(); } catch (e) {} }
  }, { once: true });
  document.addEventListener('pointerdown', function () {
    if (pending) { var p = pending; pending = null; playBell(p.file, p.vol); }
  });
  var dw = $('drawerWrap');
  if ($('openDrawer')) $('openDrawer').onclick = function () { dw.classList.add('open'); };
  ['closeDrawer', 'drawerShade'].forEach(function (id) { if ($(id)) $(id).onclick = function () { dw.classList.remove('open'); }; });
  if ($('navLogout')) $('navLogout').onclick = function (e) { e.preventDefault(); logout(); };
  if ($('soundPill')) $('soundPill').onclick = async function () {
    var next = !(S && S.settings.bell_active);
    var r = await api('POST', '/api/settings', { bell_active: next });
    if (r.ok) { if (S) S.settings.bell_active = next; updatePill(); refresh(); }
  };

  function normTime(v) {
    var m = /^\s*(\d{1,2})\s*[.:]\s*(\d{2})\s*$/.exec(v || '');
    if (!m || +m[1] > 23 || +m[2] > 59) return '';
    return ('0' + m[1]).slice(-2) + ':' + m[2];
  }

  window.SSB = {
    state: null, normTime: normTime, api: api, flash: flash, confirm: confirmDlg, logout: logout, refresh: refresh, playBell: playBell,
    defaultSound: function (t) { return DEFAULT_SOUND[t] || DEFAULT_SOUND.masuk; },
    onState: function (fn) { hooks.push(fn); if (S) fn(S); }
  };
  refresh(); setInterval(refresh, 5000); setInterval(tick, 1000); renderClock();
})();
