/* ============================================================
   ROOMSYNC — sidebar_rooms.js
   The shared sidebar, wired to the API. Loaded on every page after
   js/config.js. It:
   - sends logged-out visitors to login.html
   - lists your rooms (sidebar + mobile/tablet dropdowns) and remembers
     the selected room in localStorage "roomsync_room"
   - shows the members of the selected room
   - create a room, join a room with an invite code
   - shows your name and status
   Other scripts can listen for the "roomsync:room" event (detail.id) and
   ask window.RoomSyncHome.currentRoomId(). Dispatch "roomsync:rooms-changed"
   on document to make this file reload the room list (after leaving a room).
   All user text is written with textContent (never innerHTML).
   Needs: js/config.js (window.ROOMSYNC).
   ============================================================ */
(function () {
  'use strict';

  var cfg = window.ROOMSYNC;
  if (!cfg) { return; }

  // Tell rooms.js this page gets its rooms from the API, so the old demo data stays off.
  document.body.setAttribute('data-api-rooms', '');

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

  /* ---------- profile photos ---------- */
  // <img> tags cannot send the login token, so a photo is downloaded with fetch()
  // and shown from a blob: address. Each photo is downloaded once per page.
  var PLACEHOLDER = '../assets/profile_photo.png';
  var photoCache = {};
  function photoSrc(url) {
    if (!url) { return Promise.resolve(''); }
    if (!photoCache[url]) {
      photoCache[url] = fetch(cfg.API_BASE + url, { headers: { Authorization: 'Bearer ' + read(cfg.TOKEN_KEY) } })
        .then(function (res) { return res.ok ? res.blob() : null; })
        .then(function (blob) { return blob ? URL.createObjectURL(blob) : ''; })
        .catch(function () { return ''; })
        .then(function (src) { if (!src) { delete photoCache[url]; } return src; });
    }
    return photoCache[url];
  }
  function showMyPhoto(url) {
    var imgs = document.querySelectorAll('.avatar-img, .profile-photo');
    photoSrc(url).then(function (src) {
      imgs.forEach(function (img) { img.src = src || PLACEHOLDER; });
    });
  }
  window.RoomSyncAvatars = { photoSrc: photoSrc, showMyPhoto: showMyPhoto };

  function myId() {
    try { return JSON.parse(read(cfg.USER_KEY) || 'null').id; } catch (e) { return null; }
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
      opt.value = String(r.id);
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
      li.dataset.avatar = m.avatar_url || '';
      li.dataset.self = String(m.user_id === myId());

      var avatar = document.createElement('span');
      avatar.className = 'online-user-avatar';
      avatar.textContent = initials(m.name);
      if (m.avatar_url) {
        var pic = document.createElement('img');
        pic.className = 'online-user-photo';
        pic.alt = '';
        photoSrc(m.avatar_url).then(function (src) {
          if (src) { pic.src = src; avatar.insertBefore(pic, avatar.firstChild); }
        });
      }
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
    // Tell the other home scripts (the week board) which room is selected now.
    document.dispatchEvent(new CustomEvent('roomsync:room', { detail: { id: id } }));
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
  // Home's modal has ids and error lines; the other pages' copies are plain. Add what is missing
  // so one set of code below works everywhere.
  function prepareModals() {
    var j = byId('joinRoomForm');
    var c = byId('createRoomForm');
    function needError(form, id) {
      if (!form || byId(id)) { return; }
      var p = document.createElement('p');
      p.className = 'abt-form-error';
      p.id = id;
      p.setAttribute('role', 'alert');
      p.hidden = true;
      var actions = form.querySelector('.abt-form-actions');
      form.insertBefore(p, actions);
    }
    if (j) {
      var ji = j.querySelector('input');
      if (ji && !byId('joinCodeInput')) { ji.id = 'joinCodeInput'; ji.maxLength = 16; ji.placeholder = 'Paste your invite code'; ji.autocomplete = 'off'; }
      needError(j, 'joinError');
    }
    if (c) {
      var ci = c.querySelector('input[type="text"]');
      if (ci && !byId('createNameInput')) { ci.id = 'createNameInput'; ci.maxLength = 100; }
      var cs = c.querySelector('select');
      if (cs && !byId('createTypeSelect')) {
        cs.id = 'createTypeSelect';
        var values = ['classroom', 'study_group', 'team', 'other'];
        Array.prototype.forEach.call(cs.options, function (opt, i) { opt.value = values[i] || 'other'; });
      }
      needError(c, 'createError');
    }
    // The invite code line lives under the member list; home has it in its HTML, the others get it here.
    if (!byId('inviteCodeLine') && byId('onlineUsersList')) {
      var line = document.createElement('p');
      line.className = 'invite-code-line';
      line.id = 'inviteCodeLine';
      line.hidden = true;
      line.appendChild(document.createTextNode('Invite code: '));
      var strong = document.createElement('strong');
      strong.id = 'inviteCodeValue';
      line.appendChild(strong);
      byId('onlineUsersList').parentNode.appendChild(line);
    }
    // We have no live "online" tracking yet (T2), so call the list what it is.
    document.querySelectorAll('.online-users-title').forEach(function (el) { el.textContent = 'Members'; });
  }
  prepareModals();
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

  /* ---------- profile row ---------- */
  var KIND_LABEL = { working: 'Working!', brb: 'BRB!', away: 'Somewhere Else' };

  function statusLabel(st) {
    if (!st) { return KIND_LABEL.working; }
    if (st.kind === 'custom') { return st.text || 'Custom'; }
    return KIND_LABEL[st.kind] || KIND_LABEL.working;
  }

  async function renderProfile() {
    var user = null;
    try { user = JSON.parse(read(cfg.USER_KEY) || 'null'); } catch (e) { user = null; }
    var nameEl = document.querySelector('.profile-name');
    var statusEl = document.querySelector('.profile-status');
    var img = document.querySelector('.avatar-img');
    if (nameEl) { nameEl.textContent = user && user.name ? user.name : ''; }
    if (statusEl) { statusEl.textContent = ''; }
    if (img && user && user.name) { img.alt = user.name; }
    // The profile page fills in its own name and status (js/profile_api.js).
    if (document.body.hasAttribute('data-api-profile')) { return; }
    var r = await api('/users/me');
    if (!r.ok) { return; }
    if (nameEl) { nameEl.textContent = r.body.name; }
    if (statusEl) { statusEl.textContent = statusLabel(r.body.status); }
    if (img) { img.alt = r.body.name; }
    showMyPhoto(r.body.avatar_url);
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

  // What home_board.js needs from this file.
  window.RoomSyncHome = {
    api: api,
    showToast: showToast,
    errorText: errorText,
    currentRoomId: function () { return currentId; },
    isAdmin: function () { var r = currentRoom(); return !!(r && r.role === 'admin'); }
  };

  // Another script (for example Settings after Leave Room) can ask for a fresh room list.
  document.addEventListener('roomsync:rooms-changed', function () { init(); });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();