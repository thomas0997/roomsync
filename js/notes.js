/* ============================================================
   ROOMSYNC — notes.js
   Notes page, wired to the API:
   - the room's shared files (Upload File, list, filter, sort)
   - click a text or code file to read it in the page; click a PDF or Word file to download it
   - delete your own files (admins can delete any)
   New Doc and New Sheet are "coming soon".
   Every file name and every line of text is written with textContent (never innerHTML).
   Needs: js/sidebar_rooms.js (window.RoomSyncHome) loaded first.
   ============================================================ */
(function () {
  'use strict';

  var home = window.RoomSyncHome;
  var cfg = window.ROOMSYNC || {};
  var grid = document.getElementById('notesGrid');
  if (!home || !grid) { return; }

  var MAX_BYTES = 10 * 1024 * 1024;
  var BINARY = { pdf: 1, docx: 1 };
  var TEXT = { txt: 1, md: 1, csv: 1, json: 1, sql: 1, py: 1, java: 1, c: 1, cc: 1, cpp: 1, cxx: 1, h: 1, hpp: 1, cs: 1, js: 1, ts: 1 };

  var files = [];           // the room's files, as the server sent them
  var filter = 'all';
  var sortKey = 'date-modified';
  var loadCounter = 0;      // lets us ignore answers that arrive after you switched room
  var viewing = null;       // the file open in the viewer
  var viewCounter = 0;
  var uploading = false;

  function byId(id) { return document.getElementById(id); }
  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) { node.className = cls; }
    if (text !== undefined) { node.textContent = text; }
    return node;
  }
  function read(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }
  function extOf(name) { var i = name.lastIndexOf('.'); return i < 0 ? '' : name.slice(i + 1).toLowerCase(); }
  function myId() { try { return JSON.parse(read(cfg.USER_KEY || 'roomsync_user') || 'null').id; } catch (e) { return null; } }

  // For the two things the shared api() cannot do: send a raw file, and receive a file.
  async function authFetch(path, opts) {
    opts = opts || {};
    opts.headers = opts.headers || {};
    opts.headers.Authorization = 'Bearer ' + read(cfg.TOKEN_KEY || 'roomsync_token');
    var res;
    try { res = await fetch((cfg.API_BASE || '') + path, opts); } catch (e) { return null; }
    if (res.status === 401) { window.location.replace('login.html'); return null; }
    return res;
  }
  async function problemText(res) {
    if (!res) { return home.errorText({ status: 0, body: null }); }
    var body = null;
    try { body = await res.json(); } catch (e) { body = null; }
    return home.errorText({ status: res.status, body: body });
  }

  function prettySize(n) {
    if (n < 1024) { return n + ' B'; }
    if (n < 1024 * 1024) { return Math.round(n / 1024) + ' KB'; }
    return (n / (1024 * 1024)).toFixed(1) + ' MB';
  }
  function timeAgo(iso) {
    var seconds = Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 1000));
    if (seconds < 60) { return 'just now'; }
    var minutes = Math.round(seconds / 60);
    if (minutes < 60) { return minutes + (minutes === 1 ? ' minute ago' : ' minutes ago'); }
    var hours = Math.round(minutes / 60);
    if (hours < 24) { return hours + (hours === 1 ? ' hour ago' : ' hours ago'); }
    var days = Math.round(hours / 24);
    if (days < 30) { return days + (days === 1 ? ' day ago' : ' days ago'); }
    return new Date(iso).toLocaleDateString();
  }

  /* ---------- the list ---------- */
  function setMessage(text) {
    var note = byId('notesEmpty');
    note.textContent = text || '';
    note.hidden = !text;
  }

  function visibleFiles() {
    var list = files.filter(function (f) { return filter === 'all' || f.kind === filter; });
    list.sort(function (a, b) {
      if (sortKey === 'az') { return a.name.toLowerCase() < b.name.toLowerCase() ? -1 : 1; }
      if (sortKey === 'za') { return a.name.toLowerCase() < b.name.toLowerCase() ? 1 : -1; }
      return Date.parse(b.created_at) - Date.parse(a.created_at);   // newest first (modified and added are the same for now)
    });
    return list;
  }

  var SVG_NS = 'http://www.w3.org/2000/svg';
  function trashIcon() {
    var svg = document.createElementNS(SVG_NS, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '2');
    var path = document.createElementNS(SVG_NS, 'path');
    path.setAttribute('d', 'M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14M10 11v6M14 11v6');
    svg.appendChild(path);
    return svg;
  }

  function fileCard(f) {
    var item = el('div', 'notes-file-item');
    var card = el('button', 'notes-file-card');
    card.type = 'button';
    card.dataset.type = f.kind;
    var docs = f.kind === 'docs';
    card.appendChild(el('span', 'notes-file-icon ' + (docs ? 'notes-icon-doc' : 'notes-icon-generic'),
                        docs ? 'D' : extOf(f.name).toUpperCase().slice(0, 4)));
    card.appendChild(el('span', 'notes-file-name', f.name));
    card.appendChild(el('span', 'notes-file-meta',
                        f.created_by_name + ' • ' + prettySize(f.size) + ' • ' + timeAgo(f.created_at)));
    card.addEventListener('click', function () { openFile(f); });
    item.appendChild(card);
    if (f.created_by === myId() || home.isAdmin()) {
      var del = el('button', 'notes-file-delete');
      del.type = 'button';
      del.setAttribute('aria-label', 'Delete ' + f.name);
      del.title = 'Delete for everyone';
      del.appendChild(trashIcon());
      del.addEventListener('click', function () { deleteFile(f); });
      item.appendChild(del);
    }
    return item;
  }

  function render() {
    while (grid.firstChild) { grid.removeChild(grid.firstChild); }
    var list = visibleFiles();
    list.forEach(function (f) { grid.appendChild(fileCard(f)); });
    if (list.length === 0 && files.length > 0) { setMessage('No ' + filter + ' here yet.'); }
    else if (list.length === 0) { setMessage('No files yet. Upload the first one!'); }
    else { setMessage(''); }
  }

  async function load() {
    var mine = ++loadCounter;
    var roomId = home.currentRoomId();
    files = [];
    while (grid.firstChild) { grid.removeChild(grid.firstChild); }
    if (roomId === null || roomId === undefined) { setMessage('Join or create a room to share files.'); return; }
    setMessage('Loading files...');
    var r = await home.api('/rooms/' + roomId + '/files');
    if (mine !== loadCounter) { return; }   // you switched room while this loaded
    if (!r.ok) { setMessage("Couldn't load this room's files."); home.showToast(home.errorText(r)); return; }
    files = r.body;
    render();
  }

  /* ---------- open, download, delete ---------- */
  async function download(f) {
    var res = await authFetch('/files/' + f.id + '/download');
    if (!res || !res.ok) { home.showToast(await problemText(res)); return; }
    var url = URL.createObjectURL(await res.blob());
    var link = document.createElement('a');
    link.href = url;
    link.download = f.name;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 10000);
  }

  function openFile(f) {
    if (TEXT[extOf(f.name)]) { openViewer(f); } else { download(f); }
  }

  async function openViewer(f) {
    var mine = ++viewCounter;
    viewing = f;
    byId('fileViewTitle').textContent = f.name;
    byId('fileViewText').textContent = 'Loading...';
    byId('fileViewNote').hidden = true;
    byId('fileViewOverlay').hidden = false;
    byId('fileViewClose').focus();
    var r = await home.api('/files/' + f.id + '/text');
    if (mine !== viewCounter) { return; }   // closed or replaced while loading
    if (!r.ok) { closeViewer(); home.showToast(home.errorText(r)); return; }
    byId('fileViewText').textContent = r.body.text;
    var note = byId('fileViewNote');
    note.textContent = 'Showing the first part of this file. Download it to see everything.';
    note.hidden = !r.body.truncated;
  }

  function closeViewer() {
    viewCounter++;
    viewing = null;
    byId('fileViewOverlay').hidden = true;
    byId('fileViewText').textContent = '';
  }

  async function deleteFile(f) {
    if (!window.confirm('Delete "' + f.name + '" for everyone in the room? This cannot be undone.')) { return; }
    var r = await home.api('/files/' + f.id, 'DELETE');
    if (!r.ok && r.status !== 404) { if (r.status !== 401) { home.showToast(home.errorText(r)); } return; }
    files = files.filter(function (x) { return x.id !== f.id; });
    render();
    home.showToast('File deleted.');
  }

  /* ---------- upload ---------- */
  async function uploadAll(picked) {
    var roomId = home.currentRoomId();
    if (roomId === null || roomId === undefined) { home.showToast('Join or create a room first.'); return; }
    var button = byId('notesUpload');
    var title = byId('notesUploadTitle');
    uploading = true;
    button.disabled = true;
    var done = 0;
    for (var i = 0; i < picked.length; i++) {
      var file = picked[i];
      var ext = extOf(file.name);
      if (!BINARY[ext] && !TEXT[ext]) { home.showToast('"' + file.name + '" is not an allowed file type.'); continue; }
      if (file.size === 0) { home.showToast('"' + file.name + '" is empty.'); continue; }
      if (file.size > MAX_BYTES) { home.showToast('"' + file.name + '" is over 10 MB.'); continue; }
      title.textContent = 'Uploading ' + (i + 1) + ' of ' + picked.length + '...';
      var res = await authFetch('/rooms/' + roomId + '/files?name=' + encodeURIComponent(file.name), {
        method: 'POST',
        headers: { 'Content-Type': 'application/octet-stream' },
        body: file
      });
      if (res && res.status === 201) {
        files.unshift(await res.json());
        done++;
        render();
      } else {
        home.showToast(file.name + ': ' + await problemText(res));
      }
    }
    title.textContent = 'Upload File';
    button.disabled = false;
    uploading = false;
    if (done > 0) { home.showToast(done === 1 ? 'File uploaded.' : done + ' files uploaded.'); }
  }

  /* ---------- wiring ---------- */
  var input = byId('notesFileInput');
  byId('notesUpload').addEventListener('click', function () { if (!uploading) { input.click(); } });
  input.addEventListener('change', function () {
    var picked = Array.prototype.slice.call(input.files);
    input.value = '';                       // so choosing the same file again still fires
    if (picked.length) { uploadAll(picked); }
  });
  byId('notesNewDoc').addEventListener('click', function () { home.showToast('New docs are coming soon. For now, upload a .docx file.'); });
  byId('notesNewSheet').addEventListener('click', function () { home.showToast('New sheets are coming soon.'); });

  var pills = document.querySelectorAll('.notes-filter-pill');
  pills.forEach(function (pill) {
    pill.addEventListener('click', function () {
      pills.forEach(function (p) { p.classList.remove('notes-filter-active'); });
      pill.classList.add('notes-filter-active');
      filter = pill.dataset.filter;
      render();
    });
  });
  var sortSelect = byId('notesSortSelect');
  if (sortSelect) { sortSelect.addEventListener('change', function () { sortKey = sortSelect.value; render(); }); }

  byId('fileViewClose').addEventListener('click', closeViewer);
  byId('fileViewDone').addEventListener('click', closeViewer);
  byId('fileViewDownload').addEventListener('click', function () { if (viewing) { download(viewing); } });
  byId('fileViewOverlay').addEventListener('click', function (e) { if (e.target === e.currentTarget) { closeViewer(); } });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !byId('fileViewOverlay').hidden) { closeViewer(); } });

  document.addEventListener('roomsync:room', load);
  if (home.currentRoomId() !== null && home.currentRoomId() !== undefined) { load(); }
  else { setMessage('Loading files...'); }
})();
