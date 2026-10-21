/* ============================================================
   ROOMSYNC — task_ui.js
   Small helpers shared by the pages that show tasks (Calendar, Approve):
   Manila dates, and the task / day cards. Exposes window.RoomSyncTasks.
   All user text is written with textContent (never innerHTML).
   Weeks and months run in Manila time (UTC+8, no daylight saving), same as the server.
   ============================================================ */
(function () {
  'use strict';

  var MANILA_MS = 8 * 60 * 60 * 1000;
  var DAY_MS = 24 * 60 * 60 * 1000;
  var MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
                'August', 'September', 'October', 'November', 'December'];
  var DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
  var KNOWN_TYPES = ['exam', 'quiz', 'case-study', 'activity', 'seatwork', 'assignment'];

  // A "calendar day" is a UTC-midnight Date that stands for a Manila day.
  function manilaToday() {
    var m = new Date(Date.now() + MANILA_MS);
    return new Date(Date.UTC(m.getUTCFullYear(), m.getUTCMonth(), m.getUTCDate()));
  }
  function addDays(day, n) { return new Date(day.getTime() + n * DAY_MS); }
  function ymd(day) { return day.toISOString().slice(0, 10); }
  function sameDay(a, b) { return ymd(a) === ymd(b); }
  function shortMonthDay(day) { return MONTHS[day.getUTCMonth()].slice(0, 3) + ' ' + day.getUTCDate(); }

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

  function isKnownType(type) { return KNOWN_TYPES.indexOf(type) !== -1; }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) { node.className = className; }
    if (text !== undefined) { node.textContent = text; }
    return node;
  }

  function clear(node) { while (node.firstChild) { node.removeChild(node.firstChild); } }

  function reminderCard(task) {
    var card = el('div', 'reminder-card');
    var top = el('div', 'reminder-top');
    var bullet = el('span', 'reminder-bullet');
    bullet.setAttribute('aria-hidden', 'true');
    top.appendChild(bullet);
    top.appendChild(el('p', 'reminder-title', task.title));
    card.appendChild(top);

    var tags = el('div', 'reminder-tags');
    tags.appendChild(el('span', 'type-badge ' + (isKnownType(task.type) ? 'type-' + task.type : 'type-custom'),
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

  window.RoomSyncTasks = {
    MONTHS: MONTHS, DAYS: DAYS, MANILA_MS: MANILA_MS, DAY_MS: DAY_MS,
    manilaToday: manilaToday, addDays: addDays, ymd: ymd, sameDay: sameDay,
    shortMonthDay: shortMonthDay, manilaDayOf: manilaDayOf, timeText: timeText,
    isKnownType: isKnownType, el: el, clear: clear, reminderCard: reminderCard, dayCard: dayCard
  };
})();