/* ============================================================
   ROOMSYNC — task_detail.js
   A small pop-up with everything about one task: title, type, subject, due time, who added it,
   "Edited by <admin>" and the note. An admin also gets an Edit button (it opens the New TODO form).
   window.RoomSyncTaskDetail.open(task, { canEdit: true|false })
   Used by Home (the "i" button on a card) and Calendar (click a task).
   All user text is written with textContent (never innerHTML).
   ============================================================ */
(function () {
  'use strict';

  var MANILA_MS = 8 * 60 * 60 * 1000;
  var DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  var MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  var KNOWN_TYPES = ['exam', 'quiz', 'case-study', 'activity', 'seatwork', 'assignment'];

  var overlay = null;
  var body = null;
  var closeBtn = null;

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) { node.className = cls; }
    if (text !== undefined) { node.textContent = text; }
    return node;
  }

  function dateText(iso) {
    var m = new Date(new Date(iso).getTime() + MANILA_MS);
    return DAYS[m.getUTCDay()] + ', ' + MONTHS[m.getUTCMonth()] + ' ' + m.getUTCDate();
  }

  function dueText(task) {
    if (task.all_day) { return dateText(task.due_at) + ' · All day'; }
    var m = new Date(new Date(task.due_at).getTime() + MANILA_MS);
    var h = m.getUTCHours();
    var min = String(m.getUTCMinutes()).padStart(2, '0');
    var suffix = h >= 12 ? 'PM' : 'AM';
    return dateText(task.due_at) + ' · ' + (h % 12 || 12) + ':' + min + ' ' + suffix;
  }

  function close() {
    if (overlay) { overlay.hidden = true; }
  }

  function build() {
    overlay = el('div', 'todo-modal-overlay');
    overlay.hidden = true;
    var card = el('div', 'todo-modal abt-form-card task-detail');
    card.setAttribute('role', 'dialog');
    card.setAttribute('aria-modal', 'true');
    card.setAttribute('aria-label', 'Task details');
    body = el('div', 'task-detail-body');
    card.appendChild(body);
    overlay.appendChild(card);
    document.body.appendChild(overlay);
    overlay.addEventListener('click', function (e) { if (e.target === overlay) { close(); } });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && overlay && !overlay.hidden) { close(); }
    });
  }

  function row(label, value) {
    var r = el('div', 'task-detail-row');
    r.appendChild(el('span', 'task-detail-label', label));
    r.appendChild(el('span', 'task-detail-value', value));
    return r;
  }

  function myId() {
    var cfg = window.ROOMSYNC || {};
    try { return JSON.parse(localStorage.getItem(cfg.USER_KEY || 'roomsync_user') || 'null').id; } catch (e) { return null; }
  }
  function prettySize(n) {
    if (n < 1024) { return n + ' B'; }
    if (n < 1024 * 1024) { return Math.max(1, Math.round(n / 1024)) + ' KB'; }
    return (n / (1024 * 1024)).toFixed(1) + ' MB';
  }

  // Link and unlink notes. Each change is its own request; whatever succeeded is what the card shows afterwards.
  async function applyNotes(task, picked) {
    var home = window.RoomSyncHome;
    var before = (task.attachments || []).map(function (a) { return a.file_id; });
    var after = picked.map(function (f) { return f.id; });
    var list = (task.attachments || []).slice();
    var failed = null;
    for (var i = 0; i < before.length && !failed; i++) {
      if (after.indexOf(before[i]) === -1) {
        var d = await home.api('/tasks/' + task.id + '/attachments/' + before[i], 'DELETE');
        if (d.ok) { list = list.filter(function (a) { return a.file_id !== before[i]; }); } else { failed = d; }
      }
    }
    for (var j = 0; j < picked.length && !failed; j++) {
      if (before.indexOf(picked[j].id) === -1) {
        var r = await home.api('/tasks/' + task.id + '/attachments/' + picked[j].id, 'PUT');
        if (r.ok) { list = r.body.attachments; } else { failed = r; }
      }
    }
    task.attachments = list;
    if (failed && failed.status !== 401) { home.showToast(home.errorText(failed)); }
  }

  function notesSection(task, canAttach, rerender) {
    var list = task.attachments || [];
    if (!list.length && !canAttach) { return null; }
    var box = el('div', 'task-detail-notes');
    box.appendChild(el('span', 'task-detail-label', 'Attached notes'));
    list.forEach(function (a) {
      var item = el('div', 'task-detail-attached');
      var open = el('button', 'task-detail-attached-open');
      open.type = 'button';
      open.title = 'Click to download';
      open.appendChild(el('span', 'task-detail-attached-name', a.name));
      var sizeEl = el('span', 'task-detail-attached-size', prettySize(a.size) + ' \u00b7 Download');
      open.appendChild(sizeEl);
      open.addEventListener('click', async function () {
        if (!window.RoomSyncAttach || open.classList.contains('is-busy')) { return; }
        open.classList.add('is-busy');
        sizeEl.textContent = 'Downloading...';
        try { await Promise.all([window.RoomSyncAttach.download(a.file_id, a.name), new Promise(function (r) { setTimeout(r, 500); })]); }
        finally { open.classList.remove('is-busy'); sizeEl.textContent = prettySize(a.size) + ' \u00b7 Download'; }
      });
      item.appendChild(open);
      if (canAttach) {
        var x = el('button', 'todo-attached-x', '\u00d7');
        x.type = 'button';
        x.setAttribute('aria-label', 'Remove ' + a.name);
        x.addEventListener('click', async function () {
          var keep = list.filter(function (b) { return b.file_id !== a.file_id; })
                         .map(function (b) { return { id: b.file_id, name: b.name, size: b.size }; });
          await applyNotes(task, keep);
          rerender();
        });
        item.appendChild(x);
      }
      box.appendChild(item);
    });
    if (canAttach && window.RoomSyncAttach) {
      var more = el('button', 'todo-link-btn', list.length ? '+ Attach more notes' : '+ Attach notes');
      more.type = 'button';
      more.addEventListener('click', async function () {
        var picked = await window.RoomSyncAttach.pickFiles({
          roomId: task.room_id, max: 5,
          selected: list.map(function (b) { return b.file_id; })
        });
        if (!picked) { return; }
        await applyNotes(task, picked);
        rerender();
      });
      box.appendChild(more);
    }
    return box;
  }

  function open(task, opts) {
    if (!task) { return; }
    if (!overlay) { build(); }
    opts = opts || {};
    body.textContent = '';

    var head = el('div', 'task-detail-head');
    head.appendChild(el('h2', 'abt-form-title task-detail-title', task.title));
    closeBtn = el('button', 'todo-modal-close', '×');
    closeBtn.type = 'button';
    closeBtn.setAttribute('aria-label', 'Close');
    closeBtn.addEventListener('click', close);
    head.appendChild(closeBtn);
    body.appendChild(head);

    var tags = el('div', 'reminder-tags task-detail-tags');
    var known = KNOWN_TYPES.indexOf(task.type) !== -1;
    tags.appendChild(el('span', 'type-badge ' + (known ? 'type-' + task.type : 'type-custom'),
                        task.type.replace(/-/g, ' ').toUpperCase()));
    if (task.subject) { tags.appendChild(el('span', 'subject-tag', task.subject)); }
    body.appendChild(tags);

    body.appendChild(row('Due', dueText(task)));
    if (task.created_by_name) { body.appendChild(row('Added by', task.created_by_name)); }
    if (task.edited_by_name) {
      body.appendChild(row('Edited by', task.edited_by_name + (task.edited_at ? ' · ' + dateText(task.edited_at) : '')));
    }

    var noteBox = el('div', 'task-detail-note');
    noteBox.appendChild(el('span', 'task-detail-label', 'Note'));
    noteBox.appendChild(el('p', task.note ? 'task-detail-note-text' : 'task-detail-note-empty',
                           task.note || 'No note on this task.'));
    body.appendChild(noteBox);

    var canAttach = (opts.canEdit || task.created_by === myId()) && task.status !== 'rejected';
    var notes = notesSection(task, canAttach, function () { open(task, opts); });
    if (notes) { body.appendChild(notes); }

    var actions = el('div', 'abt-form-actions');
    if (opts.canEdit && window.RoomSyncNewTodo) {
      var edit = el('button', 'abt-btn-submit', 'Edit');
      edit.type = 'button';
      edit.addEventListener('click', function () {
        close();
        window.RoomSyncNewTodo.openEdit(task, function () {
          document.dispatchEvent(new CustomEvent('roomsync:rooms-changed'));   // every page reloads its list
        });
      });
      actions.appendChild(edit);
    }
    var done = el('button', 'abt-btn-reset', 'Close');
    done.type = 'button';
    done.addEventListener('click', close);
    actions.appendChild(done);
    body.appendChild(actions);

    overlay.hidden = false;
    closeBtn.focus();
  }

  window.RoomSyncTaskDetail = { open: open };
})();
