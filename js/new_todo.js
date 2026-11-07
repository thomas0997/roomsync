/* ============================================================
   ROOMSYNC — new_todo.js
   The New TODO form, shared by every page that has the + New TODO button
   (Home, Calendar, Approve, Discussion, Notes, About):
   - sends a real task to the API; a member's task waits for an admin to approve it
   - then asks the page to refresh (the "roomsync:rooms-changed" event reloads the sidebar
     and every page script reloads its data for the room)
   The same form also EDITS a task: window.RoomSyncNewTodo.openEdit(task, onSaved).
   The creator or a room admin can edit a pending task; only an admin can edit an approved one
   (the server decides).
   Extras this file adds to the form itself (no page needs its own HTML for them):
   - "Custom..." in the Type list: a tag of 1 to 15 characters
   - an optional Note (300 characters)
   - "+ Add another title": more titles that share the type, subject, date and time. Each title is
     sent as its OWN task (one POST each), so every title stays a separate card.
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

  var CUSTOM = '__custom__';   // the value of the "Custom..." choice in the Type list
  var KNOWN_TYPES = ['exam', 'quiz', 'case-study', 'activity', 'seatwork', 'assignment'];
  var MAX_TITLES = 10;         // titles per form (the server allows 20 new tasks an hour per person)
  var MAX_CUSTOM = 15;         // same limit as the server
  var typeSelect = byId('todoType');
  var customWrap = null;
  var customInput = null;
  var noteInput = null;
  var noteWrap = null;
  var extraBox = null;
  var addTitleBtn = null;
  var addTitleHint = null;

  function field(labelText, control) {
    var label = document.createElement('label');
    label.className = 'abt-field';
    var span = document.createElement('span');
    span.className = 'abt-field-label';
    span.textContent = labelText;
    label.appendChild(span);
    label.appendChild(control);
    return label;
  }

  function after(node, newNode) { node.parentNode.insertBefore(newNode, node.nextSibling); }

  function syncCustom() {
    if (!customWrap) { return; }
    customWrap.hidden = typeSelect.value !== CUSTOM;
    if (!customWrap.hidden) { customInput.focus(); }
  }

  function extraInputs() { return extraBox ? extraBox.querySelectorAll('input') : []; }

  function syncAddTitle() {
    if (!addTitleBtn) { return; }
    var count = extraInputs().length;
    addTitleBtn.disabled = count + 1 >= MAX_TITLES;
    addTitleHint.hidden = count === 0;
  }

  function addTitleRow(text) {
    var row = document.createElement('div');
    row.className = 'todo-extra-row';
    var input = document.createElement('input');
    input.type = 'text';
    input.maxLength = 200;
    input.placeholder = 'Another title';
    input.setAttribute('aria-label', 'Another title');
    input.value = text || '';
    var remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'todo-extra-remove';
    remove.textContent = '\u00d7';
    remove.setAttribute('aria-label', 'Remove this title');
    remove.addEventListener('click', function () { row.remove(); syncAddTitle(); });
    row.appendChild(input);
    row.appendChild(remove);
    extraBox.appendChild(row);
    syncAddTitle();
    return input;
  }

  // The short create form: title, type chips, one date, then optional links.
  // Subject, time and extra titles are not shown while creating; Edit still has every field.
  var CHIP_TYPES = [['exam', 'Exam'], ['quiz', 'Quiz'], ['case-study', 'Case Study'],
                    ['assignment', 'Assignment'], ['activity', 'Activity'], ['seatwork', 'Seatwork'], [CUSTOM, '+ Custom']];
  var chipBox = null;
  var noteLink = null;
  var timeLink = null;
  var timeWrap = null;
  var attachLink = null;   // "+ Attach notes" (needs js/attach_picker.js)
  var attachWrap = null;   // the "Attached notes" list under the form
  var attached = [];       // the room files picked for the new task (at most 5)

  function syncChips() {
    if (!chipBox) { return; }
    Array.prototype.forEach.call(chipBox.children, function (b) {
      b.setAttribute('aria-pressed', b.getAttribute('data-type') === typeSelect.value ? 'true' : 'false');
    });
  }

  // Notes (room files) can be attached while creating. The list shows name and size with a x to remove one.
  function drawAttached() {
    if (!attachWrap) { return; }
    var box = attachWrap.querySelector('.todo-attached-list');
    box.textContent = '';
    attached.forEach(function (f) {
      var item = document.createElement('div');
      item.className = 'todo-attached-item';
      var name = document.createElement('span');
      name.className = 'todo-attached-name';
      name.textContent = f.name;
      var size = document.createElement('span');
      size.className = 'todo-attached-size';
      size.textContent = f.size < 1048576 ? Math.max(1, Math.round(f.size / 1024)) + ' KB' : (f.size / 1048576).toFixed(1) + ' MB';
      var x = document.createElement('button');
      x.type = 'button';
      x.className = 'todo-attached-x';
      x.textContent = '\u00d7';
      x.setAttribute('aria-label', 'Remove ' + f.name);
      x.addEventListener('click', function () {
        attached = attached.filter(function (a) { return a.id !== f.id; });
        drawAttached();
      });
      item.appendChild(name);
      item.appendChild(size);
      item.appendChild(x);
      box.appendChild(item);
    });
    attachWrap.classList.toggle('open', attached.length > 0);
    if (attachLink) { attachLink.hidden = attached.length > 0; }
  }

  async function chooseNotes() {
    var roomId = Number(byId('todoModalRoom').value);
    if (!roomId) { showFormError('Pick a room first.'); return; }
    var picked = await window.RoomSyncAttach.pickFiles({
      roomId: roomId, max: 5,
      selected: attached.map(function (f) { return f.id; })
    });
    if (picked) { attached = picked; drawAttached(); }
  }

  function buildAttach(links) {
    attachLink = document.createElement('button');
    attachLink.type = 'button';
    attachLink.className = 'todo-link-btn';
    attachLink.textContent = '+ Attach notes';
    attachLink.addEventListener('click', chooseNotes);
    links.appendChild(attachLink);
    attachWrap = document.createElement('div');
    attachWrap.className = 'todo-attach-field';
    var label = document.createElement('span');
    label.className = 'abt-field-label';
    label.textContent = 'Attached notes';
    var listBox = document.createElement('div');
    listBox.className = 'todo-attached-list';
    var more = document.createElement('button');
    more.type = 'button';
    more.className = 'todo-link-btn';
    more.textContent = '+ Attach more notes';
    more.addEventListener('click', chooseNotes);
    attachWrap.appendChild(label);
    attachWrap.appendChild(listBox);
    attachWrap.appendChild(more);
    links.parentNode.insertBefore(attachWrap, links);
    byId('todoModalRoom').addEventListener('change', function () { attached = []; drawAttached(); });   // notes belong to one room
  }

  function buildSimple() {
    chipBox = document.createElement('div');
    chipBox.className = 'todo-type-chips';
    CHIP_TYPES.forEach(function (pair) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'todo-chip';
      b.setAttribute('data-type', pair[0]);
      b.setAttribute('aria-pressed', 'false');
      b.textContent = pair[1];
      b.addEventListener('click', function () {
        typeSelect.value = pair[0];
        typeSelect.dispatchEvent(new Event('change'));
        syncChips();
      });
      chipBox.appendChild(b);
    });
    typeSelect.parentNode.appendChild(chipBox);
    typeSelect.required = false;   // the select is hidden here; the submit check below shows the message instead
    typeSelect.addEventListener('change', syncChips);
    byId('todoSubject').closest('label').classList.add('todo-opt-field');
    timeWrap = byId('todoTime').closest('label');
    timeWrap.classList.add('todo-time-field');
    byId('todoModalRoom').closest('label').classList.add('todo-room-field');
    function makeLink(text, wrap, field) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'todo-link-btn';
      b.textContent = text;
      b.addEventListener('click', function () {
        wrap.classList.add('open');
        b.hidden = true;
        field.focus();
      });
      return b;
    }
    timeLink = makeLink('+ Add time', timeWrap, byId('todoTime'));
    noteLink = makeLink('+ Add a note', noteWrap, noteInput);
    var links = document.createElement('div');
    links.className = 'todo-quick-links';
    links.appendChild(timeLink);
    links.appendChild(noteLink);
    errorBox.parentNode.insertBefore(links, errorBox);
    if (window.RoomSyncAttach) { buildAttach(links); }   // needs the links row to be in the page already
    form.classList.add('todo-simple');
  }

  // Put the extra bits into the form. Runs once; the form HTML on each page stays as it is.
  function buildExtras() {
    var customOpt = document.createElement('option');
    customOpt.value = CUSTOM;
    customOpt.textContent = 'Custom\u2026';
    typeSelect.appendChild(customOpt);
    customInput = document.createElement('input');
    customInput.type = 'text';
    customInput.id = 'todoCustomType';
    customInput.maxLength = MAX_CUSTOM;
    customInput.placeholder = 'e.g. Reporting';
    customWrap = field('Custom tag (up to ' + MAX_CUSTOM + ' characters)', customInput);
    customWrap.classList.add('todo-custom-type');
    customWrap.hidden = true;
    after(typeSelect.closest('label'), customWrap);
    typeSelect.addEventListener('change', syncCustom);

    noteInput = document.createElement('textarea');
    noteInput.id = 'todoNote';
    noteInput.rows = 3;
    noteInput.maxLength = 300;
    noteInput.placeholder = 'Anything your classmates should know (optional)';
    noteWrap = field('Note (optional)', noteInput);
    noteWrap.classList.add('todo-note-field');
    after(byId('todoSubject').closest('label'), noteWrap);
    buildSimple();

    var titleLabel = byId('todoTitle').closest('label');
    extraBox = document.createElement('div');
    extraBox.className = 'todo-extra-titles';
    addTitleBtn = document.createElement('button');
    addTitleBtn.type = 'button';
    addTitleBtn.className = 'todo-add-title';
    addTitleBtn.textContent = '+ Add another title';
    addTitleBtn.addEventListener('click', function () { addTitleRow('').focus(); });
    addTitleHint = document.createElement('p');
    addTitleHint.className = 'todo-hint';
    addTitleHint.textContent = 'Same type, subject, date and time. Each title becomes its own task.';
    addTitleHint.hidden = true;
    after(titleLabel, extraBox);
    after(extraBox, addTitleBtn);
    after(addTitleBtn, addTitleHint);
    form.addEventListener('reset', function () { setTimeout(resetExtras, 0); });
  }

  function resetExtras() {
    if (!extraBox) { return; }
    extraBox.textContent = '';
    customWrap.hidden = true;
    syncAddTitle();
    syncChips();
    if (noteWrap) { noteWrap.classList.remove('open'); }
    if (noteLink) { noteLink.hidden = false; }
    if (timeWrap) { timeWrap.classList.remove('open'); }
    if (timeLink) { timeLink.hidden = false; }
    attached = [];
    drawAttached();
  }

  // The tag to send: a built-in type, or the custom text (a custom tag that spells a built-in type uses it).
  function readType() {
    if (typeSelect.value !== CUSTOM) { return typeSelect.value; }
    var text = customInput.value.trim().replace(/\s+/g, ' ');
    var slug = text.toLowerCase().replace(/ /g, '-');
    return KNOWN_TYPES.indexOf(slug) !== -1 ? slug : text;
  }

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
    form.classList.toggle('todo-simple', !task);   // short form to create, full form to edit
    if (titleEl) { titleEl.textContent = task ? 'Edit TODO' : 'New TODO'; }
    if (submitBtn) { submitBtn.textContent = task ? 'Save' : 'Create'; }
    var select = byId('todoModalRoom');
    if (select) { select.disabled = !!task; }   // a task never moves to another room
    if (addTitleBtn) {                           // one title at a time when editing
      addTitleBtn.hidden = !!task;
      extraBox.hidden = !!task;
      if (task) { addTitleHint.hidden = true; } else { syncAddTitle(); }
    }
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
    if (KNOWN_TYPES.indexOf(task.type) !== -1) {
      typeSelect.value = task.type;
    } else {            // a custom tag: show it in the custom box
      typeSelect.value = CUSTOM;
      customInput.value = task.type;
    }
    syncCustom();
    byId('todoSubject').value = task.subject || '';
    noteInput.value = task.note || '';
    byId('todoDate').min = '';          // an old date is fine as long as you do not change it
    byId('todoDate').value = date;
    byId('todoTime').value = time;
    var select = byId('todoModalRoom');
    if (select) { select.value = String(task.room_id); }
    byId('todoModalOverlay').hidden = false;
  }
  window.RoomSyncNewTodo = { openEdit: openEdit };   // rooms.js sees this and does not fake the submit

  async function saveEdit(title, type, subject, note, date, time) {
    var task = editing.task;
    var payload = {};
    if (title !== task.title) { payload.title = title; }
    if (type !== task.type) { payload.type = type; }
    if (subject !== (task.subject || '')) { payload.subject = subject || null; }
    if (note !== (task.note || '')) { payload.note = note || null; }
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

  // Reads the Type list and the custom box. Returns '' (and shows the reason) when it is not usable.
  function checkedType() {
    if (typeSelect.value === CUSTOM) {
      var len = readType().length;
      if (len < 1 || len > MAX_CUSTOM) {
        showFormError('Custom tag must be 1 to ' + MAX_CUSTOM + ' characters.');
        return '';
      }
    }
    return readType();
  }

  form.addEventListener('submit', async function (e) {
    e.preventDefault();
    if (busy) { return; }
    var title = byId('todoTitle').value.trim();
    var date = byId('todoDate').value;
    var time = byId('todoTime').value ? byId('todoTime').value.slice(0, 5) : '';
    var subject = byId('todoSubject').value.trim();
    var note = noteInput.value.trim();
    var roomId = Number(byId('todoModalRoom').value);

    if (!typeSelect.value) {
      showFormError(editing ? 'Please fill in the title, type and due date.'
                            : 'Please fill in the title, type, due date and room.');
      return;
    }
    var type = checkedType();
    if (!type) { return; }

    if (editing) {
      if (!title || !type || !date) {
        showFormError('Please fill in the title, type and due date.');
        return;
      }
      await saveEdit(title, type, subject, note, date, time);
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

    // The first title plus any extra titles (blank ones are skipped). One task per title.
    var titles = [title];
    Array.prototype.forEach.call(extraInputs(), function (input) {
      var t = input.value.trim();
      if (t) { titles.push(t); }
    });

    busy = true;
    if (submitBtn) { submitBtn.disabled = true; }
    var created = 0;
    var approvedCount = 0;
    var failure = null;
    for (var i = 0; i < titles.length; i++) {
      var payload = { title: titles[i], type: type, due_at: dueAt, all_day: !time };
      if (subject) { payload.subject = subject; }
      if (note) { payload.note = note; }
      if (attached.length) { payload.file_ids = attached.map(function (f) { return f.id; }); }
      var r = await home.api('/rooms/' + roomId + '/tasks', 'POST', payload);
      if (!r.ok) { failure = r; break; }
      created += 1;
      if (r.body.status === 'approved') { approvedCount += 1; }
    }
    busy = false;
    if (submitBtn) { submitBtn.disabled = false; }

    if (created > 0) {   // the room page and the sidebar badge refresh even after a partial success
      document.dispatchEvent(new CustomEvent('roomsync:rooms-changed'));
    }
    if (failure) {
      if (created > 0) {   // keep only the titles that were NOT created, so nothing is sent twice
        var left = titles.slice(created);
        byId('todoTitle').value = left[0];
        extraBox.textContent = '';
        left.slice(1).forEach(function (t) { addTitleRow(t); });
        syncAddTitle();
        home.showToast(created + ' of ' + titles.length + ' created.');
      }
      if (failure.status !== 401) { showFormError(home.errorText(failure)); }
      return;
    }
    closeModal();
    form.reset();
    if (created > 1) {
      home.showToast(created + ' TODOs created' + (approvedCount < created ? '. Pending ones show once an admin approves them.' : '!'));
    } else if (approvedCount === 1) {
      home.showToast('TODO created!');
    } else {
      home.showToast('Sent for approval. It shows on the board once an admin approves it.');
    }
  });

  buildExtras();
})();