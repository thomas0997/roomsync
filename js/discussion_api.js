/* ============================================================
   ROOMSYNC — discussion_api.js
   Room chat for pages/discussion.html, wired to the API.
   Opt in with <body data-api-discussion>; js/discussion.js (the old
   demo code) returns early when that attribute is set.
   Needs js/config.js and js/sidebar_rooms.js (window.ROOMSYNC and
   window.RoomSyncHome). All user text is written with textContent,
   never innerHTML.
   ============================================================ */
(function () {
  'use strict';

  if (!document.body.hasAttribute('data-api-discussion')) { return; }
  var cfg = window.ROOMSYNC;
  var home = window.RoomSyncHome;
  if (!cfg || !home) { return; }

  var PAGE_SIZE = 50;        // the server's default page
  var MAX_LENGTH = 2000;     // the server's message limit
  var POLL_MS = 10000;
  var NEAR_BOTTOM_PX = 120;
  var SNIPPET_LENGTH = 80;
  var SVG_NS = 'http://www.w3.org/2000/svg';

  function byId(id) { return document.getElementById(id); }

  var thread = byId('discThread');
  var box = byId('discMessages');
  var emptyEl = byId('discEmpty');
  var loadRow = byId('discLoadRow');
  var loadBtn = byId('discLoadEarlier');
  var form = byId('discInputForm');
  var input = byId('discMessageInput');
  var counter = byId('discCounter');
  var replyBar = byId('discReplyIndicator');
  var replyName = byId('discReplyName');
  var replySnippet = byId('discReplySnippet');
  var replyCancel = byId('discReplyCancel');
  var sendBtn = form ? form.querySelector('.disc-send-btn') : null;
  if (!thread || !box || !emptyEl || !loadRow || !loadBtn || !form || !input || !sendBtn ||
      !counter || !replyBar || !replyName || !replySnippet || !replyCancel) { return; }

  /* ---------- state ---------- */
  var roomId = null;
  var started = false;
  var token = 0;           // changes on every room switch, so late answers from the old room are ignored
  var msgs = [];           // loaded messages, oldest first
  var nodes = {};          // message id -> element
  var members = {};        // user id -> avatar_url ('' when none)
  var hasMore = false;     // older messages may exist
  var loaded = false;      // the first page of this room has arrived
  var busy = false;        // a load or a poll is running
  var sending = false;
  var pollFailed = false;  // so a dead connection shows one toast, not one every 10 seconds
  var localSeq = 0;        // counts messages added, so a poll never removes one it started before
  var replyTo = null;      // {id, name, snippet}

  var me = null;
  try { me = JSON.parse(localStorage.getItem(cfg.USER_KEY) || 'null').id; } catch (e) { me = null; }

  /* ---------- small helpers ---------- */
  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) { node.className = className; }
    if (text !== undefined) { node.textContent = text; }
    return node;
  }

  function firstChar(text) {
    var chars = Array.from((text || '').trim());
    return chars.length ? chars[0].toUpperCase() : '?';
  }

  function initials(name) {
    var parts = (name || '').trim().split(/\s+/).filter(Boolean);
    if (!parts.length) { return '?'; }
    var out = firstChar(parts[0]);
    if (parts.length > 1) { out += firstChar(parts[parts.length - 1]); }
    return out;
  }

  function formatTime(iso) {
    var d = new Date(iso);
    if (isNaN(d.getTime())) { return ''; }
    var time = d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    if (d.toDateString() === new Date().toDateString()) { return time; }
    return d.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ', ' + time;
  }

  function snippetText(text) {
    return text.length >= SNIPPET_LENGTH ? text + '...' : text;
  }

  function replyIcon() {
    var svg = document.createElementNS(SVG_NS, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '2');
    var path = document.createElementNS(SVG_NS, 'path');
    path.setAttribute('d', 'M9 14 4 9l5-5M4 9h11a4 4 0 0 1 4 4v7');
    path.setAttribute('stroke-linecap', 'round');
    path.setAttribute('stroke-linejoin', 'round');
    svg.appendChild(path);
    return svg;
  }

  /* ---------- scrolling ---------- */
  // The thread may scroll by itself or the whole page may; use whichever one does.
  function scroller() {
    var overflow = window.getComputedStyle(thread).overflowY;
    return /(auto|scroll)/.test(overflow) ? thread : (document.scrollingElement || document.documentElement);
  }
  function isNearBottom() {
    var s = scroller();
    return s.scrollHeight - s.scrollTop - s.clientHeight < NEAR_BOTTOM_PX;
  }
  function scrollToBottom() {
    requestAnimationFrame(function () { var s = scroller(); s.scrollTop = s.scrollHeight; });
  }

  /* ---------- small bits of the page ---------- */
  function renderEmpty() {
    var text = '';
    if (roomId === null) { text = 'Join or create a room to start chatting.'; }
    else if (!loaded && pollFailed) { text = 'Could not load messages. Trying again...'; }
    else if (!loaded) { text = 'Loading messages...'; }
    else if (msgs.length === 0) { text = 'No messages yet. Say hi.'; }
    emptyEl.textContent = text;
    emptyEl.hidden = text === '';
  }

  function updateLoadRow() { loadRow.hidden = !(hasMore && msgs.length > 0); }

  function refreshForm() {
    var off = roomId === null;
    input.disabled = off;
    sendBtn.disabled = off || sending;
  }

  function updateCounter() {
    var len = input.value.length;
    counter.hidden = len === 0;
    counter.textContent = len + '/' + MAX_LENGTH;
    counter.classList.toggle('disc-counter-near', len >= MAX_LENGTH - 100);
  }

  function autosize() {
    input.style.height = 'auto';
    if (input.value) { input.style.height = Math.min(input.scrollHeight, 140) + 'px'; }
  }

  function setReply(m) {
    replyTo = { id: m.id, name: m.author_name, snippet: m.body.slice(0, SNIPPET_LENGTH) };
    replyName.textContent = m.author_name;
    replySnippet.textContent = snippetText(replyTo.snippet);
    replyBar.hidden = false;
    input.focus();
  }

  function clearReply() {
    replyTo = null;
    replyName.textContent = '';
    replySnippet.textContent = '';
    replyBar.hidden = true;
  }

  /* ---------- building one message ---------- */
  function makeAvatar(m) {
    var span = el('span', 'disc-avatar', initials(m.author_name));
    var url = members[m.author_id];
    if (url && window.RoomSyncAvatars) {
      var img = el('img', 'disc-avatar-photo');
      img.alt = '';
      window.RoomSyncAvatars.photoSrc(url).then(function (src) {
        if (src) { img.src = src; span.appendChild(img); }
      });
    }
    return span;
  }

  function buildNode(m) {
    var own = m.author_id === me;
    var group = el('div', 'disc-msg-group' + (own ? ' disc-msg-own' : ''));

    var meta = el('div', 'disc-msg-meta');
    var avatar = makeAvatar(m);
    var name = el('span', 'disc-name', m.author_name);
    var time = el('span', 'disc-time', formatTime(m.created_at));
    time.title = new Date(m.created_at).toLocaleString();
    if (own) { meta.appendChild(name); meta.appendChild(time); meta.appendChild(avatar); }
    else { meta.appendChild(avatar); meta.appendChild(name); meta.appendChild(time); }
    group.appendChild(meta);

    var bubble = el('button', 'disc-bubble', m.body);
    bubble.type = 'button';
    bubble.title = 'Reply';
    bubble.addEventListener('click', function () { setReply(m); });

    var row = el('div', 'disc-bubble-row');
    if (m.reply_to) {
      var stack = el('div', 'disc-bubble-stack');
      stack.appendChild(bubble);
      var tag = el('div', 'disc-reply-tag');
      tag.appendChild(replyIcon());
      tag.appendChild(document.createTextNode(
        'Replying to ' + m.reply_to.author_name + ': ' + snippetText(m.reply_to.snippet)
      ));
      stack.appendChild(tag);
      row.appendChild(stack);
    } else {
      row.appendChild(bubble);
    }
    group.appendChild(row);

    var actions = el('div', 'disc-actions');
    var replyBtn = el('button', 'disc-action-btn', 'Reply');
    replyBtn.type = 'button';
    replyBtn.addEventListener('click', function () { setReply(m); });
    actions.appendChild(replyBtn);
    if (own) {   // only your own messages can be deleted
      var delBtn = el('button', 'disc-action-btn disc-action-delete', 'Delete');
      delBtn.type = 'button';
      delBtn.addEventListener('click', function () { deleteMessage(m); });
      actions.appendChild(delBtn);
    }
    group.appendChild(actions);
    return group;
  }

  /* ---------- keeping the list in order ---------- */
  function findMsg(id) {
    for (var i = 0; i < msgs.length; i++) { if (msgs[i].id === id) { return msgs[i]; } }
    return null;
  }

  function insertSorted(m) {
    if (nodes[m.id]) { return false; }
    m._seq = ++localSeq;
    var node = buildNode(m);
    nodes[m.id] = node;
    var i = msgs.length;
    while (i > 0 && msgs[i - 1].id > m.id) { i--; }
    msgs.splice(i, 0, m);
    var next = msgs[i + 1];
    box.insertBefore(node, next ? nodes[next.id] : null);
    return true;
  }

  function removeNode(id) {
    var node = nodes[id];
    if (node && node.parentNode) { node.parentNode.removeChild(node); }
    delete nodes[id];
  }

  function removeMessage(id) {
    msgs = msgs.filter(function (m) { return m.id !== id; });
    removeNode(id);
  }

  function replaceMessage(m) {
    var old = nodes[m.id];
    var fresh = buildNode(m);
    if (old && old.parentNode) { old.parentNode.replaceChild(fresh, old); }
    nodes[m.id] = fresh;
    for (var i = 0; i < msgs.length; i++) {
      if (msgs[i].id === m.id) { m._seq = msgs[i]._seq; msgs[i] = m; break; }
    }
  }

  function resetList() {
    while (box.firstChild) { box.removeChild(box.firstChild); }
    msgs = [];
    nodes = {};
    members = {};
    hasMore = false;
    loaded = false;
    loadBtn.disabled = false;
  }

  /* ---------- talking to the server ---------- */
  async function loadMembers(id) {
    var r = await home.api('/rooms/' + id + '/members');
    var map = {};
    if (r.ok) { r.body.forEach(function (m) { map[m.user_id] = m.avatar_url || ''; }); }
    return map;
  }

  function handleListError(r) {
    if (r.status === 401) { return; }   // api() is already sending you to the login page
    if (r.status === 403 || r.status === 404) {   // removed from the room: same flow as the other pages
      home.showToast('You are no longer in this room.');
      document.dispatchEvent(new CustomEvent('roomsync:rooms-changed'));
      return;
    }
    if (!pollFailed) { home.showToast(home.errorText(r)); }
    pollFailed = true;
  }

  async function loadInitial() {
    var my = ++token;
    var id = roomId;
    resetList();
    busy = true;
    renderEmpty();
    var results = await Promise.all([
      home.api('/rooms/' + id + '/messages?limit=' + PAGE_SIZE),   // no before_id on the first load
      loadMembers(id)
    ]);
    if (my !== token) { return; }
    busy = false;
    var r = results[0];
    if (!r.ok) { handleListError(r); renderEmpty(); return; }
    pollFailed = false;
    members = results[1];
    r.body.forEach(function (m) { insertSorted(m); });
    hasMore = r.body.length >= PAGE_SIZE;
    loaded = true;
    updateLoadRow();
    renderEmpty();
    scrollToBottom();
  }

  async function loadEarlier() {
    if (!hasMore || busy || roomId === null || !msgs.length) { return; }
    var my = token;
    var id = roomId;
    busy = true;
    loadBtn.disabled = true;
    var r = await home.api('/rooms/' + id + '/messages?limit=' + PAGE_SIZE + '&before_id=' + msgs[0].id);
    if (my !== token) { return; }
    busy = false;
    loadBtn.disabled = false;
    if (!r.ok) { handleListError(r); return; }
    var s = scroller();
    var fromBottom = s.scrollHeight - s.scrollTop;   // keep the view where it is while older messages appear above
    r.body.forEach(function (m) { insertSorted(m); });
    hasMore = r.body.length >= PAGE_SIZE;
    updateLoadRow();
    s.scrollTop = s.scrollHeight - fromBottom;
  }

  // Compare the newest page from the server with what is on screen.
  function reconcile(latest, seqAtStart) {
    var stick = isNearBottom();
    var inLatest = {};
    latest.forEach(function (m) { inLatest[m.id] = true; });

    // More than a full page arrived since the last check: start fresh so nothing is skipped.
    if (msgs.length && latest.length >= PAGE_SIZE && latest[0].id > msgs[msgs.length - 1].id) {
      loadInitial();
      return;
    }

    // Messages inside the newest page that the server no longer has were deleted.
    var lowest = latest.length ? latest[0].id : null;
    var changed = false;
    msgs = msgs.filter(function (m) {
      var inWindow = latest.length === 0 || m.id >= lowest;
      var oldEnough = (m._seq || 0) <= seqAtStart;   // never drop a message we added after this poll started
      if (inWindow && oldEnough && !inLatest[m.id]) { removeNode(m.id); changed = true; return false; }
      return true;
    });

    var added = false;
    latest.forEach(function (m) {
      if (!nodes[m.id]) { if (insertSorted(m)) { added = true; } return; }
      var old = findMsg(m.id);
      if (old && old.reply_to_id !== m.reply_to_id) {   // the message it replied to was deleted
        replaceMessage(m);
        changed = true;
      }
    });

    if (added || changed) { renderEmpty(); }
    if (added && stick) { scrollToBottom(); }
  }

  async function poll() {
    if (roomId === null || busy || sending) { return; }
    if (!loaded) { loadInitial(); return; }
    var my = token;
    var seqAtStart = localSeq;
    busy = true;
    var r = await home.api('/rooms/' + roomId + '/messages?limit=' + PAGE_SIZE);
    if (my !== token) { return; }
    busy = false;
    if (!r.ok) { handleListError(r); return; }
    pollFailed = false;
    reconcile(r.body, seqAtStart);
  }

  function tooFastText(r) {
    var found = r.body && typeof r.body.detail === 'string' ? r.body.detail.match(/(\d+)\s*second/) : null;
    return found
      ? "You're sending too fast. Try again in " + found[1] + ' seconds.'
      : "You're sending too fast. Try again in a moment.";
  }

  async function send() {
    if (sending || roomId === null) { return; }
    var text = input.value.trim();
    if (!text) { return; }
    if (text.length > MAX_LENGTH) {
      home.showToast('Messages can be up to ' + MAX_LENGTH + ' characters.');
      return;
    }
    var my = token;
    var id = roomId;
    var payload = { body: text };
    if (replyTo) { payload.reply_to_id = replyTo.id; }
    sending = true;
    refreshForm();
    var r = await home.api('/rooms/' + id + '/messages', 'POST', payload);
    sending = false;
    refreshForm();
    if (my !== token) { return; }   // you switched rooms while this was sending

    if (r.ok) {
      input.value = '';
      clearReply();
      updateCounter();
      autosize();
      insertSorted(r.body);
      renderEmpty();
      scrollToBottom();
      poll();   // pick up what others wrote in the meantime
      return;
    }
    // Every failure keeps what you typed.
    if (r.status === 429) { home.showToast(tooFastText(r)); return; }
    if (r.status === 403 || r.status === 404) { handleListError(r); return; }
    if (r.status === 422 && replyTo) { clearReply(); poll(); }   // the message you replied to may be gone
    if (r.status !== 401) { home.showToast(home.errorText(r)); }
  }

  async function deleteMessage(m) {
    if (!window.confirm('Delete this message?')) { return; }
    var my = token;
    var r = await home.api('/messages/' + m.id, 'DELETE');
    if (my !== token) { return; }
    if (r.ok) {
      removeMessage(m.id);
      renderEmpty();
      poll();   // replies to it lose their quote
      return;
    }
    if (r.status === 404) { loadInitial(); return; }   // already gone, or no longer your room
    if (r.status !== 401) { home.showToast(home.errorText(r)); }
  }

  /* ---------- rooms ---------- */
  function switchRoom(id) {
    if (started && id === roomId) { return; }
    started = true;
    roomId = id;
    token++;
    busy = false;
    pollFailed = false;
    resetList();
    clearReply();
    input.value = '';
    updateCounter();
    autosize();
    refreshForm();
    updateLoadRow();
    renderEmpty();
    if (id !== null) { loadInitial(); }
  }

  document.addEventListener('roomsync:room', function (e) {
    var id = e.detail && typeof e.detail.id === 'number' ? e.detail.id : null;
    switchRoom(id);
  });

  /* ---------- events ---------- */
  form.addEventListener('submit', function (e) { e.preventDefault(); send(); });

  input.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {   // Enter sends, Shift+Enter is a new line
      e.preventDefault();
      send();
    } else if (e.key === 'Escape' && replyTo) {
      clearReply();
    }
  });

  input.addEventListener('input', function () { updateCounter(); autosize(); });
  replyCancel.addEventListener('click', clearReply);
  loadBtn.addEventListener('click', loadEarlier);

  // Poll every 10 seconds, but only while the tab is visible.
  setInterval(function () {
    if (document.visibilityState === 'visible') { poll(); }
  }, POLL_MS);
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible') { poll(); }
  });

  /* ---------- start ---------- */
  refreshForm();
  var current = home.currentRoomId();
  if (current !== null) { switchRoom(current); }   // otherwise wait for the "roomsync:room" event
})();