/* ============================================================
   ROOMSYNC — new_todo.js
   The New TODO form, shared by every page that has the + New TODO button
   (Home, Calendar, Approve, Discussion, Notes, About):
   - sends a real task to the API; a member's task waits for an admin to approve it
   - then asks the page to refresh (the "roomsync:rooms-changed" event reloads the sidebar
     and every page script reloads its data for the room)
   The same form also EDITS a task: window.RoomSyncNewTodo.openEdit(task, onSaved).
   The creator or a room admin can edit a pending task (the server decides).
   The modal itself opens and closes in js/rooms.js. This file fills the room list's choice,
   checks the form and sends it.
   The date and time you type are Manila time (UTC+8), same as the server.
   All user text is written with textContent (never innerHTML).
   Needs: js/sidebar_rooms.js loaded first (it exposes window.RoomSyncHome).
   ============================================================ */
(function () {
  'use strict';

  var home = window.RoomSyncHome;
  var form = document.getElementById('todoModalForm');
  if (!home || !form) { return; }

  var MANILA_MS = 8 * 60 * 60 * 1000;   // Manila is UTC+8, no daylight saving

  function byId(id) { return document.getElementById(id); }

  function manilaTodayText() {
    return new Date(Date.now() + MANILA_MS).toISOString().slice(0, 10);
  }

  var errorBox = byId('todoFormError');
  var titleEl = form.parentNode.querySelector('.abt-form-title');
  var submitBtn = form.querySelector('button[type="submit"]');
  var busy = false;
  var editing = null;   // null = creating; { task, onSaved, date, time } = editing that task

  function showFormError(text) {
    if (!errorBox) { return; }
    errorBox.textContent = text;
    errorBox.hidden = !text;
  }

  function closeModal() {
    var overlay = byId('todoModalOverlay');
    if (overlay) { overlay.hidden = true; }
  }

  // Create mode or edit mode: the heading, the button text and the room list follow.
  function setMode(task, onSaved) {
    editing = task ? { task: task, onSaved: onSaved } : null;
    if (titleEl) { titleEl.textContent = task ? 'Edit TODO' : 'New TODO'; }
    if (submitBtn) { submitBtn.textContent = task ? 'Save' : 'Create'; }
    var select = byId('todoModalRoom');
    if (select) { select.disabled = !!task; }   // a task never moves to another room
  }

  // Opening the form to create: pick the room you are looking at and clear old errors.
  ['newTodoBtnDesktop', 'newTodoBtnTablet', 'newTodoBtnMobile'].forEach(function (id) {
    var btn = byId(id);
    if (!btn) { return; }
    btn.addEventListener('click', function () {
      if (editing) { form.reset(); }
      setMode(null);
      showFormError('');
      byId('todoDate').min = manilaTodayText();   // the date picker greys out days that are over
      var select = byId('todoModalRoom');
      var current = home.currentRoomId();
      if (select && current !== null && current !== undefined) { select.value = String(current); }
    });
  });

  // Opening the form to edit a task. onSaved() runs after a successful save (reload the page's list).
  function openEdit(task, onSaved) {
    form.reset();
    setMode(task, onSaved);
    showFormError('');
    var m = new Date(new Date(task.due_at).getTime() + MANILA_MS);
    var date = m.toISOString().slice(0, 10);
    var time = task.all_day ? '' : m.toISOString().slice(11, 16);
    editing.date = date;
    editing.time = time;
    byId('todoTitle').value = task.title;
    var typeSelect = byId('todoType');
    var hasType = Array.prototype.some.call(typeSelect.options, function (o) { return o.value === task.type; });
    if (!hasType) {   // a custom type name: add it so the form can show it
      var opt = document.createElement('option');
      opt.value = task.type;
      opt.textContent = task.type;
      typeSelect.appendChild(opt);
    }
    typeSelect.value = task.type;
    byId('todoSubject').value = task.subject || '';
    byId('todoDate').min = '';          // an old date is fine as long as you do not change it
    byId('todoDate').value = date;
    byId('todoTime').value = time;
    var select = byId('todoModalRoom');
    if (select) { select.value = String(task.room_id); }
    byId('todoModalOverlay').hidden = false;
  }
  window.RoomSyncNewTodo = { openEdit: openEdit };   // rooms.js sees this and does not fake the submit

  async function saveEdit(title, type, subject, date, time) {
    var task = editing.task;
    var payload = {};
    if (title !== task.title) { payload.title = title; }
    if (type !== task.type) { payload.type = type; }
    if (subject !== (task.subject || '')) { payload.subject = subject || null; }
    if (date !== editing.date || time !== editing.time) {
      var dueAt = date + 'T' + (time ? time : '23:59') + ':00+08:00';
      if (new Date(dueAt).getTime() <= Date.now()) {
        showFormError(time ? 'That time has already passed. Pick a time in the future.'
                           : 'That date has already passed. Pick today or a later day.');
        return;
      }
      payload.due_at = dueAt;
      payload.all_day = !time;
    }
    if (Object.keys(payload).length === 0) {
      closeModal();
      home.showToast('No changes.');
      return;
    }
    showFormError('');
    busy = true;
    if (submitBtn) { submitBtn.disabled = true; }
    var r = await home.api('/tasks/' + task.id, 'PATCH', payload);
    busy = false;
    if (submitBtn) { submitBtn.disabled = false; }
    if (!r.ok) {
      if (r.status === 401) { return; }
      if (r.status === 404 || r.status === 403) {   // deleted or already decided meanwhile
        closeModal();
        home.showToast(home.errorText(r));
        if (editing.onSaved) { editing.onSaved(); }
        return;
      }
      showFormError(home.errorText(r));
      return;
    }
    closeModal();
    home.showToast('Task updated.');
    if (editing.onSaved) { editing.onSaved(); }
  }

  form.addEventListener('submit', async function (e) {
    e.preventDefault();
    if (busy) { return; }
    var title = byId('todoTitle').value.trim();
    var type = byId('todoType').value;
    var date = byId('todoDate').value;
    var time = byId('todoTime').value ? byId('todoTime').value.slice(0, 5) : '';
    var subject = byId('todoSubject').value.trim();
    var roomId = Number(byId('todoModalRoom').value);

    if (editing) {
      if (!title || !type || !date) {
        showFormError('Please fill in the title, type and due date.');
        return;
      }
      await saveEdit(title, type, subject, date, time);
      return;
    }

    if (!title || !type || !date || !roomId) {
      showFormError('Please fill in the title, type, due date and room.');
      return;
    }
    // The date and time you typed are Manila time. No time means "all day" (end of that day).
    var dueAt = date + 'T' + (time ? time : '23:59') + ':00+08:00';
    if (new Date(dueAt).getTime() <= Date.now()) {
      showFormError(time ? 'That time has already passed. Pick a time in the future.'
                         : 'That date has already passed. Pick today or a later day.');
      return;
    }
    showFormError('');

    var payload = { title: title, type: type, due_at: dueAt, all_day: !time };
    if (subject) { payload.subject = subject; }

    busy = true;
    if (submitBtn) { submitBtn.disabled = true; }
    var r = await home.api('/rooms/' + roomId + '/tasks', 'POST', payload);
    busy = false;
    if (submitBtn) { submitBtn.disabled = false; }

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
    // Refresh the sidebar badge and whatever page you are on.
    document.dispatchEvent(new CustomEvent('roomsync:rooms-changed'));
  });
})();