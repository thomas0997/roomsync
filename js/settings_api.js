/* ============================================================
   ROOMSYNC — settings_api.js
   Settings page, wired to the API:
   - lists your real rooms, each with a Leave Room button
   - Delete Account (type DELETE to confirm)
   Theme and the toggles stay in the browser until T2.
   All user text is written with textContent (never innerHTML).
   Needs: js/config.js (window.ROOMSYNC) and <body data-api-settings>.
   ============================================================ */
(function () {
  'use strict';

  var cfg = window.ROOMSYNC;
  if (!cfg || !document.body.hasAttribute('data-api-settings')) { return; }

  var ROOM_KEY = 'roomsync_room';

  function read(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }
  function drop(key) { try { localStorage.removeItem(key); } catch (e) { /* ignore */ } }
  function byId(id) { return document.getElementById(id); }

  function goLogin() {
    drop(cfg.TOKEN_KEY);
    drop(cfg.USER_KEY);
    drop(ROOM_KEY);
    window.location.replace('login.html');
  }

  if (!read(cfg.TOKEN_KEY)) { goLogin(); return; }

  // "Show empty days": kept in this browser; the Home board reads the same key.
  var emptyDaysBox = document.getElementById('showEmptyDays');
  if (emptyDaysBox) {
    emptyDaysBox.checked = read('roomsync.showEmptyDays') === '1';
    emptyDaysBox.addEventListener('change', function () {
      try { localStorage.setItem('roomsync.showEmptyDays', emptyDaysBox.checked ? '1' : '0'); } catch (e) { /* ignore */ }
    });
  }

  async function api(path, method, payload) {
    var opts = { method: method || 'GET', headers: { Authorization: 'Bearer ' + read(cfg.TOKEN_KEY) } };
    if (payload !== undefined) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(payload);
    }
    var res;
    try {
      res = await fetch(cfg.API_BASE + path, opts);
    } catch (e) {
      return { ok: false, status: 0, body: null };
    }
    if (res.status === 401) { goLogin(); return { ok: false, status: 401, body: null }; }
    var body = null;
    if (res.status !== 204) {
      try { body = await res.json(); } catch (e) { body = null; }
    }
    return { ok: res.ok, status: res.status, body: body };
  }

  function errorText(r) {
    if (r.status === 0) { return "Can't reach the server. Check your connection and try again."; }
    if (r.body && typeof r.body.detail === 'string') { return r.body.detail; }
    return 'Something went wrong. Please try again.';
  }

  function showToast(message) {
    var toast = document.createElement('div');
    toast.className = 'abt-toast';
    toast.textContent = message;
    document.body.appendChild(toast);
    requestAnimationFrame(function () { toast.classList.add('abt-toast-show'); });
    setTimeout(function () {
      toast.classList.remove('abt-toast-show');
      setTimeout(function () { toast.remove(); }, 250);
    }, 3200);
  }

  /* ---------- your name in the sidebar ---------- */
  (function showName() {
    var user = null;
    try { user = JSON.parse(read(cfg.USER_KEY) || 'null'); } catch (e) { user = null; }
    var nameEl = document.querySelector('.profile-name');
    var statusEl = document.querySelector('.profile-status');
    if (nameEl) { nameEl.textContent = user && user.name ? user.name : ''; }
    if (statusEl) { statusEl.textContent = ''; }
  })();

  /* ---------- rooms + Leave ---------- */
  var list = byId('settingsRooms');

  function renderRooms(rooms) {
    list.textContent = '';
    if (!rooms.length) {
      var row = document.createElement('div');
      row.className = 'settings-row settings-row-last';
      var text = document.createElement('div');
      text.className = 'settings-row-text';
      var label = document.createElement('div');
      label.className = 'settings-row-sub';
      label.textContent = 'You are not in any rooms.';
      text.appendChild(label);
      row.appendChild(text);
      list.appendChild(row);
      return;
    }
    rooms.forEach(function (r, i) {
      var row = document.createElement('div');
      row.className = 'settings-row' + (i === rooms.length - 1 ? ' settings-row-last' : '');
      var text = document.createElement('div');
      text.className = 'settings-row-text';
      var label = document.createElement('div');
      label.className = 'settings-row-label settings-room-name';
      label.textContent = r.name;
      text.appendChild(label);
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn-leave-room';
      btn.textContent = 'Leave Room';
      btn.addEventListener('click', function () { leave(r, btn); });
      row.appendChild(text);
      row.appendChild(btn);
      list.appendChild(row);
    });
  }

  async function leave(room, btn) {
    var warning = 'Leave "' + room.name + '"? You can rejoin later with an invite code.';
    if (room.member_count <= 1) { warning = 'You are the only member of "' + room.name + '". Leaving deletes the room and everything in it. Continue?'; }
    if (!confirm(warning)) { return; }
    btn.disabled = true;
    var r = await api('/rooms/' + room.id + '/leave', 'POST');
    if (!r.ok) { btn.disabled = false; showToast(errorText(r)); return; }
    if (read(ROOM_KEY) === String(room.id)) { drop(ROOM_KEY); }
    showToast('You left ' + room.name + '.');
    loadRooms();
    document.dispatchEvent(new CustomEvent('roomsync:rooms-changed'));
  }

  async function loadRooms() {
    var r = await api('/rooms');
    if (r.ok) { renderRooms(r.body); } else if (r.status !== 401) { showToast(errorText(r)); }
  }

  /* ---------- Delete Account ---------- */
  var deleteBtn = byId('deleteAccountBtn');
  if (deleteBtn) {
    deleteBtn.addEventListener('click', async function () {
      var typed = prompt('This permanently removes you from every room and closes your account. Type DELETE to confirm.');
      if (typed !== 'DELETE') { return; }
      deleteBtn.disabled = true;
      var r = await api('/users/me', 'DELETE');
      if (!r.ok) { deleteBtn.disabled = false; showToast(errorText(r)); return; }
      goLogin();
    });
  }

  if (list) { loadRooms(); }
})();