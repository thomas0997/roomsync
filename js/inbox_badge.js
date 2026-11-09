/* ============================================================
   ROOMSYNC — inbox_badge.js
   On every page: asks the server how many unread Inbox messages you have (every 30 seconds while the tab is
   visible), shows a small dot on the Inbox link and the phone "More" button, and pops a toast when a new
   message arrives. The toast text is "<name>: <subject>", set with textContent (never as HTML).
   window.RoomSyncInbox.refresh() asks again right now (the Inbox page calls it after you read or delete a message).
   Needs: js/sidebar_rooms.js (window.RoomSyncHome) loaded first.
   ============================================================ */
(function () {
  'use strict';

  var home = window.RoomSyncHome;
  if (!home) { return; }

  var EVERY_MS = 30 * 1000;
  var last = null;       // the count we saw last time (null = not asked yet, so no toast on page load)
  var timer = null;
  var asking = false;

  function targets() {
    var list = Array.prototype.slice.call(document.querySelectorAll('a[href="inbox.html"]'));
    var more = document.getElementById('moreTabBtn');
    if (more) { list.push(more); }
    return list;
  }

  function showDot(n) {
    targets().forEach(function (node) {
      var dot = node.querySelector('.inbox-dot');
      if (n > 0 && !dot) {
        dot = document.createElement('span');
        dot.className = 'inbox-dot';
        dot.setAttribute('role', 'img');
        dot.setAttribute('aria-label', 'Unread messages');
        node.appendChild(dot);
      }
      if (dot) { dot.hidden = n <= 0; }
    });
  }

  async function announce() {
    var r = await home.api('/inbox?limit=1');
    if (!r.ok || !r.body || !r.body.length) { home.showToast('You have a new message in your Inbox.'); return; }
    var m = r.body[0];
    var subject = m.subject.length > 50 ? m.subject.slice(0, 50) + '…' : m.subject;
    home.showToast('New message from ' + m.from_name + ': ' + subject);
  }

  async function refresh() {
    if (asking) { return; }
    asking = true;
    try {
      var r = await home.api('/inbox/unread-count');
      if (!r.ok || !r.body || typeof r.body.count !== 'number') { return; }
      var n = r.body.count;
      showDot(n);
      var grew = last !== null && n > last;
      last = n;
      document.dispatchEvent(new CustomEvent('roomsync:inbox-unread', { detail: { count: n, grew: grew } }));
      if (grew) { announce(); }
    } finally {
      asking = false;
    }
  }

  function start() {
    refresh();
    timer = setInterval(function () { if (!document.hidden) { refresh(); } }, EVERY_MS);
    document.addEventListener('visibilitychange', function () { if (!document.hidden) { refresh(); } });
  }

  window.RoomSyncInbox = { refresh: refresh };
  if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', start); } else { start(); }
})();
