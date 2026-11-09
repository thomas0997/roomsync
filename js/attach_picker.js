/* ============================================================
   ROOMSYNC — attach_picker.js
   Two small pop-ups for linking notes (room files) to tasks, plus a download helper:
     RoomSyncAttach.pickFiles({ roomId, selected, max })  -> Promise of the chosen file objects, or null if cancelled
         "Attach notes": tick up to 5 of the room's files.
     RoomSyncAttach.pickTask({ roomId, file })            -> Promise of the chosen task object, or null if cancelled
         "Attach to a task": search the room's approved tasks and pick one.
     RoomSyncAttach.download(fileId, name)                -> downloads a note (same member-only check as the Notes page)
   Every name and title is written with textContent (never innerHTML).
   Needs: js/sidebar_rooms.js (window.RoomSyncHome) loaded first.
   ============================================================ */
(function () {
  'use strict';

  var home = window.RoomSyncHome;
  var cfg = window.ROOMSYNC || {};
  if (!home) { return; }

  var MANILA_MS = 8 * 60 * 60 * 1000;
  var MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) { node.className = cls; }
    if (text !== undefined) { node.textContent = text; }
    return node;
  }
  function prettySize(n) {
    if (n < 1024) { return n + ' B'; }
    if (n < 1024 * 1024) { return Math.round(n / 1024) + ' KB'; }
    return (n / (1024 * 1024)).toFixed(1) + ' MB';
  }
  function extOf(name) { var i = name.lastIndexOf('.'); return i < 0 ? '' : name.slice(i + 1).toUpperCase().slice(0, 4); }
  function shortDate(iso) {
    var m = new Date(new Date(iso).getTime() + MANILA_MS);
    return MONTHS[m.getUTCMonth()] + ' ' + m.getUTCDate();
  }

  /* ---------- a pop-up shell: title, a search box, a list, Cancel and a main button ---------- */
  function shell(title, placeholder, mainLabel) {
    var overlay = el('div', 'todo-modal-overlay attach-overlay');
    var card = el('div', 'todo-modal abt-form-card attach-card');
    card.setAttribute('role', 'dialog');
    card.setAttribute('aria-modal', 'true');
    card.setAttribute('aria-label', title);
    var head = el('div', 'todo-modal-head');
    head.appendChild(el('h2', 'abt-form-title', title));
    var x = el('button', 'todo-modal-close', '×');
    x.type = 'button';
    x.setAttribute('aria-label', 'Close');
    head.appendChild(x);
    var search = el('input', 'attach-search');
    search.type = 'search';
    search.placeholder = placeholder;
    search.maxLength = 50;
    search.setAttribute('aria-label', placeholder);
    var listBox = el('div', 'attach-list');
    var msg = el('p', 'attach-msg');
    msg.hidden = true;
    var actions = el('div', 'abt-form-actions');
    var main = el('button', 'abt-btn-submit', mainLabel);
    main.type = 'button';
    var cancel = el('button', 'abt-btn-reset', 'Cancel');
    cancel.type = 'button';
    actions.appendChild(main);
    actions.appendChild(cancel);
    card.appendChild(head);
    card.appendChild(search);
    card.appendChild(listBox);
    card.appendChild(msg);
    card.appendChild(actions);
    overlay.appendChild(card);
    document.body.appendChild(overlay);
    return { overlay: overlay, search: search, list: listBox, msg: msg, main: main, cancel: cancel, x: x };
  }

  function say(ui, text) { ui.msg.textContent = text || ''; ui.msg.hidden = !text; }

  /* ---------- pick notes (files) ---------- */
  function pickFiles(opts) {
    opts = opts || {};
    var max = opts.max || 5;
    var chosen = {};   // file id -> file object
    var ui = shell('Attach notes', 'Search this room’s notes', 'Done');
    var files = [];
    return new Promise(function (resolve) {
      function finish(result) { ui.overlay.remove(); document.removeEventListener('keydown', onKey); resolve(result); }
      function onKey(e) { if (e.key === 'Escape') { finish(null); } }
      document.addEventListener('keydown', onKey);

      function count() { return Object.keys(chosen).length; }
      function draw() {
        ui.list.textContent = '';
        var q = ui.search.value.trim().toLowerCase();
        var shown = files.filter(function (f) { return !q || f.name.toLowerCase().indexOf(q) !== -1; });
        shown.forEach(function (f) {
          var on = !!chosen[f.id];
          var row = el('button', 'attach-row' + (on ? ' attach-row-on' : ''));
          row.type = 'button';
          row.setAttribute('role', 'checkbox');
          row.setAttribute('aria-checked', on ? 'true' : 'false');
          var box = el('span', 'attach-check', on ? '✓' : '');
          row.appendChild(box);
          row.appendChild(el('span', 'attach-ext', extOf(f.name)));
          var text = el('span', 'attach-row-text');
          text.appendChild(el('span', 'attach-row-name', f.name));
          text.appendChild(el('span', 'attach-row-sub', prettySize(f.size)));
          row.appendChild(text);
          row.addEventListener('click', function () {
            if (chosen[f.id]) { delete chosen[f.id]; }
            else if (count() >= max) { say(ui, 'You can attach up to ' + max + ' notes.'); return; }
            else { chosen[f.id] = f; }
            say(ui, '');
            draw();
          });
          ui.list.appendChild(row);
        });
        if (!shown.length) { say(ui, files.length ? 'No notes match that.' : 'No notes in this room yet. Upload one on the Notes page first.'); }
        ui.main.textContent = count() ? 'Done (' + count() + ')' : 'Done';
      }

      ui.x.addEventListener('click', function () { finish(null); });
      ui.cancel.addEventListener('click', function () { finish(null); });
      ui.overlay.addEventListener('click', function (e) { if (e.target === ui.overlay) { finish(null); } });
      ui.search.addEventListener('input', function () { say(ui, ''); draw(); });
      ui.main.addEventListener('click', function () {
        finish(Object.keys(chosen).map(function (k) { return chosen[k]; }));
      });

      say(ui, 'Loading...');
      home.api('/rooms/' + opts.roomId + '/files').then(function (r) {
        if (!r.ok) { say(ui, r.status === 401 ? '' : home.errorText(r)); return; }
        files = r.body;
        (opts.selected || []).forEach(function (id) {
          files.forEach(function (f) { if (f.id === id) { chosen[id] = f; } });
        });
        say(ui, '');
        draw();
        ui.search.focus();
      });
    });
  }

  /* ---------- pick a task ---------- */
  function monthText(d) { return d.getUTCFullYear() + '-' + String(d.getUTCMonth() + 1).padStart(2, '0'); }

  function pickTask(opts) {
    opts = opts || {};
    var ui = shell('Attach “' + (opts.file ? opts.file.name : 'note') + '” to', 'Search approved tasks', 'Attach');
    var tasks = [];
    var chosen = null;
    var searchCounter = 0;
    var timer = null;
    ui.main.disabled = true;
    return new Promise(function (resolve) {
      function finish(result) { clearTimeout(timer); ui.overlay.remove(); document.removeEventListener('keydown', onKey); resolve(result); }
      function onKey(e) { if (e.key === 'Escape') { finish(null); } }
      document.addEventListener('keydown', onKey);

      function draw() {
        ui.list.textContent = '';
        tasks.forEach(function (t) {
          var on = chosen && chosen.id === t.id;
          var row = el('button', 'attach-row' + (on ? ' attach-row-on' : ''));
          row.type = 'button';
          row.setAttribute('role', 'radio');
          row.setAttribute('aria-checked', on ? 'true' : 'false');
          row.appendChild(el('span', 'attach-check', on ? '✓' : ''));
          var text = el('span', 'attach-row-text');
          text.appendChild(el('span', 'attach-row-name', t.title));
          text.appendChild(el('span', 'attach-row-sub', shortDate(t.due_at) + (t.subject ? ' · ' + t.subject : '')));
          row.appendChild(text);
          row.addEventListener('click', function () { chosen = t; ui.main.disabled = false; draw(); });
          ui.list.appendChild(row);
        });
        say(ui, tasks.length ? '' : 'No approved tasks found.');
      }

      async function loadUpcoming() {
        var now = new Date(Date.now() + MANILA_MS);
        var next = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() + 1, 1));
        var a = await home.api('/rooms/' + opts.roomId + '/calendar?month=' + monthText(now));
        var b = await home.api('/rooms/' + opts.roomId + '/calendar?month=' + monthText(next));
        var all = (a.ok ? a.body : []).concat(b.ok ? b.body : []);
        if (!a.ok && !b.ok) { say(ui, a.status === 401 ? '' : home.errorText(a)); return; }
        tasks = all.filter(function (t) { return Date.parse(t.due_at) >= Date.now() - 86400000; })
                   .sort(function (x, y) { return Date.parse(x.due_at) - Date.parse(y.due_at); });
        draw();
      }

      async function runSearch() {
        var q = ui.search.value.trim();
        if (!q) { loadUpcoming(); return; }
        var mine = ++searchCounter;
        var r = await home.api('/rooms/' + opts.roomId + '/tasks/search?q=' + encodeURIComponent(q));
        if (mine !== searchCounter) { return; }
        if (!r.ok) { say(ui, r.status === 401 ? '' : home.errorText(r)); return; }
        tasks = r.body;
        draw();
      }

      ui.x.addEventListener('click', function () { finish(null); });
      ui.cancel.addEventListener('click', function () { finish(null); });
      ui.overlay.addEventListener('click', function (e) { if (e.target === ui.overlay) { finish(null); } });
      ui.search.addEventListener('input', function () { clearTimeout(timer); timer = setTimeout(runSearch, 250); });
      ui.main.addEventListener('click', function () { if (chosen) { finish(chosen); } });

      say(ui, 'Loading...');
      loadUpcoming();
      ui.search.focus();
    });
  }

  /* ---------- download a note ---------- */
  async function download(fileId, name) {
    var res;
    try {
      res = await fetch((cfg.API_BASE || '') + '/files/' + fileId + '/download',
        { headers: { Authorization: 'Bearer ' + localStorage.getItem(cfg.TOKEN_KEY || 'roomsync_token') } });
    } catch (e) { home.showToast(home.errorText({ status: 0, body: null })); return; }
    if (res.status === 401) { window.location.replace('login.html'); return; }
    if (!res.ok) {
      var body = null;
      try { body = await res.json(); } catch (e) { body = null; }
      home.showToast(home.errorText({ status: res.status, body: body }));
      return;
    }
    var url = URL.createObjectURL(await res.blob());
    var link = document.createElement('a');
    link.href = url;
    link.download = name;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 10000);
  }

  window.RoomSyncAttach = { pickFiles: pickFiles, pickTask: pickTask, download: download };
})();
