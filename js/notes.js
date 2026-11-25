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
  var folders = [];         // the room's folders (flat, no nesting)
  var filter = 'all';
  var folderFilter = 'all'; // 'all' | 'unfiled' | a folder id
  var sortKey = 'date-modified';
  var loadCounter = 0;      // lets us ignore answers that arrive after you switched room
  var viewing = null;       // the file open in the viewer
  var viewCounter = 0;
  var uploading = false;
  var movingFile = null;    // the file currently shown in the move-to-folder modal
  var editingFolder = null; // non-null while the folder modal is renaming (vs. creating new)

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
    if (folderFilter === 'unfiled') { list = list.filter(function (f) { return f.folder_id === null; }); }
    else if (folderFilter !== 'all') { list = list.filter(function (f) { return f.folder_id === folderFilter; }); }
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

  var SVG_NS_SHARE = 'http://www.w3.org/2000/svg';
  function shareIcon() {
    var svg = document.createElementNS(SVG_NS_SHARE, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '2');
    svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round');
    var path = document.createElementNS(SVG_NS_SHARE, 'path');
    path.setAttribute('d', 'M15 6a3 3 0 1 0-2.8-4M9 13.5a3 3 0 1 0 0 5.9M15 18a3 3 0 1 0 2.8 4M9.4 11.2l5.2-3M9.4 14.7l5.2 3');
    svg.appendChild(path);
    return svg;
  }

  function folderIcon() {
    var svg = document.createElementNS(SVG_NS_SHARE, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '2');
    svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round');
    var path = document.createElementNS(SVG_NS_SHARE, 'path');
    path.setAttribute('d', 'M3 7a2 2 0 0 1 2-2h4l2 2.5h8a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z');
    svg.appendChild(path);
    return svg;
  }

  function editIcon() {
    var svg = document.createElementNS(SVG_NS_SHARE, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '2');
    svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round');
    var path = document.createElementNS(SVG_NS_SHARE, 'path');
    path.setAttribute('d', 'M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19 3 20l1-4z');
    svg.appendChild(path);
    return svg;
  }

  // Under each card: which approved tasks use this note, and a button to attach it to a task.
  function usageRow(f) {
    var row = el('div', 'notes-usage');
    var used = f.used_in || [];
    var tags = el('div', 'notes-usage-tags');
    if (used.length) {
      tags.appendChild(el('span', 'notes-usage-label', 'USED IN'));
      used.forEach(function (u) { tags.appendChild(el('span', 'notes-usage-tag', u.title)); });
      var extra = (f.used_in_count || used.length) - used.length;
      if (extra > 0) { tags.appendChild(el('span', 'notes-usage-more', '+' + extra + ' more')); }
    } else {
      tags.appendChild(el('span', 'notes-usage-label', 'NOT ATTACHED TO ANY TASK'));
    }
    row.appendChild(tags);
    if (window.RoomSyncAttach) {
      var attach = el('button', 'todo-link-btn notes-usage-attach', 'Attach to a task');
      attach.type = 'button';
      attach.addEventListener('click', function () { attachToTask(f); });
      row.appendChild(attach);
    }
    return row;
  }

  async function attachToTask(f) {
    var roomId = home.currentRoomId();
    var task = await window.RoomSyncAttach.pickTask({ roomId: roomId, file: f });
    if (!task) { return; }
    var r = await home.api('/tasks/' + task.id + '/attachments/' + f.id, 'PUT');
    if (!r.ok) { if (r.status !== 401) { home.showToast(home.errorText(r)); } return; }
    home.showToast('Attached to \u201c' + task.title + '\u201d.');
    load();   // refresh the "Used in" tags
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
    var opens = !!TEXT[extOf(f.name)];
    var cue = el('span', 'notes-file-cue');
    cue.appendChild(cueIcon(opens ? 'open' : 'download'));
    cue.appendChild(el('span', 'notes-file-cue-text', opens ? 'Click to open' : 'Click to download'));
    card.appendChild(cue);
    card.title = opens ? 'Open ' + f.name : 'Download ' + f.name;
    card.addEventListener('click', function () { openFile(f, card); });
    item.appendChild(card);
    item.appendChild(usageRow(f));
    var canManage = f.created_by === myId() || home.isAdmin();
    if (canManage) {
      var move = el('button', 'notes-file-move');
      move.type = 'button';
      move.setAttribute('aria-label', 'Move ' + f.name + ' to a folder');
      move.title = 'Move to a folder';
      move.appendChild(folderIcon());
      move.addEventListener('click', function (e) { e.stopPropagation(); openMoveModal(f); });
      item.appendChild(move);

      var share = el('button', 'notes-file-share' + (f.is_public ? ' is-public' : ''));
      share.type = 'button';
      share.setAttribute('aria-label', (f.is_public ? 'Manage public link for ' : 'Share ') + f.name);
      share.title = f.is_public ? 'Public link is on' : 'Share with a public link';
      share.appendChild(shareIcon());
      share.addEventListener('click', function (e) { e.stopPropagation(); openShareModal(f, 'file'); });
      item.appendChild(share);

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
    renderFolderBar();
  }

  async function load() {
    var mine = ++loadCounter;
    var roomId = home.currentRoomId();
    files = [];
    folders = [];
    folderFilter = 'all';
    while (grid.firstChild) { grid.removeChild(grid.firstChild); }
    if (roomId === null || roomId === undefined) { setMessage('Join or create a room to share files.'); renderFolderBar(); return; }
    setMessage('Loading files...');
    var r = await home.api('/rooms/' + roomId + '/files');
    if (mine !== loadCounter) { return; }   // you switched room while this loaded
    if (!r.ok) { setMessage("Couldn't load this room's files."); home.showToast(home.errorText(r)); return; }
    files = r.body;
    var fr = await home.api('/rooms/' + roomId + '/folders');
    if (mine !== loadCounter) { return; }
    folders = fr.ok ? fr.body : [];
    render();
  }

  /* ---------- folders ---------- */
  function folderCanManage(folder) {
    return folder.created_by === myId() || home.isAdmin();
  }

  function renderFolderBar() {
    var row = byId('notesFolderRow');
    if (!row) { return; }
    while (row.firstChild) { row.removeChild(row.firstChild); }

    function chip(key, label, count) {
      var btn = el('button', 'notes-filter-pill notes-folder-pill' + (folderFilter === key ? ' notes-filter-active' : ''),
                   count === undefined ? label : label + ' (' + count + ')');
      btn.type = 'button';
      btn.addEventListener('click', function () { folderFilter = key; render(); });
      return btn;
    }

    row.appendChild(chip('all', 'All'));
    row.appendChild(chip('unfiled', 'Unfiled', files.filter(function (f) { return f.folder_id === null; }).length));
    folders.forEach(function (folder) {
      row.appendChild(chip(folder.id, folder.name, folder.file_count));
    });

    var add = el('button', 'notes-filter-pill notes-folder-add', '+ New Folder');
    add.type = 'button';
    add.addEventListener('click', function () { openFolderModal(null); });
    row.appendChild(add);

    renderFolderToolbar();
  }

  function renderFolderToolbar() {
    var bar = byId('notesFolderToolbar');
    var actions = byId('notesFolderToolbarActions');
    if (!bar || !actions) { return; }
    var folder = typeof folderFilter === 'number' ? folders.find(function (f) { return f.id === folderFilter; }) : null;
    if (!folder) { bar.hidden = true; return; }
    bar.hidden = false;
    byId('notesFolderToolbarName').textContent = folder.name;
    while (actions.firstChild) { actions.removeChild(actions.firstChild); }
    if (!folderCanManage(folder)) { return; }

    var share = el('button', 'notes-file-share' + (folder.is_public ? ' is-public' : ''));
    share.type = 'button';
    share.title = folder.is_public ? 'Public link is on' : 'Share with a public link';
    share.setAttribute('aria-label', (folder.is_public ? 'Manage public link for ' : 'Share ') + folder.name);
    share.appendChild(shareIcon());
    share.addEventListener('click', function () { openShareModal(folder, 'folder'); });
    actions.appendChild(share);

    var rename = el('button', 'notes-file-share');
    rename.type = 'button';
    rename.title = 'Rename folder';
    rename.setAttribute('aria-label', 'Rename ' + folder.name);
    rename.appendChild(editIcon());
    rename.addEventListener('click', function () { openFolderModal(folder); });
    actions.appendChild(rename);

    var del = el('button', 'notes-file-delete');
    del.type = 'button';
    del.title = 'Delete folder';
    del.setAttribute('aria-label', 'Delete ' + folder.name);
    del.appendChild(trashIcon());
    del.addEventListener('click', function () { deleteFolder(folder); });
    actions.appendChild(del);
  }

  function openFolderModal(folder) {
    editingFolder = folder;
    byId('folderModalTitle').textContent = folder ? 'Rename folder' : 'New folder';
    byId('folderModalSubmit').textContent = folder ? 'Save' : 'Create';
    byId('folderModalName').value = folder ? folder.name : '';
    byId('folderModalError').hidden = true;
    byId('folderModalOverlay').hidden = false;
    byId('folderModalName').focus();
  }

  function closeFolderModal() {
    editingFolder = null;
    byId('folderModalOverlay').hidden = true;
  }

  async function submitFolderModal(e) {
    e.preventDefault();
    var name = byId('folderModalName').value.trim();
    var errorBox = byId('folderModalError');
    errorBox.hidden = true;
    if (!name) { return; }
    var roomId = home.currentRoomId();
    var r = editingFolder
      ? await home.api('/folders/' + editingFolder.id, 'PATCH', { name: name })
      : await home.api('/rooms/' + roomId + '/folders', 'POST', { name: name });
    if (!r.ok) {
      if (r.status !== 401) { errorBox.textContent = home.errorText(r); errorBox.hidden = false; }
      return;
    }
    if (editingFolder) {
      var i = folders.findIndex(function (x) { return x.id === r.body.id; });
      if (i !== -1) { folders[i] = r.body; }
    } else {
      folders.push(r.body);
    }
    closeFolderModal();
    render();
    home.showToast(editingFolder ? 'Folder renamed.' : 'Folder created.');
  }

  async function deleteFolder(folder) {
    if (!window.confirm('Delete "' + folder.name + '"? Its files will move back to the room’s main list.')) { return; }
    var r = await home.api('/folders/' + folder.id, 'DELETE');
    if (!r.ok && r.status !== 404) { if (r.status !== 401) { home.showToast(home.errorText(r)); } return; }
    folders = folders.filter(function (x) { return x.id !== folder.id; });
    files.forEach(function (f) { if (f.folder_id === folder.id) { f.folder_id = null; } });
    if (folderFilter === folder.id) { folderFilter = 'all'; }
    render();
    home.showToast('Folder deleted.');
  }

  /* ---------- move file to folder ---------- */
  function openMoveModal(f) {
    movingFile = f;
    var list = byId('moveModalList');
    while (list.firstChild) { list.removeChild(list.firstChild); }

    function option(key, label, current) {
      var btn = el('button', 'notes-move-option' + (current ? ' is-current' : ''), label);
      btn.type = 'button';
      btn.disabled = current;
      btn.addEventListener('click', function () { moveFileTo(key); });
      return btn;
    }

    list.appendChild(option(null, 'No folder (room root)', f.folder_id === null));
    folders.forEach(function (folder) {
      list.appendChild(option(folder.id, folder.name, f.folder_id === folder.id));
    });
    if (folders.length === 0) {
      list.appendChild(el('p', 'notes-empty', 'No folders yet. Create one first.'));
    }
    byId('moveModalOverlay').hidden = false;
  }

  function closeMoveModal() {
    movingFile = null;
    byId('moveModalOverlay').hidden = true;
  }

  async function moveFileTo(folderId) {
    if (!movingFile) { return; }
    var f = movingFile;
    var r = await home.api('/files/' + f.id + '/move', 'PATCH', { folder_id: folderId });
    if (!r.ok) { if (r.status !== 401) { home.showToast(home.errorText(r)); } return; }
    var i = files.findIndex(function (x) { return x.id === r.body.id; });
    if (i !== -1) { files[i] = r.body; }
    closeMoveModal();
    render();
    home.showToast(folderId === null ? 'Moved to room root.' : 'Moved to folder.');
  }

  /* ---------- open, download, delete ---------- */
  function cueIcon(kind) {
    var NS = 'http://www.w3.org/2000/svg';
    var svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '2');
    svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round');
    svg.setAttribute('aria-hidden', 'true');
    var d = { open: 'M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12zM12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z',
              download: 'M12 4v11M7 11l5 5 5-5M5 20h14',
              busy: 'M21 12a9 9 0 1 1-6.2-8.55' }[kind];
    var path = document.createElementNS(NS, 'path');
    path.setAttribute('d', d);
    svg.appendChild(path);
    return svg;
  }

  // While a download runs the card says "Downloading..." (and ignores a second click), so it never looks stuck.
  function setBusy(card, on, label) {
    if (!card) { return; }
    var cue = card.querySelector('.notes-file-cue');
    card.classList.toggle('is-busy', on);
    card.setAttribute('aria-busy', on ? 'true' : 'false');
    if (cue) {
      while (cue.firstChild) { cue.removeChild(cue.firstChild); }
      if (on) { cue.appendChild(cueIcon('busy')); cue.appendChild(el('span', 'notes-file-cue-text', 'Downloading...')); }
      else { cue.appendChild(cueIcon('download')); cue.appendChild(el('span', 'notes-file-cue-text', label || 'Click to download')); }
    }
  }

  async function download(f, card) {
    if (f.downloading) { return; }
    f.downloading = true;
    var dlBtn = byId('fileViewDownload');
    var dlLabel = dlBtn.textContent;
    setBusy(card, true);
    if (viewing && viewing.id === f.id) { dlBtn.disabled = true; dlBtn.textContent = 'Downloading...'; }
    try { await Promise.all([downloadNow(f), new Promise(function (r) { setTimeout(r, 500); })]); }
    finally {
      f.downloading = false;
      setBusy(card, false);
      dlBtn.disabled = false;
      dlBtn.textContent = dlLabel === 'Downloading...' ? 'Download' : dlLabel;
    }
  }

  async function downloadNow(f) {
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

  function openFile(f, card) {
    if (TEXT[extOf(f.name)]) { openViewer(f); } else { download(f, card); }
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

  /* ---------- public share link (files and folders share this one modal) ---------- */
  var sharing = null;      // the file or folder currently shown in the share modal
  var sharingKind = null;  // 'file' | 'folder'

  function publicLink(token) {
    var base = cfg.API_BASE || window.location.origin;
    return base + '/public/files/' + encodeURIComponent(token);
  }

  function publicFolderLink(token) {
    return window.location.origin + window.location.pathname.replace(/notes\.html$/, 'public_folder.html')
      + '?token=' + encodeURIComponent(token);
  }

  function applyShareUpdate(updated) {
    if (sharingKind === 'folder') {
      var fi = folders.findIndex(function (x) { return x.id === updated.id; });
      if (fi !== -1) { folders[fi] = updated; }
    } else {
      var i = files.findIndex(function (x) { return x.id === updated.id; });
      if (i !== -1) { files[i] = updated; }
    }
    if (sharing && sharing.id === updated.id) { sharing = updated; }
    render();
  }

  function fillShareModal(obj) {
    byId('shareModalFileName').textContent = obj.name;
    byId('shareModalTitle').textContent = sharingKind === 'folder' ? 'Share folder' : 'Share file';
    byId('shareModalNote').textContent = sharingKind === 'folder'
      ? 'Anyone with this link can browse and download every file in this folder — no RoomSync account needed. Files added to the folder later are included automatically. The rest of this room stays private.'
      : 'Anyone with this link can view and download this file — no RoomSync account needed. The rest of this room stays private.';
    var makeLink = sharingKind === 'folder' ? publicFolderLink : publicLink;
    byId('shareModalLink').value = obj.share_token ? makeLink(obj.share_token) : '';
    byId('shareModalOff').disabled = !obj.share_token;
  }

  async function openShareModal(obj, kind) {
    sharing = obj;
    sharingKind = kind;
    fillShareModal(obj);
    byId('shareModalOverlay').hidden = false;
    if (!obj.is_public) {
      byId('shareModalOff').disabled = true;
      var path = kind === 'folder' ? '/folders/' + obj.id + '/share' : '/files/' + obj.id + '/share';
      var r = await home.api(path, 'POST');
      if (sharing !== obj) { return; }   // closed before this came back
      if (!r.ok) {
        if (r.status !== 401) { home.showToast(home.errorText(r)); }
        closeShareModal();
        return;
      }
      applyShareUpdate(r.body);
      fillShareModal(r.body);
      home.showToast('Public link created.');
    }
  }

  function closeShareModal() {
    sharing = null;
    sharingKind = null;
    byId('shareModalOverlay').hidden = true;
  }

  async function turnOffShare() {
    if (!sharing) { return; }
    var obj = sharing;
    var kind = sharingKind;
    byId('shareModalOff').disabled = true;
    var path = kind === 'folder' ? '/folders/' + obj.id + '/share' : '/files/' + obj.id + '/share';
    var r = await home.api(path, 'DELETE');
    if (!r.ok) {
      if (r.status !== 401) { home.showToast(home.errorText(r)); }
      byId('shareModalOff').disabled = false;
      return;
    }
    applyShareUpdate(r.body);
    fillShareModal(r.body);
    home.showToast('Public link turned off.');
  }

  async function copyShareLink() {
    var input = byId('shareModalLink');
    if (!input.value) { return; }
    try {
      await navigator.clipboard.writeText(input.value);
      home.showToast('Link copied.');
    } catch (e) {
      input.select();
      home.showToast('Copy this link: ' + input.value);
    }
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
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') { return; }
    if (!byId('fileViewOverlay').hidden) { closeViewer(); }
    if (!byId('shareModalOverlay').hidden) { closeShareModal(); }
    if (!byId('folderModalOverlay').hidden) { closeFolderModal(); }
    if (!byId('moveModalOverlay').hidden) { closeMoveModal(); }
  });

  byId('shareModalClose').addEventListener('click', closeShareModal);
  byId('shareModalDone').addEventListener('click', closeShareModal);
  byId('shareModalOverlay').addEventListener('click', function (e) { if (e.target === e.currentTarget) { closeShareModal(); } });
  byId('shareModalCopy').addEventListener('click', copyShareLink);
  byId('shareModalOff').addEventListener('click', turnOffShare);

  byId('folderModalClose').addEventListener('click', closeFolderModal);
  byId('folderModalCancel').addEventListener('click', closeFolderModal);
  byId('folderModalOverlay').addEventListener('click', function (e) { if (e.target === e.currentTarget) { closeFolderModal(); } });
  byId('folderModalForm').addEventListener('submit', submitFolderModal);

  byId('moveModalClose').addEventListener('click', closeMoveModal);
  byId('moveModalOverlay').addEventListener('click', function (e) { if (e.target === e.currentTarget) { closeMoveModal(); } });

  document.addEventListener('roomsync:room', load);
  if (home.currentRoomId() !== null && home.currentRoomId() !== undefined) { load(); }
  else { setMessage('Loading files...'); }
})();
