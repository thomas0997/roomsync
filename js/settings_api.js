/* ============================================================
   ROOMSYNC — settings_api.js
   Settings page, wired to the API:
   - lists your real rooms, each with a Leave Room button
   - Delete Account (type DELETE to confirm)
   - Show empty days and Task Colors: saved on your account (GET/PUT /users/me/settings, T2),
     so they follow you to any device. The notification toggles are not wired yet.
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
      if (r.role === 'admin') { text.appendChild(iconControls(r)); }   // only admins change the icon (shown under the name)
      row.appendChild(text);
      row.appendChild(btn);
      list.appendChild(row);
    });
  }

  /* ---------- room icon (admins) ---------- */
  var ICON_TYPES = ['image/jpeg', 'image/png', 'image/webp'];
  var MAX_ICON = 2 * 1024 * 1024;   // same as the server

  function iconControls(room) {
    var box = document.createElement('div');
    box.className = 'settings-room-icon';
    var picker = document.createElement('input');
    picker.type = 'file';
    picker.accept = 'image/jpeg,image/png,image/webp';
    picker.hidden = true;
    var change = document.createElement('button');
    change.type = 'button';
    change.className = 'btn-room-icon';
    change.textContent = room.avatar_url ? 'Change icon' : 'Add icon';
    change.addEventListener('click', function () { picker.click(); });
    box.appendChild(picker);
    box.appendChild(change);
    if (room.avatar_url) {
      var remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'btn-room-icon';
      remove.textContent = 'Remove icon';
      remove.addEventListener('click', async function () {
        remove.disabled = true;
        var r = await api('/rooms/' + room.id + '/avatar', 'DELETE');
        if (!r.ok) { remove.disabled = false; showToast(errorText(r)); return; }
        showToast('Room icon removed.');
        loadRooms();
        document.dispatchEvent(new CustomEvent('roomsync:rooms-changed'));
      });
      box.appendChild(remove);
    }
    picker.addEventListener('change', async function () {
      var file = picker.files && picker.files[0];
      picker.value = '';
      if (!file) { return; }
      if (ICON_TYPES.indexOf(file.type) === -1) { showToast('Choose a JPEG, PNG or WebP picture.'); return; }
      if (file.size > MAX_ICON) { showToast('That picture is too big (2 MB maximum).'); return; }
      change.disabled = true;
      var res;
      try {
        res = await fetch(cfg.API_BASE + '/rooms/' + room.id + '/avatar', {
          method: 'PUT',
          headers: { Authorization: 'Bearer ' + read(cfg.TOKEN_KEY), 'Content-Type': file.type },
          body: file
        });
      } catch (e) {
        change.disabled = false;
        showToast(errorText({ status: 0, body: null }));
        return;
      }
      var body = null;
      try { body = await res.json(); } catch (e) { body = null; }
      change.disabled = false;
      if (res.status === 401) { goLogin(); return; }
      if (!res.ok) { showToast(errorText({ status: res.status, body: body })); return; }
      showToast('Room icon updated.');
      loadRooms();
      document.dispatchEvent(new CustomEvent('roomsync:rooms-changed'));
    });
    return box;
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

  /* ---------- Show empty days + Task Colors (account-level, T2) ---------- */
  var TASK_TYPES = ['exam', 'quiz', 'case-study', 'activity', 'seatwork', 'assignment'];
  var DEFAULT_COLORS = {
    exam: '#df0000', quiz: '#f2b84b', 'case-study': '#c79adb',
    activity: '#f2795a', seatwork: '#009cdf', assignment: '#8f8f97'
  };
  var emptyDaysBox = byId('showEmptyDays');
  var colorInputs = {};
  TASK_TYPES.forEach(function (type) {
    var input = document.querySelector('.settings-color-input[data-type="' + type + '"]');
    if (input) { colorInputs[type] = input; }
  });
  var resetColorsBtn = byId('resetTaskColorsBtn');

  function applySettings(s) {
    if (emptyDaysBox) { emptyDaysBox.checked = !!s.show_empty_days; }
    TASK_TYPES.forEach(function (type) {
      if (colorInputs[type]) { colorInputs[type].value = (s.task_colors && s.task_colors[type]) || DEFAULT_COLORS[type]; }
    });
  }

  async function saveSettings(payload) {
    var r = await api('/users/me/settings', 'PUT', payload);
    if (!r.ok) { showToast(errorText(r)); return null; }
    // Every page's nav (sidebar_rooms.js) reads this to show empty days on Home and to
    // color task badges everywhere; it only re-applies on a fresh load, so ask for one.
    document.dispatchEvent(new CustomEvent('roomsync:rooms-changed'));
    return r.body;
  }

  if (emptyDaysBox) {
    emptyDaysBox.addEventListener('change', function () {
      saveSettings({ show_empty_days: emptyDaysBox.checked });
    });
  }
  Object.keys(colorInputs).forEach(function (type) {
    colorInputs[type].addEventListener('change', function () {
      var colors = {};
      colors[type] = colorInputs[type].value;
      saveSettings({ task_colors: colors }).then(function (s) { if (s) { showToast('Task colors updated.'); } });
    });
  });
  if (resetColorsBtn) {
    resetColorsBtn.addEventListener('click', async function () {
      resetColorsBtn.disabled = true;
      var r = await saveSettings({ task_colors: DEFAULT_COLORS });
      resetColorsBtn.disabled = false;
      if (r) { applySettings(r); showToast('Task colors reset.'); }
    });
  }
  (async function loadSettings() {
    var r = await api('/users/me/settings');
    if (r.ok) { applySettings(r.body); }
  })();

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