/* ============================================================
   ROOMSYNC — home_board.js
   Home page week board and New TODO form, wired to the API:
   - loads this week, next week and the week after for the selected room
   - shows approved tasks only (the server decides that)
   - tick a task off (click the card), or remove it from YOUR board with the x; both are per user
   - weeks that are over disappear once everything in them is ticked or removed;
     a past week with unticked tasks stays as OVERDUE; "Show earlier weeks" brings the rest back
   - Removed tasks list with Restore
   (the New TODO form lives in js/new_todo.js and works on every page)
   Weeks run Sunday to Saturday in Manila time (UTC+8), same as the server.
   All user text is written with textContent (never innerHTML).
   Needs: js/sidebar_rooms.js loaded first (it exposes window.RoomSyncHome).
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

  function clear(node) { while (node.firstChild) { node.removeChild(node.firstChild); } }

  function typeBadge(task) {
    var known = KNOWN_TYPES.indexOf(task.type) !== -1;
    return el('span', 'type-badge ' + (known ? 'type-' + task.type : 'type-custom'),
              task.type.replace(/-/g, ' ').toUpperCase());
  }

  // Ticked or not: the card, the green bullet and the screen-reader state all follow the task.
  function applyDone(card, bullet, task, done) {
    task.done = done;
    card.classList.toggle('is-complete', done);
    bullet.classList.toggle('is-complete', done);
    card.setAttribute('aria-checked', done ? 'true' : 'false');
    if (window.RoomSyncAlert) { window.RoomSyncAlert.applyCard(card, task); }
  }

  async function toggleDone(card, bullet, task) {
    if (card.dataset.busy) { return; }
    var want = !task.done;
    applyDone(card, bullet, task, want);          // show it straight away, undo if the server says no
    card.dataset.busy = '1';
    var r = await home.api('/tasks/' + task.id + '/done', want ? 'PUT' : 'DELETE');
    delete card.dataset.busy;
    if (r.ok) { return; }
    applyDone(card, bullet, task, !want);
    if (r.status === 401) { return; }
    home.showToast(home.errorText(r));
    if (r.status === 404 || r.status === 409) { loadBoard(home.currentRoomId()); }   // the task changed under us
  }

  async function removeTask(task) {
    var r = await home.api('/tasks/' + task.id + '/hidden', 'PUT');
    if (!r.ok) {
      if (r.status !== 401) { home.showToast(home.errorText(r)); }
      if (r.status === 404 || r.status === 409) { loadBoard(home.currentRoomId()); }
      return;
    }
    home.showToast('Removed from your Home page. Restore it under Removed tasks.');
    loadBoard(home.currentRoomId());
  }

  var SVG_NS = 'http://www.w3.org/2000/svg';
  function trashIcon() {
    var svg = document.createElementNS(SVG_NS, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '2');
    svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round');
    var path = document.createElementNS(SVG_NS, 'path');
    path.setAttribute('d', 'M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14M10 11v6M14 11v6');
    svg.appendChild(path);
    return svg;
  }

  // Admins can delete a task for the whole room. Asks first; it cannot be undone.
  async function deleteTask(task) {
    if (!window.confirm('Delete "' + task.title + '" for everyone in the room? This cannot be undone.')) { return; }
    var r = await home.api('/tasks/' + task.id, 'DELETE');
    if (!r.ok && r.status !== 404) {
      if (r.status !== 401) { home.showToast(home.errorText(r)); }
      return;
    }
    home.showToast('Task deleted.');
    loadBoard(home.currentRoomId());
  }

  function reminderCard(task) {
    var card = el('div', 'reminder-card');
    card.tabIndex = 0;
    card.setAttribute('role', 'checkbox');
    card.setAttribute('aria-checked', 'false');

    var top = el('div', 'reminder-top');
    var bullet = el('span', 'reminder-bullet');
    bullet.setAttribute('aria-hidden', 'true');
    top.appendChild(bullet);
    top.appendChild(el('p', 'reminder-title', task.title));
    if (home.isAdmin()) {
      var del = el('button', 'reminder-delete');
      del.type = 'button';
      del.setAttribute('aria-label', 'Delete for everyone');
      del.title = 'Delete for everyone (admin)';
      del.appendChild(trashIcon());
      del.addEventListener('click', function (e) {
        e.stopPropagation();                        // do not tick the task
        deleteTask(task);
      });
      top.appendChild(del);
    }
    var remove = el('button', 'reminder-remove', '×');
    remove.type = 'button';
    remove.setAttribute('aria-label', 'Remove from my Home page');
    remove.title = 'Remove from my Home page';
    remove.addEventListener('click', function (e) {
      e.stopPropagation();                        // do not tick the task
      removeTask(task);
    });
    top.appendChild(remove);
    card.appendChild(top);

    var tags = el('div', 'reminder-tags');
    tags.appendChild(typeBadge(task));
    if (task.subject) { tags.appendChild(el('span', 'subject-tag', task.subject)); }
    card.appendChild(tags);

    card.appendChild(el('p', 'reminder-time', timeText(task)));

    applyDone(card, bullet, task, !!task.done);
    card.addEventListener('click', function () { toggleDone(card, bullet, task); });
    card.addEventListener('keydown', function (e) {
      if (e.target === card && (e.key === 'Enter' || e.key === ' ')) {
        e.preventDefault();
        toggleDone(card, bullet, task);
      }
    });
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

  function groupByDay(tasks) {
    var byDay = {};
    tasks.forEach(function (t) {
      var key = manilaDayOf(t.due_at);
      (byDay[key] = byDay[key] || []).push(t);
    });
    return byDay;
  }

  function renderWeek(index, sunday, tasks, today) {
    var board = byId(BOARD_IDS[index]);
    var note = byId('weekNote' + index);
    var range = byId('weekRange' + index);
    if (!board) { return; }
    if (range) { range.textContent = weekRange(sunday); }
    clear(board);

    var byDay = groupByDay(tasks);

    // This week: today onwards, plus any earlier day that still has a task you have not ticked.
    // Other weeks: all seven days.
    var firstDay = 0;
    if (index === 0) {
      firstDay = Math.max(0, Math.round((today - sunday) / DAY_MS));
      for (var d = 0; d < firstDay; d++) {
        var earlier = byDay[ymd(addDays(sunday, d))] || [];
        if (earlier.some(function (t) { return !t.done; })) { firstDay = d; break; }
      }
    }
    var shown = 0;
    var cards = [];
    var showEmpty = false;   // Settings > "Show empty days" (off by default); today always stays
    try { showEmpty = localStorage.getItem('roomsync.showEmptyDays') === '1'; } catch (e) { showEmpty = false; }
    for (var i = firstDay; i < 7; i++) {
      var day = addDays(sunday, i);
      var list = byDay[ymd(day)] || [];
      shown += list.length;
      if (list.length === 0 && !showEmpty && !sameDay(day, today)) { continue; }
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

  /* ---------- earlier weeks ---------- */
  // Weeks that are over stay hidden when everything in them is ticked (or removed). A past week with
  // something unticked stays on the board as OVERDUE. "Show earlier weeks" brings the hidden ones back.
  var MAX_BACK = 26;        // how many weeks back the button will look
  var AUTO_BACK = 4;        // weeks checked automatically for unticked tasks
  var SCAN_BATCH = 8;       // weeks fetched per scan step
  var roomState = { roomId: null, revealed: {}, collapsed: [], nextScan: AUTO_BACK + 1, scanning: false };

  function weekLabelText(k) { return k === 1 ? 'LAST WEEK' : k + ' WEEKS AGO'; }

  function renderPastWeek(k, sunday, tasks) {
    var wrap = el('div', 'earlier-week');
    wrap.dataset.k = String(k);
    var section = el('section', 'week-section');
    var overdue = tasks.some(function (t) { return !t.done; });
    var h = el('h2', 'week-label week-label-muted');
    h.appendChild(el('span', 'week-label-accent-muted', weekLabelText(k)));
    h.appendChild(document.createTextNode(' '));
    h.appendChild(el('span', 'bullet', '•'));
    h.appendChild(document.createTextNode(' ' + weekRange(sunday)));
    if (overdue) { h.appendChild(el('span', 'week-overdue', 'OVERDUE')); }
    section.appendChild(h);

    var board = el('div', 'board board-grid');
    var byDay = groupByDay(tasks);
    var shown = 0;
    for (var i = 0; i < 7; i++) {            // only the days that have tasks
      var day = addDays(sunday, i);
      var list = byDay[ymd(day)] || [];
      if (list.length) { board.appendChild(dayCard(day, list, false)); shown += list.length; }
    }
    if (shown === 0) {
      section.appendChild(el('p', 'empty-week-note', 'Nothing scheduled that week.'));
    } else {
      section.appendChild(board);
    }
    wrap.appendChild(section);
    wrap.appendChild(el('hr', 'section-rule'));

    // Oldest weeks at the top, newest next to "This week".
    var holder = byId('earlierWeeks');
    var before = null;
    Array.prototype.forEach.call(holder.children, function (child) {
      if (before === null && Number(child.dataset.k) < k) { before = child; }
    });
    holder.insertBefore(wrap, before);
    return wrap;
  }

  function sundayBack(k) {
    var today = manilaToday();
    return addDays(addDays(today, -today.getUTCDay()), -7 * k);
  }

  function resetEarlier(keepRevealed) {
    clear(byId('earlierWeeks'));
    roomState.collapsed = [];
    roomState.nextScan = AUTO_BACK + 1;
    if (!keepRevealed) { roomState.revealed = {}; }
    var bar = byId('earlierBar');
    if (bar) { bar.hidden = false; }
  }

  async function showEarlier() {
    var roomId = roomState.roomId;
    if (roomId === null || roomState.scanning) { return; }
    var mine = loadCounter;
    roomState.scanning = true;
    var btn = byId('earlierBtn');
    if (btn) { btn.disabled = true; }

    var next = roomState.collapsed.shift();
    while (!next && roomState.nextScan <= MAX_BACK) {
      var ks = [];
      for (var k = roomState.nextScan; k < roomState.nextScan + SCAN_BATCH && k <= MAX_BACK; k++) { ks.push(k); }
      roomState.nextScan += SCAN_BATCH;
      var results = await Promise.all(ks.map(function (n) {
        return home.api('/rooms/' + roomId + '/tasks?week_start=' + ymd(sundayBack(n)));
      }));
      if (mine !== loadCounter) { roomState.scanning = false; if (btn) { btn.disabled = false; } return; }   // room changed meanwhile
      if (!results.every(function (r) { return r.ok; })) {
        roomState.nextScan -= SCAN_BATCH;
        roomState.scanning = false;
        if (btn) { btn.disabled = false; }
        home.showToast(home.errorText(results.filter(function (r) { return !r.ok; })[0]));
        return;
      }
      results.forEach(function (r, i) {
        if (r.body.length && !roomState.revealed[ks[i]]) { roomState.collapsed.push({ k: ks[i], tasks: r.body }); }
      });
      next = roomState.collapsed.shift();
    }

    roomState.scanning = false;
    if (btn) { btn.disabled = false; }
    if (!next) {
      home.showToast('No earlier tasks.');
      var bar = byId('earlierBar');
      if (bar) { bar.hidden = true; }
      return;
    }
    roomState.revealed[next.k] = true;
    var wrap = renderPastWeek(next.k, sundayBack(next.k), next.tasks);
    if (wrap.scrollIntoView) { wrap.scrollIntoView({ behavior: 'smooth', block: 'center' }); }
  }

  /* ---------- removed tasks ---------- */
  function renderRemoved(tasks) {
    var section = byId('removedSection');
    var list = byId('removedList');
    var count = byId('removedCount');
    if (!section || !list) { return; }
    clear(list);
    if (count) { count.textContent = String(tasks.length); }
    if (tasks.length === 0) { section.hidden = true; list.hidden = true; return; }
    section.hidden = false;
    var open = byId('removedToggle').getAttribute('aria-expanded') === 'true';
    list.hidden = !open;
    tasks.forEach(function (task) {
      var row = el('div', 'removed-row');
      var text = el('div', 'removed-text');
      text.appendChild(el('p', 'removed-title', task.title));
      var meta = el('div', 'removed-meta');
      meta.appendChild(typeBadge(task));
      var when = shortMonthDay(new Date(manilaDayOf(task.due_at) + 'T00:00:00Z')) + ', ' + timeText(task);
      meta.appendChild(el('span', 'subject-tag', (task.subject ? task.subject + ' • ' : '') + when));
      text.appendChild(meta);
      row.appendChild(text);
      var restore = el('button', 'removed-restore', 'Restore');
      restore.type = 'button';
      restore.addEventListener('click', async function () {
        restore.disabled = true;
        var r = await home.api('/tasks/' + task.id + '/hidden', 'DELETE');
        if (!r.ok) {
          restore.disabled = false;
          if (r.status !== 401) { home.showToast(home.errorText(r)); }
          return;
        }
        home.showToast('Task restored to your Home page.');
        loadBoard(home.currentRoomId());
      });
      row.appendChild(restore);
      list.appendChild(row);
    });
  }

  function showMessage(text) {
    for (var i = 0; i < 3; i++) {
      var board = byId(BOARD_IDS[i]);
      var note = byId('weekNote' + i);
      if (board) { clear(board); }
      if (note) { note.textContent = i === 0 ? text : ''; note.hidden = i !== 0; }
    }
    clear(byId('earlierWeeks'));
    var bar = byId('earlierBar');
    if (bar) { bar.hidden = true; }
    var removed = byId('removedSection');
    if (removed) { removed.hidden = true; }
  }

  /* ---------- loading the board ---------- */
  async function loadBoard(roomId) {
    var mine = ++loadCounter;
    if (roomId === null || roomId === undefined) {
      roomState.roomId = null;
      showMessage('Join or create a room to see its tasks.');
      return;
    }
    var sameRoom = roomState.roomId === roomId;
    roomState.roomId = roomId;
    var today = manilaToday();
    var sunday = addDays(today, -today.getUTCDay());

    // This week, next week, the week after, the last few weeks (for overdue tasks), weeks you
    // brought back with "Show earlier weeks", and your removed tasks.
    var pastKs = [];
    for (var k = 1; k <= AUTO_BACK; k++) { pastKs.push(k); }
    if (sameRoom) {
      Object.keys(roomState.revealed).forEach(function (key) {
        if (pastKs.indexOf(Number(key)) === -1) { pastKs.push(Number(key)); }
      });
    }
    var calls = [0, 1, 2].map(function (i) {
      return home.api('/rooms/' + roomId + '/tasks?week_start=' + ymd(addDays(sunday, 7 * i)));
    }).concat(pastKs.map(function (n) {
      return home.api('/rooms/' + roomId + '/tasks?week_start=' + ymd(sundayBack(n)));
    }));
    calls.push(home.api('/rooms/' + roomId + '/tasks/removed'));
    var results = await Promise.all(calls);
    if (mine !== loadCounter) { return; }   // you switched rooms while this loaded
    if (!results.every(function (r) { return r.ok; })) {
      var failed = results.filter(function (r) { return !r.ok; })[0];
      showMessage("Couldn't load tasks.");
      home.showToast(home.errorText(failed));
      return;
    }

    resetEarlier(sameRoom);
    results.slice(0, 3).forEach(function (r, i) { renderWeek(i, addDays(sunday, 7 * i), r.body, today); });
    pastKs.forEach(function (n, i) {
      var tasks = results[3 + i].body;
      if (!tasks.length) { return; }
      var unfinished = tasks.some(function (t) { return !t.done; });
      if (unfinished || roomState.revealed[n]) {
        renderPastWeek(n, sundayBack(n), tasks);
      } else {
        roomState.collapsed.push({ k: n, tasks: tasks });
      }
    });
    roomState.collapsed.sort(function (a, b) { return a.k - b.k; });
    renderRemoved(results[results.length - 1].body);
  }

  document.addEventListener('roomsync:room', function (e) { loadBoard(e.detail.id); });
  if (home.currentRoomId() !== undefined && home.currentRoomId() !== null) {
    loadBoard(home.currentRoomId());   // the room was chosen before this script started
  }

  var earlierBtn = byId('earlierBtn');
  if (earlierBtn) { earlierBtn.addEventListener('click', showEarlier); }
  var removedToggle = byId('removedToggle');
  if (removedToggle) {
    removedToggle.addEventListener('click', function () {
      var list = byId('removedList');
      var open = removedToggle.getAttribute('aria-expanded') !== 'true';
      removedToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (list) { list.hidden = !open; }
    });
  }
})();