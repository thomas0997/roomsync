/* ============================================================
   ROOMSYNC — task_ui.js
   Small helpers shared by the pages that show tasks (Calendar, Approve):
   the task / day cards can be ticked off and removed when the page passes `actions`.
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

  // `actions` is optional. Without it the card is read-only (Approve page).
  // With it the card can be ticked off and removed from your Home board, like on Home:
  //   { api, toast, errorText, onChanged(), onRemoved(task), onStale(),
  //     canDelete() (true for room admins), onDeleted(task) }
  function applyDone(card, bullet, task, done) {
    task.done = done;
    card.classList.toggle('is-complete', done);
    bullet.classList.toggle('is-complete', done);
    card.setAttribute('aria-checked', done ? 'true' : 'false');
  }

  async function toggleDone(card, bullet, task, actions) {
    if (card.dataset.busy) { return; }
    var want = !task.done;
    applyDone(card, bullet, task, want);          // show it straight away, undo if the server says no
    card.dataset.busy = '1';
    var r = await actions.api('/tasks/' + task.id + '/done', want ? 'PUT' : 'DELETE');
    delete card.dataset.busy;
    if (r.ok) { if (actions.onChanged) { actions.onChanged(); } return; }
    applyDone(card, bullet, task, !want);
    if (r.status === 401) { return; }
    actions.toast(actions.errorText(r));
    if ((r.status === 404 || r.status === 409) && actions.onStale) { actions.onStale(); }
  }

  async function removeTask(task, actions) {
    var r = await actions.api('/tasks/' + task.id + '/hidden', 'PUT');
    if (!r.ok) {
      if (r.status !== 401) { actions.toast(actions.errorText(r)); }
      if ((r.status === 404 || r.status === 409) && actions.onStale) { actions.onStale(); }
      return;
    }
    actions.toast('Removed from your Home page. Restore it under Removed tasks on Home.');
    if (actions.onRemoved) { actions.onRemoved(task); }
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
  async function deleteTask(task, actions) {
    if (!window.confirm('Delete "' + task.title + '" for everyone in the room? This cannot be undone.')) { return; }
    var r = await actions.api('/tasks/' + task.id, 'DELETE');
    if (!r.ok && r.status !== 404) {
      if (r.status !== 401) { actions.toast(actions.errorText(r)); }
      return;
    }
    actions.toast('Task deleted.');
    if (actions.onDeleted) { actions.onDeleted(task); }
  }

  function reminderCard(task, actions) {
    var card = el('div', 'reminder-card');
    var top = el('div', 'reminder-top');
    var bullet = el('span', 'reminder-bullet');
    bullet.setAttribute('aria-hidden', 'true');
    top.appendChild(bullet);
    top.appendChild(el('p', 'reminder-title', task.title));
    if (actions) {
      if (actions.canDelete && actions.canDelete()) {
        var del = el('button', 'reminder-delete');
        del.type = 'button';
        del.setAttribute('aria-label', 'Delete for everyone');
        del.title = 'Delete for everyone (admin)';
        del.appendChild(trashIcon());
        del.addEventListener('click', function (e) {
          e.stopPropagation();                    // do not tick the task
          deleteTask(task, actions);
        });
        top.appendChild(del);
      }
      var remove = el('button', 'reminder-remove', '\u00d7');
      remove.type = 'button';
      remove.setAttribute('aria-label', 'Remove from my Home page');
      remove.title = 'Remove from my Home page';
      remove.addEventListener('click', function (e) {
        e.stopPropagation();                      // do not tick the task
        removeTask(task, actions);
      });
      top.appendChild(remove);
    }
    card.appendChild(top);

    var tags = el('div', 'reminder-tags');
    tags.appendChild(el('span', 'type-badge ' + (isKnownType(task.type) ? 'type-' + task.type : 'type-custom'),
                        task.type.replace(/-/g, ' ').toUpperCase()));
    if (task.subject) { tags.appendChild(el('span', 'subject-tag', task.subject)); }
    card.appendChild(tags);

    card.appendChild(el('p', 'reminder-time', timeText(task)));

    if (actions) {
      card.tabIndex = 0;
      card.setAttribute('role', 'checkbox');
      applyDone(card, bullet, task, !!task.done);
      card.addEventListener('click', function () { toggleDone(card, bullet, task, actions); });
      card.addEventListener('keydown', function (e) {
        if (e.target === card && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault();
          toggleDone(card, bullet, task, actions);
        }
      });
    }
    return card;
  }

  function dayCard(day, tasks, isToday, actions) {
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
    tasks.forEach(function (t) { card.appendChild(reminderCard(t, actions)); });
    return card;
  }

  window.RoomSyncTasks = {
    MONTHS: MONTHS, DAYS: DAYS, MANILA_MS: MANILA_MS, DAY_MS: DAY_MS,
    manilaToday: manilaToday, addDays: addDays, ymd: ymd, sameDay: sameDay,
    shortMonthDay: shortMonthDay, manilaDayOf: manilaDayOf, timeText: timeText,
    isKnownType: isKnownType, el: el, clear: clear, trashIcon: trashIcon, reminderCard: reminderCard, dayCard: dayCard
  };
})();