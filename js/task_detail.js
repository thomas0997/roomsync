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
