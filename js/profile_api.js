/* ============================================================
   ROOMSYNC — profile_api.js
   Profile page, wired to the API:
   - your name, email, join date, rooms and activity numbers
   - the status picker (saved on the server, visible to your rooms)
   - Edit Profile (change your name) and Log out
   All user text is written with textContent (never innerHTML).
   Needs: js/config.js (window.ROOMSYNC) and <body data-api-profile>.
   ============================================================ */
(function () {
  'use strict';

  var cfg = window.ROOMSYNC;
  if (!cfg || !document.body.hasAttribute('data-api-profile')) { return; }

  var ROOM_KEY = 'roomsync_room';
  var KIND_LABEL = { working: 'Working!', brb: 'BRB!', away: 'Somewhere Else' };
  var DOT_COLORS = ['#df0000', '#34c759', '#f2b84b', '#0073ec', '#c79adb'];

  var me = null;
  var editing = false;

  function read(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }
  function store(key, value) { try { localStorage.setItem(key, value); } catch (e) { /* ignore */ } }
  function drop(key) { try { localStorage.removeItem(key); } catch (e) { /* ignore */ } }
  function byId(id) { return document.getElementById(id); }
  function setText(el, text) { if (el) { el.textContent = text; } }

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
    if (r.status === 422) { return 'Please check what you entered.'; }
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
    }, 2400);
  }

  function statusLabel(status) {
    if (!status) { return KIND_LABEL.working; }
    if (status.kind === 'custom') { return status.text || 'Custom'; }
    return KIND_LABEL[status.kind] || KIND_LABEL.working;
  }

  function formatJoined(iso) {
    var d = new Date(iso);
    if (isNaN(d.getTime())) { return ''; }
    return d.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric', timeZone: 'Asia/Manila' });
  }

  /* ---------- who I am ---------- */
  function renderMe() {
    if (!me) { return; }
    setText(document.querySelector('.profile-name'), me.name);
    setText(byId('sidebarStatusText'), statusLabel(me.status));
    setText(document.querySelector('.profile-name-big'), me.name);
    setText(document.querySelector('.profile-email'), me.email);
    if (!editing) { setText(byId('acctName'), me.name); }
    setText(byId('acctEmail'), me.email);
    setText(byId('acctJoined'), formatJoined(me.joined_at));
    var img = document.querySelector('.profile-photo');
    if (img) { img.alt = me.name; }
    if (window.RoomSyncAvatars) { window.RoomSyncAvatars.showMyPhoto(me.avatar_url); }
    if (removeBtn) { removeBtn.hidden = !me.avatar_url; }

    var select = byId('statusSelect');
    var input = byId('statusCustomInput');
    if (select) { select.value = me.status.kind; }
    var done = byId('statusDoneBtn');
    if (done) { done.hidden = me.status.kind !== 'custom' && !(select && select.value === 'custom'); }
    if (input) {
      input.hidden = me.status.kind !== 'custom';
      if (me.status.kind === 'custom') { input.value = me.status.text || ''; }
    }
    store(cfg.USER_KEY, JSON.stringify({ id: me.id, email: me.email, name: me.name }));
  }

  /* ---------- rooms ---------- */
  function renderRooms(rooms) {
    var badges = document.querySelector('.profile-badges');
    var grid = byId('profileRoomGrid');
    if (badges) {
      badges.textContent = '';
      rooms.filter(function (r) { return r.role === 'admin'; }).forEach(function (r) {
        var b = document.createElement('span');
        b.className = 'profile-badge';
        b.textContent = 'ADMIN • ' + r.name.toUpperCase();
        badges.appendChild(b);
      });
    }
    if (!grid) { return; }
    grid.textContent = '';
    if (!rooms.length) {
      var empty = document.createElement('p');
      empty.className = 'empty-day-note';
      empty.textContent = 'You are not in any rooms yet. Join or create one from the home page.';
      grid.appendChild(empty);
      return;
    }
    rooms.forEach(function (r, i) {
      var card = document.createElement('div');
      card.className = 'profile-room-card';
      var text = document.createElement('div');
      var name = document.createElement('div');
      name.className = 'profile-room-name';
      name.textContent = r.name;
      var role = document.createElement('div');
      role.className = 'profile-room-role';
      role.textContent = r.role === 'admin' ? 'Admin' : 'Member';
      text.appendChild(name);
      text.appendChild(role);
      var dot = document.createElement('span');
      dot.className = 'profile-room-dot';
      dot.style.background = DOT_COLORS[i % DOT_COLORS.length];
      card.appendChild(text);
      card.appendChild(dot);
      grid.appendChild(card);
    });
  }

  /* ---------- activity ---------- */
  function renderStats(s) {
    var pending = Math.max(0, s.submitted - s.approved - s.rejected);
    setText(byId('statSubmitted'), String(s.submitted));
    setText(byId('statApproved'), String(s.approved));
    setText(byId('statPending'), String(pending));
  }

  /* ---------- profile photo ---------- */
  var MAX_PHOTO = 2 * 1024 * 1024;
  var PHOTO_TYPES = ['image/jpeg', 'image/png', 'image/webp'];
  var PHOTO_ERRORS = {
    413: 'That picture is too big. The limit is 2 MB.',
    422: "We couldn't read that picture. Use a JPEG, PNG or WebP photo.",
    429: 'Too many photo changes. Try again in a while.'
  };
  var busy = false;
  var editBtn = document.querySelector('.profile-photo-edit');

  var picker = document.createElement('input');
  picker.type = 'file';
  picker.accept = PHOTO_TYPES.join(',');
  picker.hidden = true;
  document.body.appendChild(picker);

  var removeBtn = document.createElement('button');
  removeBtn.type = 'button';
  removeBtn.className = 'profile-photo-remove';
  removeBtn.textContent = 'Remove photo';
  removeBtn.hidden = true;
  var emailEl = document.querySelector('.profile-email');
  if (emailEl && emailEl.parentNode) { emailEl.parentNode.insertBefore(removeBtn, emailEl.nextSibling); }

  function setBusy(on) {
    busy = on;
    if (editBtn) { editBtn.disabled = on; }
    removeBtn.disabled = on;
  }
  function photoChanged(message) {
    renderMe();
    document.dispatchEvent(new CustomEvent('roomsync:rooms-changed'));   // the sidebar member list shows photos too
    showToast(message);
  }

  if (editBtn) {
    editBtn.type = 'button';
    editBtn.addEventListener('click', function () { if (!busy) { picker.click(); } });
  }

  picker.addEventListener('change', async function () {
    var file = picker.files && picker.files[0];
    picker.value = '';
    if (!file || busy || !me) { return; }
    if (PHOTO_TYPES.indexOf(file.type) === -1) { showToast('Choose a JPEG, PNG or WebP picture.'); return; }
    if (file.size > MAX_PHOTO) { showToast(PHOTO_ERRORS[413]); return; }
    setBusy(true);
    var res;
    try {
      res = await fetch(cfg.API_BASE + '/users/me/avatar', {
        method: 'PUT',
        headers: { Authorization: 'Bearer ' + read(cfg.TOKEN_KEY), 'Content-Type': file.type },
        body: file
      });
    } catch (e) {
      setBusy(false);
      showToast(errorText({ status: 0, body: null }));
      return;
    }
    var body = null;
    try { body = await res.json(); } catch (e) { body = null; }
    setBusy(false);
    if (res.status === 401) { goLogin(); return; }
    if (!res.ok) { showToast(PHOTO_ERRORS[res.status] || errorText({ status: res.status, body: body })); return; }
    me.avatar_url = body.avatar_url;
    photoChanged('Photo updated.');
  });

  removeBtn.addEventListener('click', async function () {
    if (busy || !me) { return; }
    setBusy(true);
    var r = await api('/users/me/avatar', 'DELETE');
    setBusy(false);
    if (!r.ok) { showToast(errorText(r)); return; }
    me.avatar_url = null;
    photoChanged('Photo removed.');
  });

  /* ---------- status picker ---------- */
  async function saveStatus(payload) {
    var r = await api('/users/me', 'PATCH', payload);
    if (!r.ok) {
      showToast(errorText(r));
      renderMe(); // put the picker back to what the server has
      return;
    }
    me = r.body;
    renderMe();
    showToast('Status updated.');
  }

  var select = byId('statusSelect');
  var customInput = byId('statusCustomInput');
  var doneBtn = byId('statusDoneBtn');
  if (select) {
    select.addEventListener('change', function () {
      if (select.value === 'custom') {
        customInput.hidden = false;
        if (doneBtn) { doneBtn.hidden = false; }
        customInput.focus();
      } else {
        customInput.hidden = true;
        if (doneBtn) { doneBtn.hidden = true; }
        saveStatus({ status_kind: select.value });
      }
    });
  }
  if (customInput) {
    var sendCustom = function () {
      var text = customInput.value.trim();
      if (select.value !== 'custom' || !text) { return; }
      if (me && me.status.kind === 'custom' && me.status.text === text) { return; }
      saveStatus({ status_kind: 'custom', status_text: text });
    };
    customInput.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); sendCustom(); customInput.blur(); }
    });
    // The Done button is the obvious way to save; Enter works too. (No save-on-blur: it would
    // save twice when Done is clicked.)
    if (doneBtn) {
      doneBtn.addEventListener('click', function () {
        if (!customInput.value.trim()) { showToast('Type your status first.'); customInput.focus(); return; }
        sendCustom();
      });
    }
  }

  /* ---------- edit name ---------- */
  var editBtn = byId('editProfileBtn');

  function stopEditing() {
    editing = false;
    if (editBtn) { editBtn.textContent = 'Edit Profile'; }
    renderMe();
  }

  async function saveName() {
    var field = byId('acctNameInput');
    if (!field || !me) { return; }
    var value = field.value.trim();
    if (!value) { showToast('Name cannot be empty.'); field.focus(); return; }
    if (value === me.name) { stopEditing(); return; }
    var saveBtn = byId('acctNameSave');
    if (saveBtn) { saveBtn.disabled = true; }
    var r = await api('/users/me', 'PATCH', { name: value });
    if (saveBtn) { saveBtn.disabled = false; }
    if (!r.ok) { showToast(errorText(r)); return; }
    me = r.body;
    stopEditing();
    showToast('Name updated.');
  }

  function startEditing() {
    var cell = byId('acctName');
    if (!cell || !me) { return; }
    editing = true;
    if (editBtn) { editBtn.textContent = 'Save'; }
    var wrap = document.createElement('span');
    wrap.className = 'name-edit-row';
    var field = document.createElement('input');
    field.type = 'text';
    field.id = 'acctNameInput';
    field.className = 'status-custom-input';
    field.maxLength = 100;
    field.value = me.name;
    field.setAttribute('aria-label', 'Full name');
    field.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); saveName(); }
      if (e.key === 'Escape') { stopEditing(); }
    });
    var save = document.createElement('button');
    save.type = 'button';
    save.id = 'acctNameSave';
    save.className = 'status-done-btn';
    save.textContent = 'Save';
    save.addEventListener('click', saveName);
    var cancel = document.createElement('button');
    cancel.type = 'button';
    cancel.className = 'status-cancel-btn';
    cancel.textContent = 'Cancel';
    cancel.addEventListener('click', stopEditing);
    wrap.appendChild(field);
    wrap.appendChild(save);
    wrap.appendChild(cancel);
    cell.textContent = '';
    cell.appendChild(wrap);
    field.focus();
    field.select();
  }

  if (editBtn) {
    editBtn.addEventListener('click', function () {
      if (editing) { saveName(); } else { startEditing(); }
    });
  }

  /* ---------- log out ---------- */
  var logoutBtn = byId('logoutBtn');
  if (logoutBtn) { logoutBtn.addEventListener('click', goLogin); }

  /* ---------- start ---------- */
  async function init() {
    var results = await Promise.all([api('/users/me'), api('/users/me/stats'), api('/rooms')]);
    if (results[0].ok) { me = results[0].body; renderMe(); } else if (results[0].status !== 401) { showToast(errorText(results[0])); }
    if (results[1].ok) { renderStats(results[1].body); }
    if (results[2].ok) { renderRooms(results[2].body); }
  }
  init();
})();