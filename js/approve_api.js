/* ============================================================
   ROOMSYNC — approve_api.js
   Approve page, wired to the API (admins only):
   - the room's pending tasks, oldest first, with Approve / Reject
   - filter by task type, sort by due date or name
   - Edit: an admin can fix a pending task (title, type, date...) before deciding
   - History: the most recent decisions
   - Members see MY SUBMISSIONS instead: their own pending and rejected tasks, with Edit and Delete
   for the pending ones
   The server decides who may approve what (an admin can't decide their own
   task while another admin exists); its message is shown if a decision is refused.
   All user text is written with textContent (never innerHTML).
   Needs: js/sidebar_rooms.js (window.RoomSyncHome) and js/task_ui.js loaded first.
   ============================================================ */
(function () {
  'use strict';

  var home = window.RoomSyncHome;
  var T = window.RoomSyncTasks;
  var list = document.getElementById('apprList');
  if (!home || !T || !list) { return; }

  var NS = 'http://www.w3.org/2000/svg';
  var HISTORY_LIMIT = 50;

  var pending = [];        // pending tasks from the server (oldest first)
  var filter = 'all';
  var sortBy = 'date-added';
  var loadCounter = 0;     // lets us ignore answers that arrive after you switched room
  var myId = null;
  try { myId = (JSON.parse(localStorage.getItem(window.ROOMSYNC.USER_KEY) || 'null') || {}).id; } catch (e) { myId = null; }

  function byId(id) { return document.getElementById(id); }

  function icon(pathData) {
    var svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '3');
    var path = document.createElementNS(NS, 'path');
    path.setAttribute('d', pathData);
    path.setAttribute('stroke-linecap', 'round');
    path.setAttribute('stroke-linejoin', 'round');
    svg.appendChild(path);
    return svg;
  }

  function dueText(task) {
    var day = new Date(T.manilaDayOf(task.due_at) + 'T00:00:00Z');
    var text = T.shortMonthDay(day);
    return task.all_day ? text : text + ', ' + T.timeText(task);
  }

  function typeLabel(type) { return type.replace(/-/g, ' ').toUpperCase(); }

  function setMessage(text) {
    var empty = byId('apprEmpty');
    if (!empty) { return; }
    empty.textContent = text || '';
    empty.hidden = !text;
  }

  /* ---------- pending cards ---------- */
  function card(task) {
    var article = T.el('article', 'appr-card');
    article.dataset.id = String(task.id);
    article.dataset.type = task.type;

    var top = T.el('div', 'appr-card-top');
    var text = T.el('div', 'appr-card-text');
    text.appendChild(T.el('h3', 'appr-card-title', task.title));
    var who = task.created_by === myId ? 'you' : task.created_by_name;
    var meta = 'submitted by ' + who + ' • Due ' + dueText(task) + (task.subject ? ' • ' + task.subject : '');
    text.appendChild(T.el('p', 'appr-card-meta', meta));
    top.appendChild(text);
    top.appendChild(T.el('span', 'appr-badge ' + (T.isKnownType(task.type) ? 'appr-badge-' + task.type : 'appr-badge-custom'),
                         typeLabel(task.type)));
    article.appendChild(top);

    var actions = T.el('div', 'appr-card-actions');
    var approve = T.el('button', 'appr-btn-approve');
    approve.type = 'button';
    approve.appendChild(icon('M20 6 9 17l-5-5'));
    approve.appendChild(document.createTextNode('Approve'));
    var reject = T.el('button', 'appr-btn-reject');
    reject.type = 'button';
    reject.appendChild(icon('M18 6L6 18M6 6l12 12'));
    reject.appendChild(document.createTextNode('Reject'));
    var edit = T.el('button', 'appr-btn-edit', 'Edit');
    edit.type = 'button';
    edit.addEventListener('click', function () { openEdit(task); });
    approve.addEventListener('click', function () { decide(task, 'approve', article); });
    reject.addEventListener('click', function () { decide(task, 'reject', article); });
    actions.appendChild(approve);
    actions.appendChild(reject);
    actions.appendChild(edit);
    article.appendChild(actions);
    return article;
  }

  // The shared form (js/new_todo.js) edits the task; onSaved reloads whatever list we are showing.
  function openEdit(task) {
    if (window.RoomSyncNewTodo) { window.RoomSyncNewTodo.openEdit(task, load); }
  }

  /* ---------- my submissions (members) ---------- */
  function mineCard(task) {
    var article = T.el('article', 'appr-card');
    var top = T.el('div', 'appr-card-top');
    var text = T.el('div', 'appr-card-text');
    text.appendChild(T.el('h3', 'appr-card-title', task.title));
    var meta = 'Due ' + dueText(task) + (task.subject ? ' \u2022 ' + task.subject : '');
    if (task.status === 'rejected' && task.decided_by_name) { meta += ' \u2022 rejected by ' + task.decided_by_name; }
    text.appendChild(T.el('p', 'appr-card-meta', meta));
    top.appendChild(text);
    var pill = T.el('span', 'history-status ' + (task.status === 'pending' ? 'history-status-pending' : 'history-status-rejected'),
                    task.status.toUpperCase());
    var right = T.el('div', 'appr-card-right');
    right.appendChild(pill);
    right.appendChild(T.el('span', 'appr-badge ' + (T.isKnownType(task.type) ? 'appr-badge-' + task.type : 'appr-badge-custom'),
                           typeLabel(task.type)));
    top.appendChild(right);
    article.appendChild(top);

    if (task.status === 'pending') {
      var actions = T.el('div', 'appr-card-actions');
      var edit = T.el('button', 'appr-btn-edit', 'Edit');
      edit.type = 'button';
      edit.addEventListener('click', function () { openEdit(task); });
      var del = T.el('button', 'appr-btn-delete', 'Delete');
      del.type = 'button';
      del.addEventListener('click', async function () {
        if (!window.confirm('Delete "' + task.title + '"? It will not go to the room.')) { return; }
        del.disabled = true;
        var r = await home.api('/tasks/' + task.id, 'DELETE');
        if (!r.ok && r.status !== 404) {
          del.disabled = false;
          home.showToast(home.errorText(r));
          return;
        }
        home.showToast('Submission deleted.');
        load();
        document.dispatchEvent(new CustomEvent('roomsync:rooms-changed'));   // the pending count changed
      });
      actions.appendChild(edit);
      actions.appendChild(del);
      article.appendChild(actions);
    }
    return article;
  }

  function showMineParts(show) {
    ['apprMineHead', 'apprMineList'].forEach(function (id) {
      var node = byId(id);
      if (node) { node.hidden = !show; }
    });
    var empty = byId('apprMineEmpty');
    if (empty && !show) { empty.hidden = true; }
  }

  async function loadMine(roomId, token) {
    var r = await home.api('/rooms/' + roomId + '/tasks/mine?limit=100');
    if (token !== loadCounter) { return; }
    var box = byId('apprMineList');
    if (!box) { return; }
    T.clear(box);
    if (!r.ok) { showMineParts(false); home.showToast(home.errorText(r)); return; }
    var open = r.body.filter(function (t) { return t.status === 'pending' || t.status === 'rejected'; });
    showMineParts(true);
    open.forEach(function (t) { box.appendChild(mineCard(t)); });
    var empty = byId('apprMineEmpty');
    if (empty) { empty.hidden = open.length !== 0; }
  }

  function sorted(tasks) {
    var copy = tasks.slice();
    if (sortBy === 'date-modified') {
      copy.sort(function (a, b) { return new Date(a.due_at) - new Date(b.due_at); });
    } else if (sortBy === 'az') {
      copy.sort(function (a, b) { return a.title.localeCompare(b.title); });
    } else if (sortBy === 'za') {
      copy.sort(function (a, b) { return b.title.localeCompare(a.title); });
    }   // 'date-added': the server already sends oldest first
    return copy;
  }

  function renderPending() {
    T.clear(list);
    var visible = sorted(pending).filter(function (t) { return filter === 'all' || t.type === filter; });
    visible.forEach(function (t) { list.appendChild(card(t)); });
    if (pending.length === 0) {
      setMessage('Nothing left to review — all caught up.');
    } else if (visible.length === 0) {
      setMessage('No pending tasks of this type.');
    } else {
      setMessage('');
    }
  }

  async function decide(task, verb, article) {
    var buttons = article.querySelectorAll('button');
    buttons.forEach(function (b) { b.disabled = true; });
    var r = await home.api('/tasks/' + task.id + '/' + verb, 'POST');
    if (!r.ok) {
      buttons.forEach(function (b) { b.disabled = false; });
      home.showToast(home.errorText(r));
      if (r.status === 409 || r.status === 404) { load(); }   // someone else already decided it
      return;
    }
    article.classList.add('appr-card-leaving');
    pending = pending.filter(function (t) { return t.id !== task.id; });
    setTimeout(function () { article.remove(); renderPending(); }, 220);
    home.showToast(verb === 'approve' ? 'Approved: it is now on the board and calendar.' : 'Rejected.');
    loadHistory(home.currentRoomId());
    document.dispatchEvent(new CustomEvent('roomsync:rooms-changed'));   // refresh the pending counts in the sidebar
  }

  /* ---------- history ---------- */
  function historyRow(task, last) {
    var row = T.el('div', 'profile-history-row' + (last ? ' profile-history-row-last' : ''));
    function cell(label, value) {
      var s = T.el('span', '', value);
      s.setAttribute('data-label', label);
      return s;
    }
    row.appendChild(cell('Submitted by', task.created_by_name));
    row.appendChild(cell('Decided by', task.decided_by_name || ''));
    row.appendChild(cell('Activity', task.title));
    var status = T.el('span');
    status.setAttribute('data-label', 'Status');
    var approved = task.status === 'approved';
    status.appendChild(T.el('span', 'history-status ' + (approved ? 'history-status-approved' : 'history-status-rejected'),
                            approved ? 'APPROVED' : 'REJECTED'));
    row.appendChild(status);
    return row;
  }

  function renderHistory(tasks) {
    var table = byId('apprHistoryTable');
    var note = byId('apprHistoryEmpty');
    if (!table) { return; }
    table.querySelectorAll('.profile-history-row').forEach(function (r) { r.remove(); });
    tasks.forEach(function (t, i) { table.appendChild(historyRow(t, i === tasks.length - 1)); });
    table.hidden = tasks.length === 0;
    if (note) { note.hidden = tasks.length !== 0; }
  }

  async function loadHistory(roomId) {
    if (roomId === null || roomId === undefined) { return; }
    var r = await home.api('/rooms/' + roomId + '/approvals/history?limit=' + HISTORY_LIMIT);
    if (roomId !== home.currentRoomId()) { return; }
    if (r.ok) { renderHistory(r.body); }
  }

  /* ---------- loading ---------- */
  function showAdminParts(show) {
    ['apprFilters', 'apprHistoryHead', 'apprHistoryTable', 'apprHistoryEmpty'].forEach(function (id) {
      var node = byId(id);
      if (node) { node.hidden = !show; }
    });
    list.hidden = !show;
  }

  async function load() {
    var mine = ++loadCounter;
    var roomId = home.currentRoomId();
    if (roomId === null || roomId === undefined) {
      pending = [];
      T.clear(list);
      showAdminParts(false);
      showMineParts(false);
      setMessage('Join or create a room to review its tasks.');
      return;
    }
    var r = await home.api('/rooms/' + roomId + '/approvals');
    if (mine !== loadCounter) { return; }   // you switched rooms while this loaded
    if (r.status === 403) {
      pending = [];
      T.clear(list);
      showAdminParts(false);
      setMessage('Only room admins can review submissions. An admin will approve or reject your tasks.');
      loadMine(roomId, mine);
      return;
    }
    if (!r.ok) {
      showAdminParts(false);
      setMessage("Couldn't load the pending tasks.");
      home.showToast(home.errorText(r));
      return;
    }
    showAdminParts(true);
    showMineParts(false);
    pending = r.body;
    renderPending();
    loadHistory(roomId);
  }

  /* ---------- filter + sort controls ---------- */
  var pills = document.querySelectorAll('.notes-filter-pill');
  pills.forEach(function (pill) {
    pill.addEventListener('click', function () {
      filter = pill.dataset.filter;
      pills.forEach(function (p) { p.classList.toggle('notes-filter-active', p === pill); });
      renderPending();
    });
  });
  var sortSelect = byId('approveSortSelect');
  if (sortSelect) {
    sortSelect.addEventListener('change', function () { sortBy = sortSelect.value; renderPending(); });
  }

  document.addEventListener('roomsync:room', load);
  if (home.currentRoomId() !== null && home.currentRoomId() !== undefined) { load(); }
})();