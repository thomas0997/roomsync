/* ============================================================
   ROOMSYNC — home_board.js
   Home page week board and New TODO form, wired to the API:
   - loads this week, next week and the week after for the selected room
   - shows approved tasks only (the server decides that)
   - New TODO sends a real task; a member's task waits for an admin to approve it
   Weeks run Sunday to Saturday in Manila time (UTC+8), same as the server.
   All user text is written with textContent (never innerHTML).
   Needs: js/home_rooms.js loaded first (it exposes window.RoomSyncHome).
   ============================================================ */
(function () {
  'use strict';

  var home = window.RoomSyncHome;
  if (!home) { return; }

  var MANILA_MS = 8 * 60 * 60 * 1000;   // Manila is UTC+8, no daylight saving
  var DAY_MS = 24 * 60 * 60 * 1000;
  var MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
                'August', 'September', 'October', 'November', 'December'];
  var DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
  var KNOWN_TYPES = ['exam', 'quiz', 'case-study', 'activity', 'seatwork', 'assignment'];
  var BOARD_IDS = ['board-thisweek', 'board-nextweek', 'board-weekafter'];

  var loadCounter = 0;   // lets us ignore answers that arrive after you switched room

  function byId(id) { return document.getElementById(id); }

  /* ---------- dates (a "calendar day" is a UTC-midnight Date that stands for a Manila day) ---------- */
  function manilaToday() {
    var m = new Date(Date.now() + MANILA_MS);
    return new Date(Date.UTC(m.getUTCFullYear(), m.getUTCMonth(), m.getUTCDate()));
  }
  function addDays(day, n) { return new Date(day.getTime() + n * DAY_MS); }
  function ymd(day) { return day.toISOString().slice(0, 10); }
  function sameDay(a, b) { return ymd(a) === ymd(b); }
  function monthDay(day) { return MONTHS[day.getUTCMonth()] + ' ' + day.getUTCDate(); }
  function shortMonthDay(day) { return MONTHS[day.getUTCMonth()].slice(0, 3) + ' ' + day.getUTCDate(); }

  function weekRange(sunday) {
    var saturday = addDays(sunday, 6);
    if (sunday.getUTCMonth() === saturday.getUTCMonth()) {
      return MONTHS[sunday.getUTCMonth()] + ' ' + sunday.getUTCDate() + ' to ' + saturday.getUTCDate();
    }
    return monthDay(sunday) + ' to ' + monthDay(saturday);
  }

  function manilaDayOf(iso) {
    var m = new Date(new Date(iso).getTime() + MANILA_MS);
    return ymd(new Date(Date.UTC(m.getUTCFullYear(), m.getUTCMonth(), m.getUTCDate())));
  }
  function timeText(task) {
    if (task.all_day) { return 'All day'; }
    var m = new Date(new Date(task.due_at).getTime() + MANILA_MS);
    var h = m.getUTCHours();
    var min = m.getUTCMinutes();
    var suffix = h >= 12 ? 'PM' : 'AM';
    h = h % 12;
    if (h === 0) { h = 12; }
    return h + ':' + (min < 10 ? '0' : '') + min + ' ' + suffix;
  }

  /* ---------- building the cards ---------- */
  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) { node.className = className; }
    if (text !== undefined) { node.textContent = text; }
    return node;
  }

  function reminderCard(task) {
    var card = el('div', 'reminder-card');
    var top = el('div', 'reminder-top');
    var bullet = el('span', 'reminder-bullet');
    bullet.setAttribute('aria-hidden', 'true');
    top.appendChild(bullet);
    top.appendChild(el('p', 'reminder-title', task.title));
    card.appendChild(top);

    var tags = el('div', 'reminder-tags');
    var known = KNOWN_TYPES.indexOf(task.type) !== -1;
    tags.appendChild(el('span', 'type-badge ' + (known ? 'type-' + task.type : 'type-custom'),
                        task.type.replace(/-/g, ' ').toUpperCase()));
    if (task.subject) { tags.appendChild(el('span', 'subject-tag', task.subject)); }
    card.appendChild(tags);

    card.appendChild(el('p', 'reminder-time', timeText(task)));
    return card;
  }

  function dayCard(day, tasks, isToday) {
    var card = el('article', 'day-card' + (isToday ? ' day-card-today' : '') + (tasks.length === 0 ? ' day-card-empty' : ''));
    var head = el('div', 'day-card-head');
    var group = el('div', 'day-card-title-group');
    group.appendChild(el('h3', 'day-name', isToday ? 'Today' : DAYS[day.getUTCDay()]));
    group.appendChild(el('p', 'day-date-sub', isToday ? DAYS[day.getUTCDay()] : shortMonthDay(day)));
    head.appendChild(group);
    if (isToday) {
      var meta = el('div', 'day-card-meta');
      meta.appendChild(el('span', 'date-pill', shortMonthDay(day).toUpperCase()));
      meta.appendChild(el('span', 'task-count', String(tasks.length)));
      head.appendChild(meta);
    } else {
      head.appendChild(el('span', 'task-count', String(tasks.length)));
    }
    card.appendChild(head);
    if (tasks.length === 0) { card.appendChild(el('p', 'empty-day-note', 'No tasks')); }
    tasks.forEach(function (t) { card.appendChild(reminderCard(t)); });
    return card;
  }

  function clear(node) { while (node.firstChild) { node.removeChild(node.firstChild); } }

  function renderWeek(index, sunday, tasks, today) {
    var board = byId(BOARD_IDS[index]);
    var note = byId('weekNote' + index);
    var range = byId('weekRange' + index);
    if (!board) { return; }
    if (range) { range.textContent = weekRange(sunday); }
    clear(board);

    var byDay = {};
    tasks.forEach(function (t) {
      var key = manilaDayOf(t.due_at);
      (byDay[key] = byDay[key] || []).push(t);
    });

    // This week: today onwards (days already gone are not shown). Other weeks: all seven days.
    var firstDay = index === 0 ? Math.max(0, Math.round((today - sunday) / DAY_MS)) : 0;
    var shown = 0;
    var cards = [];
    for (var i = firstDay; i < 7; i++) {
      var day = addDays(sunday, i);
      var list = byDay[ymd(day)] || [];
      shown += list.length;
      cards.push(dayCard(day, list, sameDay(day, today)));
    }
    // A week with nothing in it shows one short note instead of seven empty cards.
    if (shown === 0) {
      if (note) { note.textContent = 'Nothing scheduled yet.'; note.hidden = false; }
      return;
    }
    if (note) { note.hidden = true; }
    cards.forEach(function (c) { board.appendChild(c); });
  }

  function showMessage(text) {
    for (var i = 0; i < 3; i++) {
      var board = byId(BOARD_IDS[i]);
      var note = byId('weekNote' + i);
      if (board) { clear(board); }
      if (note) { note.textContent = i === 0 ? text : ''; note.hidden = i !== 0; }
    }
  }

  /* ---------- loading the board ---------- */
  async function loadBoard(roomId) {
    var mine = ++loadCounter;
    if (roomId === null) {
      showMessage('Join or create a room to see its tasks.');
      return;
    }
    var today = manilaToday();
    var sunday = addDays(today, -today.getUTCDay());
    var results = await Promise.all([0, 1, 2].map(function (i) {
      return home.api('/rooms/' + roomId + '/tasks?week_start=' + ymd(addDays(sunday, 7 * i)));
    }));
    if (mine !== loadCounter) { return; }   // you switched rooms while this loaded
    if (!results.every(function (r) { return r.ok; })) {
      var failed = results.filter(function (r) { return !r.ok; })[0];
      showMessage("Couldn't load tasks.");
      home.showToast(home.errorText(failed));
      return;
    }
    results.forEach(function (r, i) { renderWeek(i, addDays(sunday, 7 * i), r.body, today); });
  }

  document.addEventListener('roomsync:room', function (e) { loadBoard(e.detail.id); });
  if (home.currentRoomId() !== undefined && home.currentRoomId() !== null) {
    loadBoard(home.currentRoomId());   // the room was chosen before this script started
  }

  /* ---------- New TODO form ---------- */
  var form = byId('todoModalForm');
  var errorBox = byId('todoFormError');
  var busy = false;

  function showFormError(text) {
    if (!errorBox) { return; }
    errorBox.textContent = text;
    errorBox.hidden = !text;
  }

  function closeModal() {
    var overlay = byId('todoModalOverlay');
    if (overlay) { overlay.hidden = true; }
  }

  // Opening the form: pick the room you are looking at and clear old errors.
  ['newTodoBtnDesktop', 'newTodoBtnTablet', 'newTodoBtnMobile'].forEach(function (id) {
    var btn = byId(id);
    if (!btn) { return; }
    btn.addEventListener('click', function () {
      showFormError('');
      byId('todoDate').min = ymd(manilaToday());   // the date picker greys out days that are over
      var select = byId('todoModalRoom');
      var current = home.currentRoomId();
      if (select && current !== null && current !== undefined) { select.value = String(current); }
    });
  });

  if (form) {
    form.addEventListener('submit', async function (e) {
      e.preventDefault();
      if (busy) { return; }
      var title = byId('todoTitle').value.trim();
      var type = byId('todoType').value;
      var date = byId('todoDate').value;
      var time = byId('todoTime').value;
      var subject = byId('todoSubject').value.trim();
      var roomId = Number(byId('todoModalRoom').value);

      if (!title || !type || !date || !roomId) {
        showFormError('Please fill in the title, type, due date and room.');
        return;
      }
      // The date and time you typed are Manila time. No time means "all day" (end of that day).
      var dueAt = date + 'T' + (time ? time.slice(0, 5) : '23:59') + ':00+08:00';
      if (new Date(dueAt).getTime() <= Date.now()) {
        showFormError(time ? 'That time has already passed. Pick a time in the future.'
                           : 'That date has already passed. Pick today or a later day.');
        return;
      }
      showFormError('');

      var payload = {
        title: title,
        type: type,
        due_at: dueAt,
        all_day: !time
      };
      if (subject) { payload.subject = subject; }

      busy = true;
      var button = form.querySelector('button[type="submit"]');
      if (button) { button.disabled = true; }
      var r = await home.api('/rooms/' + roomId + '/tasks', 'POST', payload);
      busy = false;
      if (button) { button.disabled = false; }

      if (!r.ok) {
        if (r.status !== 401) { showFormError(home.errorText(r)); }
        return;
      }
      closeModal();
      form.reset();
      if (r.body.status === 'approved') {
        home.showToast('TODO created!');
      } else {
        home.showToast('Sent for approval. It shows on the board once an admin approves it.');
      }
      if (roomId === home.currentRoomId()) { loadBoard(roomId); }
    });
  }
})();