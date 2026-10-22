/* ============================================================
   ROOMSYNC — calendar_api.js
   Calendar page, wired to the API:
   - month grid of the selected room's APPROVED tasks (the server decides that)
   - previous / next month buttons
   - "+N more" when a day has many tasks
   - an Exams list for the month underneath
   Months run in Manila time (UTC+8), same as the server.
   All user text is written with textContent (never innerHTML).
   Needs: js/sidebar_rooms.js (window.RoomSyncHome) and js/task_ui.js loaded first.
   ============================================================ */
(function () {
  'use strict';

  var home = window.RoomSyncHome;
  var T = window.RoomSyncTasks;
  var grid = document.getElementById('calGrid');
  if (!home || !T || !grid) { return; }

  var MAX_CHIPS = 3;      // a day with more than this shows two tasks and "+N more"
  var shown = null;       // { year, month } month being shown (month is 0 to 11)
  var lastTasks = [];     // the month on screen, so a tick can redraw without asking the server again
  var lastRemoved = {};   // ids of tasks I removed from my Home board (hidden from the Exams list)
  var loadCounter = 0;    // lets us ignore answers that arrive after you switched room or month

  function byId(id) { return document.getElementById(id); }

  function startMonth() {
    var today = T.manilaToday();
    return { year: today.getUTCFullYear(), month: today.getUTCMonth() };
  }

  function monthParam(m) {
    return m.year + '-' + (m.month < 9 ? '0' : '') + (m.month + 1);
  }

  function chipClass(task) {
    return 'cal-chip ' + (T.isKnownType(task.type) ? 'cal-chip-' + task.type : 'cal-chip-custom');
  }

  function chip(task) {
    var c = T.el('span', chipClass(task) + (task.done ? ' cal-chip-done' : ''), task.title);
    var tip = task.title + (task.subject ? ' · ' + task.subject : '') + ' · ' + T.timeText(task);
    c.title = tip;
    return c;
  }

  function dayCell(day, tasks, today) {
    var hasExam = tasks.some(function (t) { return t.type === 'exam'; });
    var cell = T.el('div', 'cal-cell' + (hasExam ? ' cal-cell-exam' : ''));
    cell.appendChild(T.el('span', 'cal-daynum' + (T.sameDay(day, today) ? ' cal-daynum-today' : ''), String(day.getUTCDate())));
    if (tasks.length <= MAX_CHIPS) {
      tasks.forEach(function (t) { cell.appendChild(chip(t)); });
      return cell;
    }
    var visible = tasks.slice(0, MAX_CHIPS - 1);
    var hidden = tasks.slice(MAX_CHIPS - 1);
    visible.forEach(function (t) { cell.appendChild(chip(t)); });
    cell.classList.add('cal-cell-has-more');
    var more = T.el('button', 'cal-chip cal-chip-custom cal-chip-more', '+' + hidden.length + ' More');
    more.type = 'button';
    var pop = T.el('div', 'cal-more-popover');
    pop.hidden = true;
    // On phones the popover is a bottom sheet: a date heading, then each task with its time.
    pop.appendChild(T.el('div', 'cal-more-title', T.DAYS[day.getUTCDay()] + ', ' + T.shortMonthDay(day)));
    hidden.forEach(function (t) {
      var c = chip(t);
      c.appendChild(T.el('span', 'cal-more-meta', (t.subject ? t.subject + ' · ' : '') + T.timeText(t)));
      pop.appendChild(c);
    });
    more.addEventListener('click', function (e) {
      e.stopPropagation();
      var wasOpen = !pop.hidden;
      document.querySelectorAll('.cal-more-popover').forEach(function (p) { p.hidden = true; });
      pop.hidden = wasOpen;
    });
    cell.appendChild(more);
    cell.appendChild(pop);
    return cell;
  }

  function setNote(text) {
    var note = byId('calEmpty');
    if (!note) { return; }
    note.textContent = text || '';
    note.hidden = !text;
  }

  function renderMonth(m, tasks, removedIds) {
    lastTasks = tasks;
    lastRemoved = removedIds || {};
    var today = T.manilaToday();
    var first = new Date(Date.UTC(m.year, m.month, 1));
    var daysInMonth = new Date(Date.UTC(m.year, m.month + 1, 0)).getUTCDate();
    var byDay = {};
    tasks.forEach(function (t) {
      var key = T.manilaDayOf(t.due_at);
      (byDay[key] = byDay[key] || []).push(t);
    });

    T.clear(grid);
    var lead = first.getUTCDay();
    for (var i = 0; i < lead; i++) { grid.appendChild(T.el('div', 'cal-cell cal-cell-empty')); }
    for (var d = 1; d <= daysInMonth; d++) {
      var day = new Date(Date.UTC(m.year, m.month, d));
      grid.appendChild(dayCell(day, byDay[T.ymd(day)] || [], today));
    }
    var trail = (7 - ((lead + daysInMonth) % 7)) % 7;
    for (var j = 0; j < trail; j++) { grid.appendChild(T.el('div', 'cal-cell cal-cell-empty')); }

    setNote(tasks.length === 0 ? 'No approved tasks this month.' : '');
    renderExams(m, byDay, today);
  }

  // Ticking or removing on the Exams list: tick redraws from what we have, remove asks the server again.
  var actions = {
    api: home.api,
    toast: home.showToast,
    errorText: home.errorText,
    onChanged: function () { renderMonth(shown, lastTasks, lastRemoved); },
    onRemoved: function () { load(); },
    onStale: function () { load(); },
    canDelete: function () { return home.isAdmin(); },
    onDeleted: function () { load(); }
  };

  function renderExams(m, byDay, today) {
    var section = byId('calExams');
    var board = byId('calExamsBoard');
    var range = byId('calExamsRange');
    if (!section || !board) { return; }
    T.clear(board);
    var keys = Object.keys(byDay).sort();
    var count = 0;
    keys.forEach(function (key) {
      var exams = byDay[key].filter(function (t) { return t.type === 'exam' && !lastRemoved[t.id]; });
      if (exams.length === 0) { return; }
      count += exams.length;
      var day = new Date(key + 'T00:00:00Z');
      board.appendChild(T.dayCard(day, exams, T.sameDay(day, today), actions));
    });
    if (range) { range.textContent = T.MONTHS[m.month] + ' ' + m.year; }
    section.hidden = count === 0;
  }

  function renderTitle(m) {
    var title = byId('calMonthTitle');
    if (title) { title.textContent = T.MONTHS[m.month] + ' ' + m.year; }
    var now = startMonth();
    var todayBtn = byId('calTodayBtn');   // only shown when you are looking at another month
    if (todayBtn) { todayBtn.hidden = (m.year === now.year && m.month === now.month); }
  }

  function blankGrid(m, text) {
    renderMonth(m, []);
    setNote(text);
  }

  async function load() {
    var mine = ++loadCounter;
    var roomId = home.currentRoomId();
    renderTitle(shown);
    if (roomId === null || roomId === undefined) {
      blankGrid(shown, 'Join or create a room to see its calendar.');
      return;
    }
    var results = await Promise.all([
      home.api('/rooms/' + roomId + '/calendar?month=' + monthParam(shown)),
      home.api('/rooms/' + roomId + '/tasks/removed')
    ]);
    if (mine !== loadCounter) { return; }   // you switched room or month while this loaded
    var r = results[0];
    if (!r.ok || !results[1].ok) {
      r = r.ok ? results[1] : r;
      blankGrid(shown, "Couldn't load this month's tasks.");
      home.showToast(home.errorText(r));
      return;
    }
    var removedIds = {};
    results[1].body.forEach(function (t) { removedIds[t.id] = true; });
    renderMonth(shown, results[0].body, removedIds);
  }

  function goToday() {
    shown = startMonth();
    load();
  }

  function step(delta) {
    var month = shown.month + delta;
    shown = { year: shown.year + Math.floor(month / 12), month: ((month % 12) + 12) % 12 };
    load();
  }

  var prev = byId('calPrevBtn');
  var next = byId('calNextBtn');
  if (prev) { prev.addEventListener('click', function () { step(-1); }); }
  if (next) { next.addEventListener('click', function () { step(1); }); }
  var todayBtn = byId('calTodayBtn');
  if (todayBtn) { todayBtn.addEventListener('click', goToday); }
  var fabToday = document.querySelector('.fab-pill');   // the phone TODAY button
  if (fabToday) { fabToday.addEventListener('click', goToday); }

  shown = startMonth();
  document.addEventListener('roomsync:room', load);
  if (home.currentRoomId() !== null && home.currentRoomId() !== undefined) {
    load();                         // the room was chosen before this script started
  } else {
    renderTitle(shown);
    blankGrid(shown, '');           // an empty month grid while the rooms load
  }
})();