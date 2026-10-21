/* ============================================================
   ROOMSYNC — search.js
   Mobile search: the magnifier button opens a full-screen sheet that searches
   the current room's approved tasks (title, subject, type). Results can be ticked off.
   Uses GET /rooms/{id}/tasks/search. All user text is written with textContent.
   ============================================================ */
(function () {
  'use strict';

  var Home = window.RoomSyncHome;
  if (!Home) { return; }

  // Small helpers of our own, so this file works on every page (task_ui.js is not on all of them).
  // Times run in Manila (UTC+8), same as the server.
  var MANILA_MS = 8 * 60 * 60 * 1000;
  var MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  var DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  var KNOWN_TYPES = ['exam', 'quiz', 'case-study', 'activity', 'seatwork', 'assignment'];
  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) { node.className = className; }
    if (text !== undefined) { node.textContent = text; }
    return node;
  }
  function clear(node) { while (node.firstChild) { node.removeChild(node.firstChild); } }

  var TYPES = [
    ['', 'All'], ['exam', 'Exam'], ['quiz', 'Quiz'], ['case-study', 'Case Study'],
    ['activity', 'Activity'], ['seatwork', 'Seatwork'], ['assignment', 'Assignment']
  ];
  var sheet, input, list, status, pills, clearBtn;
  var activeType = '';
  var timer = null;
  var ticket = 0;          // only the newest request may draw (guards against slow, stale replies)

  function dueText(task) {
    var m = new Date(new Date(task.due_at).getTime() + MANILA_MS);
    var when = DAYS[m.getUTCDay()] + ', ' + MONTHS[m.getUTCMonth()] + ' ' + m.getUTCDate() + ' \u00b7 ';
    if (task.all_day) { return when + 'All day'; }
    var h = m.getUTCHours(), min = m.getUTCMinutes();
    var hh = h % 12 === 0 ? 12 : h % 12;
    return when + hh + ':' + (min < 10 ? '0' : '') + min + (h >= 12 ? ' PM' : ' AM');
  }

  function setStatus(text) {
    status.textContent = text;
    status.hidden = !text;
  }

  function row(task) {
    var r = el('div', 'srch-row');
    r.tabIndex = 0;
    r.setAttribute('role', 'checkbox');
    var check = el('span', 'srch-check');
    check.setAttribute('aria-hidden', 'true');
    r.appendChild(check);
    var body = el('div', 'srch-body');
    body.appendChild(el('p', 'srch-title', task.title));
    var meta = el('div', 'srch-meta');
    meta.appendChild(el('span', 'type-badge ' + (KNOWN_TYPES.indexOf(task.type) !== -1 ? 'type-' + task.type : 'type-custom'),
                        task.type.replace(/-/g, ' ').toUpperCase()));
    if (task.subject) { meta.appendChild(el('span', 'subject-tag', task.subject)); }
    body.appendChild(meta);
    body.appendChild(el('p', 'srch-due', dueText(task)));
    r.appendChild(body);

    function paint() {
      r.classList.toggle('is-complete', !!task.done);
      r.setAttribute('aria-checked', task.done ? 'true' : 'false');
    }
    async function toggle() {
      if (r.dataset.busy) { return; }
      var want = !task.done;
      task.done = want; paint();                     // show it straight away, undo if the server says no
      r.dataset.busy = '1';
      var res = await Home.api('/tasks/' + task.id + '/done', want ? 'PUT' : 'DELETE');
      delete r.dataset.busy;
      if (res.ok) {
        document.dispatchEvent(new CustomEvent('roomsync:rooms-changed'));   // boards behind the sheet refresh
        return;
      }
      task.done = !want; paint();
      if (res.status !== 401) { Home.showToast(Home.errorText(res)); }
    }
    paint();
    r.addEventListener('click', toggle);
    r.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); }
    });
    return r;
  }

  async function run() {
    var text = input.value.trim();
    var q = text || activeType;                      // a type pill alone lists every task of that type
    clearBtn.hidden = !input.value;
    var mine = ++ticket;
    clear(list);
    if (!q) { setStatus('Search your room’s tasks by title, subject or type.'); return; }
    var roomId = Home.currentRoomId();
    if (!roomId) { setStatus('Pick a room first.'); return; }
    setStatus('Searching…');
    var path = '/rooms/' + roomId + '/tasks/search?q=' + encodeURIComponent(q) + (activeType ? '&type=' + encodeURIComponent(activeType) : '');
    var res = await Home.api(path, 'GET');
    if (mine !== ticket) { return; }
    if (!res.ok) { if (res.status !== 401) { setStatus(Home.errorText(res)); } return; }
    var tasks = res.body || [];
    if (!tasks.length) { setStatus('No tasks found.'); return; }
    setStatus('');
    tasks.forEach(function (t) { list.appendChild(row(t)); });
  }

  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(run, 250);
  }

  function build() {
    sheet = el('div', 'srch-sheet');
    sheet.setAttribute('role', 'dialog');
    sheet.setAttribute('aria-modal', 'true');
    sheet.setAttribute('aria-label', 'Search tasks');
    sheet.hidden = true;

    var bar = el('div', 'srch-bar');
    var back = el('button', 'srch-back', '‹');
    back.type = 'button';
    back.setAttribute('aria-label', 'Close search');
    back.addEventListener('click', close);
    bar.appendChild(back);
    var field = el('div', 'srch-field');
    input = el('input', 'srch-input');
    input.type = 'search';
    input.maxLength = 50;
    input.placeholder = 'Search tasks';
    input.setAttribute('aria-label', 'Search tasks');
    input.autocomplete = 'off';
    input.addEventListener('input', schedule);
    field.appendChild(input);
    clearBtn = el('button', 'srch-clear', '×');
    clearBtn.type = 'button';
    clearBtn.hidden = true;
    clearBtn.setAttribute('aria-label', 'Clear');
    clearBtn.addEventListener('click', function () { input.value = ''; input.focus(); run(); });
    field.appendChild(clearBtn);
    bar.appendChild(field);
    sheet.appendChild(bar);

    pills = el('div', 'srch-pills');
    TYPES.forEach(function (t) {
      var b = el('button', 'srch-pill' + (t[0] === '' ? ' is-active' : ''), t[1]);
      b.type = 'button';
      b.addEventListener('click', function () {
        activeType = t[0];
        Array.prototype.forEach.call(pills.children, function (c) { c.classList.toggle('is-active', c === b); });
        clearTimeout(timer);
        run();
      });
      pills.appendChild(b);
    });
    sheet.appendChild(pills);

    status = el('p', 'srch-status');
    sheet.appendChild(status);
    list = el('div', 'srch-list');
    sheet.appendChild(list);
    document.body.appendChild(sheet);

    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !sheet.hidden) { close(); } });
    document.addEventListener('roomsync:room', function () { if (!sheet.hidden) { run(); } });
  }

  function open() {
    if (!sheet) { build(); }
    sheet.hidden = false;
    document.body.classList.add('srch-lock');
    run();
    input.focus();
  }

  function close() {
    if (!sheet) { return; }
    clearTimeout(timer);
    ticket++;
    sheet.hidden = true;
    document.body.classList.remove('srch-lock');
  }

  Array.prototype.forEach.call(document.querySelectorAll('.fab-round[aria-label="Search"]'), function (b) {
    b.addEventListener('click', open);
  });
})();