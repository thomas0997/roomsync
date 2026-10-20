/* ============================================================
   ROOMSYNC — home_rooms.js
   Home page rooms, wired to the API:
   - sends logged-out visitors to login.html
   - lists your rooms (sidebar + mobile/tablet dropdowns)
   - shows the members of the selected room
   - create a room, join a room with an invite code
   - shows your name and a Log out button
   All user text is written with textContent (never innerHTML).
   Needs: js/config.js (window.ROOMSYNC) and <body data-api-rooms>.
   ============================================================ */
(function () {
  'use strict';

  var cfg = window.ROOMSYNC;
  if (!cfg) { return; }

  var LAST_ROOM_KEY = 'roomsync_room';
  var MAX_VISIBLE_MEMBERS = 5;

  var rooms = [];
  var members = [];
  var currentId = null;
  var membersExpanded = false;

  /* ---------- tiny helpers ---------- */
  function read(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }
  function store(key, value) { try { localStorage.setItem(key, value); } catch (e) { /* ignore */ } }
  function drop(key) { try { localStorage.removeItem(key); } catch (e) { /* ignore */ } }
  function byId(id) { return document.getElementById(id); }

  function goLogin() {
    drop(cfg.TOKEN_KEY);
    drop(cfg.USER_KEY);
    drop(LAST_ROOM_KEY);
    window.location.replace('login.html');
  }

  // Logged out? Leave before doing anything else.
  if (!read(cfg.TOKEN_KEY)) { goLogin(); return; }

  // One place that talks to the API. Adds the token, parses JSON,
  // and sends you to the login page if the server says 401.
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

  function firstChar(text) {
    var chars = Array.from((text || '').trim());
    return chars.length ? chars[0].toUpperCase() : '?';
  }

  function initials(name) {
    var parts = (name || '').trim().split(/\s+/).filter(Boolean);
    if (!parts.length) { return '?'; }
    var out = firstChar(parts[0]);
    if (parts.length > 1) { out += firstChar(parts[parts.length - 1]); }
    return out;
  }

  function currentRoom() {
    for (var i = 0; i < rooms.length; i++) {
      if (rooms[i].id === currentId) { return rooms[i]; }
    }
    return null;
  }

  /* ---------- rendering: rooms ---------- */
  function letterAvatar(name, outlined) {
    var el = document.createElement('span');
    el.className = 'room-avatar room-avatar-letter' + (outlined ? ' room-avatar-outline' : '');
    el.textContent = firstChar(name);
    el.setAttribute('aria-hidden', 'true');
    return el;
  }

  function renderDesktopPills() {
    var box = document.querySelector('.room-buttons');
    var newBtn = byId('newRoomBtnDesktop');
    if (!box || !newBtn) { return; }
    box.querySelectorAll('.room-pill:not(.room-pill-new)').forEach(function (el) { el.remove(); });
    rooms.forEach(function (r) {
      var active = r.id === currentId;
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'room-pill' + (active ? ' room-pill-active' : '');
      btn.dataset.roomId = String(r.id);
      btn.appendChild(letterAvatar(r.name, !active));
      var name = document.createElement('span');
      name.className = 'room-name';
      name.textContent = r.name;
      btn.appendChild(name);
      if (r.pending_count > 0) {
        var count = document.createElement('span');
        count.className = 'room-count';
        count.textContent = String(r.pending_count);
        count.title = r.pending_count + ' waiting for approval';
        btn.appendChild(count);
      }
      box.insertBefore(btn, newBtn);
    });
  }

  function renderDropdowns() {
    ['roomDropdownMobile', 'roomDropdownTablet'].forEach(function (id) {
      var dd = byId(id);
      if (!dd) { return; }
      var newItem = dd.querySelector('.room-dropdown-item-new');
      dd.querySelectorAll('.room-dropdown-item:not(.room-dropdown-item-new)').forEach(function (el) { el.remove(); });
      rooms.forEach(function (r) {
        var active = r.id === currentId;
        var item = document.createElement('button');
        item.type = 'button';
        item.className = 'room-dropdown-item' + (active ? ' active' : '');
        item.dataset.roomId = String(r.id);
        item.appendChild(letterAvatar(r.name, !active));
        item.appendChild(document.createTextNode(' ' + r.name));
        dd.insertBefore(item, newItem);
      });
    });
  }

  function renderTodoRoomSelect() {
    var select = byId('todoModalRoom');
    if (!select) { return; }
    while (select.firstChild) { select.removeChild(select.firstChild); }
    rooms.forEach(function (r) {
      var opt = document.createElement('option');
      opt.value = r.name;
      opt.textContent = r.name;
      select.appendChild(opt);
    });
  }

  function renderHeader() {
    var room = currentRoom();
    var label = room ? room.name : 'No rooms yet';
    document.querySelectorAll('[data-room-name]').forEach(function (el) { el.textContent = label; });
    document.querySelectorAll('[data-room-title-name]').forEach(function (el) {
      el.textContent = room ? room.name : 'your room';
    });
    document.querySelectorAll('[data-room-avatar]').forEach(function (el) {
      el.textContent = room ? firstChar(room.name) : '+';
    });
    var discInput = byId('discMessageInput');
    if (discInput && room) { discInput.placeholder = 'Message ' + room.name + '...'; }
    // The old demo cards only show for a room named "The Bozos". Using the
    // room id instead means a real room never shows demo tasks.
    document.body.setAttribute('data-current-room', room ? 'room-' + room.id : 'none');
  }

  /* ---------- rendering: members ---------- */
  function renderMembers() {
    var list = byId('onlineUsersList');
    if (!list) { return; }
    while (list.firstChild) { list.removeChild(list.firstChild); }

    var visible = membersExpanded ? members : members.slice(0, MAX_VISIBLE_MEMBERS);
    visible.forEach(function (m) {
      var li = document.createElement('li');
      li.className = 'online-user online-user-clickable';
      li.dataset.name = m.name;
      li.dataset.initials = initials(m.name);
      li.dataset.online = '';

      var avatar = document.createElement('span');
      avatar.className = 'online-user-avatar';
      avatar.textContent = initials(m.name);
      li.appendChild(avatar);

      var name = document.createElement('span');
      name.className = 'online-user-name';
      name.textContent = m.name;
      li.appendChild(name);

      if (m.role === 'admin') {
        var role = document.createElement('span');
        role.className = 'online-user-role';
        role.textContent = 'Admin';
        li.appendChild(role);
      }
      list.appendChild(li);
    });

    var hidden = members.length - visible.length;
    if (hidden > 0 || (membersExpanded && members.length > MAX_VISIBLE_MEMBERS)) {
      var li2 = document.createElement('li');
      var more = document.createElement('button');
      more.type = 'button';
      more.className = 'online-user-more';
      more.textContent = hidden > 0 ? '+' + hidden + ' other' + (hidden === 1 ? '' : 's') : 'Show less';
      more.addEventListener('click', function () {
        membersExpanded = !membersExpanded;
        renderMembers();
      });
      li2.appendChild(more);
      list.appendChild(li2);
    }
  }

  function renderInviteCode() {
    var line = byId('inviteCodeLine');
    var value = byId('inviteCodeValue');
    var room = currentRoom();
    if (!line || !value) { return; }
    // Only admins see the code, so they decide who gets in.
    if (room && room.role === 'admin') {
      value.textContent = room.invite_code;
      line.hidden = false;
    } else {
      value.textContent = '';
      line.hidden = true;
    }
  }

  async function loadMembers(roomId) {
    var r = await api('/rooms/' + roomId + '/members');
    if (roomId !== currentId) { return; }   // you switched rooms while this loaded
    members = r.ok ? r.body : [];
    if (!r.ok) { showToast(errorText(r)); }
    membersExpanded = false;
    renderMembers();
  }

  /* ---------- selecting a room ---------- */
  function selectRoom(id) {
    currentId = id;
    if (id !== null) { store(LAST_ROOM_KEY, String(id)); }
    members = [];
    renderDesktopPills();
    renderDropdowns();
    renderTodoRoomSelect();
    renderHeader();
    renderInviteCode();
    renderMembers();
    if (id !== null) { loadMembers(id); }
  }

  function closeRoomDropdowns() {
    ['roomDropdownMobile', 'roomDropdownTablet'].forEach(function (id) {
      var dd = byId(id);
      if (dd) { dd.hidden = true; }
    });
    ['roomPillBtnMobile', 'roomPillBtnTablet'].forEach(function (id) {
      var btn = byId(id);
      if (btn) { btn.setAttribute('aria-expanded', 'false'); }
    });
  }

  document.addEventListener('click', function (e) {
    var target = e.target.closest ? e.target.closest('[data-room-id]') : null;
    if (!target) { return; }
    selectRoom(Number(target.dataset.roomId));
    closeRoomDropdowns();
  });

  /* ---------- new room modal ---------- */
  function setModalOpen(open) {
    var overlay = byId('newRoomModalOverlay');
    if (overlay) { overlay.hidden = !open; }
  }

  function showFormError(id, message) {
    var el = byId(id);
    if (!el) { return; }
    el.textContent = message || '';
    el.hidden = !message;
  }

  function addRoom(room) {
    var found = false;
    for (var i = 0; i < rooms.length; i++) {
      if (rooms[i].id === room.id) { rooms[i] = room; found = true; }
    }
    if (!found) { rooms.push(room); }
  }

  var joinForm = byId('joinRoomForm');
  if (joinForm) {
    joinForm.addEventListener('submit', async function (e) {
      e.preventDefault();
      showFormError('joinError', '');
      var btn = joinForm.querySelector('[type="submit"]');
      var code = byId('joinCodeInput').value.trim();
      btn.disabled = true;
      var r = await api('/rooms/join', 'POST', { invite_code: code });
      btn.disabled = false;
      if (!r.ok) { showFormError('joinError', errorText(r)); return; }
      addRoom(r.body);
      joinForm.reset();
      setModalOpen(false);
      selectRoom(r.body.id);
      showToast('Joined ' + r.body.name);
    });
  }

  var createForm = byId('createRoomForm');
  if (createForm) {
    createForm.addEventListener('submit', async function (e) {
      e.preventDefault();
      showFormError('createError', '');
      var btn = createForm.querySelector('[type="submit"]');
      var name = byId('createNameInput').value.trim();
      if (!name) { showFormError('createError', 'Give your room a name.'); return; }
      btn.disabled = true;
      var r = await api('/rooms', 'POST', { name: name, type: byId('createTypeSelect').value });
      btn.disabled = false;
      if (!r.ok) { showFormError('createError', errorText(r)); return; }
      addRoom(r.body);
      createForm.reset();
      setModalOpen(false);
      selectRoom(r.body.id);
      showToast('Room created! Share the invite code from the sidebar.');
    });
  }

  /* ---------- profile row + log out ---------- */
  function renderProfile() {
    var user = null;
    try { user = JSON.parse(read(cfg.USER_KEY) || 'null'); } catch (e) { user = null; }
    var nameEl = document.querySelector('.profile-name');
    var statusEl = document.querySelector('.profile-status');
    var img = document.querySelector('.avatar-img');
    if (nameEl) { nameEl.textContent = user && user.name ? user.name : ''; }
    if (statusEl) { statusEl.textContent = ''; }
    if (img && user && user.name) { img.alt = user.name; }
  }

  var logoutBtn = byId('logoutBtn');
  if (logoutBtn) { logoutBtn.addEventListener('click', goLogin); }

  /* ---------- start ---------- */
  async function init() {
    renderProfile();
    var r = await api('/rooms');
    if (!r.ok) {
      showToast(errorText(r));
      renderHeader();
      return;
    }
    rooms = r.body;
    if (rooms.length === 0) {
      selectRoom(null);
      setModalOpen(true);   // empty state: offer Join / Create straight away
      return;
    }
    var saved = Number(read(LAST_ROOM_KEY));
    var start = rooms[0].id;
    rooms.forEach(function (room) { if (room.id === saved) { start = saved; } });
    selectRoom(start);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();