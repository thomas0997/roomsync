/* ============================================================
   ROOMSYNC — user_view.js
   Someone else's profile: profile.html?id=<user id>.
   Shows their name, photo, status, when they joined, and the rooms you share. Never their email.
   Only works for people in one of your rooms (the server answers 404 for anyone else).
   Your own profile (no ?id=) is handled by js/profile_api.js. All text is written with textContent.
   Needs: js/sidebar_rooms.js (window.RoomSyncHome, window.RoomSyncAvatars) loaded first.
   ============================================================ */
(function () {
  'use strict';

  var home = window.RoomSyncHome;
  var cfg = window.ROOMSYNC || {};
  var params = new URLSearchParams(window.location.search);
  if (!home || !document.body.hasAttribute('data-api-profile') || !params.has('id')) { return; }

  var KIND_LABEL = { working: 'Working!', brb: 'BRB!', away: 'Somewhere Else' };
  var DOT_COLORS = ['#df0000', '#34c759', '#f2b84b', '#0073ec', '#c79adb'];
  var wanted = params.get('id') || '';

  function byId(id) { return document.getElementById(id); }
  function setText(el, text) { if (el) { el.textContent = text; } }
  function myId() {
    try { return JSON.parse(localStorage.getItem(cfg.USER_KEY || 'roomsync_user') || 'null').id; } catch (e) { return null; }
  }

  if (/^[0-9]+$/.test(wanted) && Number(wanted) === myId()) { window.location.replace('profile.html'); return; }
  document.body.classList.add('profile-viewing');

  function statusLabel(status) {
    if (!status) { return KIND_LABEL.working; }
    if (status.kind === 'custom') { return status.text || 'Custom'; }
    return KIND_LABEL[status.kind] || KIND_LABEL.working;
  }
  // Colour of the little dot on your avatar: green working, yellow BRB, red away, grey custom.
  function setStatusDot(status) {
    var dot = document.querySelector('.sidebar-footer .status-dot');
    if (!dot) { return; }
    var kind = status && status.kind;
    if (kind !== 'brb' && kind !== 'away' && kind !== 'custom') { kind = 'working'; }
    dot.className = 'status-dot status-' + kind;
  }

  function formatJoined(iso) {
    var d = new Date(iso);
    if (isNaN(d.getTime())) { return ''; }
    return d.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric', timeZone: 'Asia/Manila' });
  }

  // The sidebar footer is about YOU, as on every other page.
  function renderMyFooter(me) {
    setText(document.querySelector('.profile-name'), me.name);
    setText(byId('sidebarStatusText'), statusLabel(me.status));
    setStatusDot(me.status);
    if (window.RoomSyncAvatars && me.avatar_url) {
      window.RoomSyncAvatars.photoSrc(me.avatar_url).then(function (src) {
        if (!src) { return; }
        document.querySelectorAll('.avatar-img').forEach(function (img) { img.src = src; });
      });
    }
  }

  function notFound() {
    setText(document.querySelector('.profile-name-big'), 'Profile not found');
    setText(document.querySelector('.profile-email'), "This person isn't in any of your rooms, or the account no longer exists.");
    var badges = document.querySelector('.profile-badges');
    if (badges) { badges.textContent = ''; }
    var title = byId('profileRoomsTitle');
    if (title) { title.hidden = true; }
    var grid = byId('profileRoomGrid');
    if (grid) { grid.textContent = ''; }
    document.title = 'Profile not found | roomsync';
  }

  function renderRooms(rooms) {
    var title = byId('profileRoomsTitle');
    var grid = byId('profileRoomGrid');
    setText(title, 'Rooms in common');
    if (!grid) { return; }
    grid.textContent = '';
    rooms.forEach(function (r, i) {
      var card = document.createElement('div');
      card.className = 'profile-room-card';
      var text = document.createElement('div');
      var name = document.createElement('div');
      name.className = 'profile-room-name';
      name.textContent = r.name;
      var role = document.createElement('div');
      role.className = 'profile-room-role';
      role.textContent = 'Shared room';
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

  function renderPerson(u) {
    document.title = u.name + ' | roomsync';
    setText(document.querySelector('.profile-name-big'), u.name);
    setText(document.querySelector('.profile-email'), 'Joined ' + formatJoined(u.joined_at));
    var badges = document.querySelector('.profile-badges');
    if (badges) {
      badges.textContent = '';
      var chip = document.createElement('span');
      chip.className = 'profile-badge';
      chip.textContent = statusLabel(u.status);
      badges.appendChild(chip);
    }
    var img = document.querySelector('.profile-photo');
    if (img) {
      img.alt = u.name;
      if (u.avatar_url && window.RoomSyncAvatars) {
        window.RoomSyncAvatars.photoSrc(u.avatar_url).then(function (src) { if (src) { img.src = src; } });
      }
    }
    renderRooms(u.rooms);
  }

  async function start() {
    if (!/^[0-9]+$/.test(wanted)) { notFound(); return; }
    var results = await Promise.all([home.api('/users/me'), home.api('/users/' + wanted)]);
    if (results[0].ok) { renderMyFooter(results[0].body); }
    if (results[1].ok) { renderPerson(results[1].body); return; }
    if (results[1].status === 404 || results[1].status === 422) { notFound(); return; }
    if (results[1].status !== 401) { home.showToast(home.errorText(results[1])); }
  }
  start();
})();
