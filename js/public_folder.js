/* ============================================================
   ROOMSYNC — public_folder.js
   Opened from a folder's public share link: public_folder.html?token=...
   No login, no RoomSync account -- GET /public/folders/{token} lists the files,
   and each one downloads straight from GET /public/folders/{token}/files/{file_id}.
   Every name and size is written with textContent (never innerHTML).
   ============================================================ */
document.addEventListener('DOMContentLoaded', function () {
  'use strict';

  var cfg = window.ROOMSYNC || {};
  var grid = document.getElementById('pfGrid');
  var titleEl = document.getElementById('pfFolderName');
  var subEl = document.querySelector('.pf-sub');
  var emptyEl = document.getElementById('pfEmpty');

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

  function extOf(name) { var i = name.lastIndexOf('.'); return i < 0 ? '' : name.slice(i + 1).toLowerCase(); }

  function downloadIcon() {
    var NS = 'http://www.w3.org/2000/svg';
    var svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '2');
    svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round');
    svg.setAttribute('aria-hidden', 'true');
    var path = document.createElementNS(NS, 'path');
    path.setAttribute('d', 'M12 4v11M7 11l5 5 5-5M5 20h14');
    svg.appendChild(path);
    return svg;
  }

  function showError(message) {
    titleEl.textContent = 'Link not available';
    if (subEl) { subEl.textContent = message; }
    grid.hidden = true;
  }

  var token = new URLSearchParams(window.location.search).get('token') || '';
  if (!token) { showError('This link is missing its token.'); return; }

  fetch((cfg.API_BASE || '') + '/public/folders/' + encodeURIComponent(token))
    .then(function (res) {
      if (res.status === 404) { showError('This folder link is invalid or has been turned off.'); return null; }
      if (res.status === 429) { showError('Too many requests. Please wait a bit and try again.'); return null; }
      if (!res.ok) { showError('Something went wrong loading this folder.'); return null; }
      return res.json();
    })
    .then(function (body) {
      if (!body) { return; }
      titleEl.textContent = body.name;
      var files = body.files || [];
      if (files.length === 0) {
        emptyEl.textContent = 'This folder is empty.';
        emptyEl.hidden = false;
        return;
      }
      files.forEach(function (f) {
        var item = el('div', 'notes-file-item');
        var card = el('a', 'notes-file-card pf-file-card');
        card.href = (cfg.API_BASE || '') + '/public/folders/' + encodeURIComponent(token) + '/files/' + f.id;
        // The server always forces a real download via Content-Disposition, so this is only a hint.
        card.setAttribute('download', f.name);
        var docs = f.kind === 'docs';
        card.appendChild(el('span', 'notes-file-icon ' + (docs ? 'notes-icon-doc' : 'notes-icon-generic'),
                            docs ? 'D' : extOf(f.name).toUpperCase().slice(0, 4)));
        card.appendChild(el('span', 'notes-file-name', f.name));
        card.appendChild(el('span', 'notes-file-meta', prettySize(f.size)));
        var cue = el('span', 'notes-file-cue');
        cue.appendChild(downloadIcon());
        cue.appendChild(el('span', 'notes-file-cue-text', 'Click to download'));
        card.appendChild(cue);
        item.appendChild(card);
        grid.appendChild(item);
      });
    })
    .catch(function () {
      showError('Can’t reach RoomSync right now. Check your connection and try again.');
    });
});
