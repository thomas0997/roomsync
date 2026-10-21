/* ============================================================
   ROOMSYNC — new_todo.js
   The New TODO form, shared by every page that has the + New TODO button
   (Home, Calendar, Approve, Discussion, Notes, About):
   - sends a real task to the API; a member's task waits for an admin to approve it
   - then asks the page to refresh (the "roomsync:rooms-changed" event reloads the sidebar
     and every page script reloads its data for the room)
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
  window.RoomSyncNewTodo = true;   // tells rooms.js not to fake the submit

  var MANILA_MS = 8 * 60 * 60 * 1000;   // Manila is UTC+8, no daylight saving

  function byId(id) { return document.getElementById(id); }

  function manilaTodayText() {
    return new Date(Date.now() + MANILA_MS).toISOString().slice(0, 10);
  }

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
      byId('todoDate').min = manilaTodayText();   // the date picker greys out days that are over
      var select = byId('todoModalRoom');
      var current = home.currentRoomId();
      if (select && current !== null && current !== undefined) { select.value = String(current); }
    });
  });

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

    var payload = { title: title, type: type, due_at: dueAt, all_day: !time };
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
    // Refresh the sidebar badge and whatever page you are on.
    document.dispatchEvent(new CustomEvent('roomsync:rooms-changed'));
  });
})();