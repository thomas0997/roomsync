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
  var clipBtn = byId('discClipBtn');
  var attachRow = byId('discAttachRow');
  var seenByEl = byId('discSeenBy');
  var mentionMenu = byId('discMentionMenu');
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
  var attached = [];       // clip attachments picked for the next message: [{id, name, size}]

  // @mention autocomplete (T2): open while typing "@partial" with no space in it yet.
  var mentionOpen = false;
  var mentionStart = -1;    // index of "@" in input.value
  var mentionMatches = [];  // [{id, name}], filtered room members
  var mentionActive = 0;    // index into mentionMatches that is keyboard-highlighted

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

  function escapeRegExp(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }

  // Bold the @Full Name substrings the server told us this message mentions, without innerHTML:
  // splits the text around each match and appends plain text nodes plus one <span> per mention.
  function appendBodyWithMentions(container, text, mentionIds) {
    var names = (mentionIds || [])
      .map(function (uid) { return memberName(uid); })
      .filter(Boolean)
      .sort(function (a, b) { return b.length - a.length; }); // longest first, so "Bob" can't shadow "Bobby Lee"
    if (!names.length) { container.appendChild(document.createTextNode(text)); return; }

    var pattern = new RegExp('(?<!\\w)@(?:' + names.map(escapeRegExp).join('|') + ')(?!\\w)', 'g');
    var last = 0;
    var match;
    while ((match = pattern.exec(text)) !== null) {
      if (match.index > last) { container.appendChild(document.createTextNode(text.slice(last, match.index))); }
      container.appendChild(el('span', 'disc-mention', match[0]));
      last = match.index + match[0].length;
    }
    container.appendChild(document.createTextNode(text.slice(last)));
  }

  function prettySize(n) {
    if (n < 1024) { return n + ' B'; }
    if (n < 1024 * 1024) { return Math.round(n / 1024) + ' KB'; }
    return (n / (1024 * 1024)).toFixed(1) + ' MB';
  }

  function appendAttachments(bubble, list) {
    if (!list || !list.length) { return; }
    var row = el('div', 'disc-attachments');
    list.forEach(function (a) {
      var chip = el('button', 'disc-attachment-chip');
      chip.type = 'button';
      chip.title = 'Download ' + a.name;
      chip.appendChild(el('span', 'disc-attachment-name', a.name));
      chip.appendChild(el('span', 'disc-attachment-size', prettySize(a.size)));
      chip.addEventListener('click', function (e) {
        e.stopPropagation();
        if (window.RoomSyncAttach) { window.RoomSyncAttach.download(a.file_id, a.name); }
      });
      row.appendChild(chip);
    });
    bubble.appendChild(row);
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
    if (clipBtn) { clipBtn.disabled = off; }
  }

  function updateCounter() {
    var len = input.value.length;
    counter.hidden = len === 0;
    counter.textContent = len + '/' + MAX_LENGTH;
    counter.classList.toggle('disc-counter-near', len >= MAX_LENGTH - 100);
  }

  function autosize() {
    input.style.height = 'auto';
    if (input.value) { input.style.height = Math.min(input.scrollHeight, Math.round(window.innerHeight * 0.4)) + 'px'; }
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

  /* ---------- clip attachments (picked notes for the NEXT message) ---------- */
  function renderAttachRow() {
    if (!attachRow) { return; }
    attachRow.textContent = '';
    attachRow.hidden = attached.length === 0;
    attached.forEach(function (f) {
      var chip = el('span', 'disc-attach-chip');
      chip.appendChild(el('span', 'disc-attach-chip-name', f.name));
      var x = el('button', 'disc-attach-chip-remove', '×');
      x.type = 'button';
      x.setAttribute('aria-label', 'Remove ' + f.name);
      x.addEventListener('click', function () {
        attached = attached.filter(function (a) { return a.id !== f.id; });
        renderAttachRow();
      });
      chip.appendChild(x);
      attachRow.appendChild(chip);
    });
  }

  async function openClipPicker() {
    if (roomId === null || !window.RoomSyncAttach) { return; }
    var picked = await window.RoomSyncAttach.pickFiles({
      roomId: roomId,
      selected: attached.map(function (f) { return f.id; }),
      max: 5
    });
    if (picked === null) { return; }  // cancelled
    attached = picked;
    renderAttachRow();
  }

  if (clipBtn) { clipBtn.addEventListener('click', openClipPicker); }

  /* ---------- @mention autocomplete (Messenger-style: type "@", click a member) ---------- */
  function mentionAvatar(uid, name) {
    var span = el('span', 'disc-avatar', initials(name));
    var url = memberAvatar(uid);
    if (url && window.RoomSyncAvatars) {
      var img = el('img', 'disc-avatar-photo');
      img.alt = '';
      window.RoomSyncAvatars.photoSrc(url).then(function (src) {
        if (src) { img.src = src; span.appendChild(img); }
      });
    }
    return span;
  }

  function closeMentionMenu() {
    mentionOpen = false;
    mentionStart = -1;
    mentionMatches = [];
    mentionActive = 0;
    if (mentionMenu) { mentionMenu.hidden = true; mentionMenu.textContent = ''; }
  }

  function insertMention(name) {
    if (mentionStart < 0) { return; }
    var caret = input.selectionStart;
    var before = input.value.slice(0, mentionStart);
    var after = input.value.slice(caret);
    var inserted = '@' + name + ' ';
    input.value = before + inserted + after;
    var pos = before.length + inserted.length;
    input.focus();
    input.setSelectionRange(pos, pos);
    closeMentionMenu();
    updateCounter();
    autosize();
  }

  function renderMentionMenu() {
    if (!mentionMenu) { return; }
    mentionMenu.textContent = '';
    if (!mentionMatches.length) { mentionMenu.hidden = true; return; }
    mentionMatches.forEach(function (person, i) {
      var item = el('button', 'disc-mention-item' + (i === mentionActive ? ' disc-mention-item-active' : ''));
      item.type = 'button';
      item.setAttribute('role', 'option');
      item.appendChild(mentionAvatar(person.id, person.name));
      item.appendChild(el('span', 'disc-mention-item-name', person.name));
      // mousedown (not click) fires before the textarea's blur, so the insert happens
      // while the dropdown's choice is still visible and the textarea keeps focus.
      item.addEventListener('mousedown', function (e) { e.preventDefault(); insertMention(person.name); });
      mentionMenu.appendChild(item);
    });
    mentionMenu.hidden = false;
  }

  // Looks at the text just before the caret for an unfinished "@query" (no space in it yet)
  // and opens/updates/closes the dropdown to match, Messenger-style.
  function updateMentionMenu() {
    if (!mentionMenu || roomId === null) { closeMentionMenu(); return; }
    var caret = input.selectionStart;
    var before = input.value.slice(0, caret);
    var match = before.match(/(?:^|\s)@([^\s@]*)$/);
    if (!match) { closeMentionMenu(); return; }
    var query = match[1].toLowerCase();
    var start = caret - match[1].length - 1;   // index of "@"
    var people = Object.keys(members)
      .map(function (uid) { return { id: Number(uid), name: memberName(Number(uid)) }; })
      .filter(function (p) { return p.name && p.id !== me; });   // mentioning yourself isn't useful
    var matches = people.filter(function (p) { return p.name.toLowerCase().indexOf(query) !== -1; });
    if (!matches.length) { closeMentionMenu(); return; }
    mentionOpen = true;
    mentionStart = start;
    mentionMatches = matches.slice(0, 8);
    mentionActive = Math.min(mentionActive, mentionMatches.length - 1);
    renderMentionMenu();
  }

  /* ---------- unread / seen-by ---------- */
  function markRead() {
    if (roomId === null) { return; }
    home.api('/rooms/' + roomId + '/messages/read', 'POST').then(function (r) {
      if (r.ok && home.refreshDiscussionBadge) { home.refreshDiscussionBadge(); }
    });
  }

  function renderSeenBy(list) {
    if (!seenByEl) { return; }
    if (!list || !list.length) { seenByEl.hidden = true; seenByEl.textContent = ''; return; }
    var names = list.map(function (p) { return p.name; });
    var text = names.length === 1 ? names[0]
      : names.length === 2 ? names[0] + ' and ' + names[1]
      : names.slice(0, -1).join(', ') + ', and ' + names[names.length - 1];
    seenByEl.textContent = 'Seen by ' + text;
    seenByEl.hidden = false;
  }

  function refreshSeenBy() {
    if (roomId === null) { return; }
    var id = roomId;
    home.api('/rooms/' + id + '/messages/seen').then(function (r) {
      if (id !== roomId) { return; }
      if (r.ok) { renderSeenBy(r.body); }
    });
  }

  /* ---------- building one message ---------- */
  function makeAvatar(m) {
    var span = el('span', 'disc-avatar', initials(m.author_name));
    var url = memberAvatar(m.author_id);
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
    var mentionsMe = me !== null && (m.mentions || []).indexOf(me) !== -1;
    var group = el('div', 'disc-msg-group' + (own ? ' disc-msg-own' : '') + (mentionsMe ? ' disc-msg-mentions-me' : ''));

    var meta = el('div', 'disc-msg-meta');
    var avatar = makeAvatar(m);
    var name = el('span', 'disc-name', m.author_name);
    var time = el('span', 'disc-time', formatTime(m.created_at));
    time.title = new Date(m.created_at).toLocaleString();
    if (own) { meta.appendChild(name); meta.appendChild(time); meta.appendChild(avatar); }
    else { meta.appendChild(avatar); meta.appendChild(name); meta.appendChild(time); }
    group.appendChild(meta);

    // One bubble holds both the quote (on top) and the message text, so they always stay together.
    var bubble = el('button', 'disc-bubble' + (m.reply_to ? ' disc-bubble-has-quote' : ''));
    bubble.type = 'button';
    bubble.title = 'Reply';
    bubble.addEventListener('click', function () { setReply(m); });
    if (m.reply_to) {
      var quote = el('span', 'disc-quote');
      quote.appendChild(replyIcon());
      quote.appendChild(el('span', 'disc-quote-text',
        'Replying to ' + m.reply_to.author_name + ': ' + snippetText(m.reply_to.snippet)));
      bubble.appendChild(quote);
    }
    var textEl = el('span', 'disc-text');
    appendBodyWithMentions(textEl, m.body, m.mentions);
    bubble.appendChild(textEl);
    appendAttachments(bubble, m.attachments);

    var row = el('div', 'disc-bubble-row');
    row.appendChild(bubble);
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
    renderSeenBy(null);
  }

  /* ---------- talking to the server ---------- */
  async function loadMembers(id) {
    var r = await home.api('/rooms/' + id + '/members');
    var map = {};
    if (r.ok) { r.body.forEach(function (m) { map[m.user_id] = { avatar_url: m.avatar_url || '', name: m.name }; }); }
    return map;
  }

  function memberAvatar(uid) { var m = members[uid]; return m ? m.avatar_url : ''; }
  function memberName(uid) { var m = members[uid]; return m ? m.name : ''; }

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
    markRead();
    refreshSeenBy();
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
    if (added) { markRead(); }
    refreshSeenBy();
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
    if (attached.length) { payload.file_ids = attached.map(function (f) { return f.id; }); }
    sending = true;
    refreshForm();
    var r = await home.api('/rooms/' + id + '/messages', 'POST', payload);
    sending = false;
    refreshForm();
    if (my !== token) { return; }   // you switched rooms while this was sending

    if (r.ok) {
      input.value = '';
      clearReply();
      closeMentionMenu();
      attached = [];
      renderAttachRow();
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
    var firstOpen = !started;   // the moment the Discussion tab itself is opened, not just a room switch
    started = true;
    roomId = id;
    if (firstOpen && home.markAllDiscussionsRead) { home.markAllDiscussionsRead(); }
    token++;
    busy = false;
    pollFailed = false;
    resetList();
    clearReply();
    closeMentionMenu();
    attached = [];
    renderAttachRow();
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
    if (mentionOpen && mentionMatches.length) {   // the dropdown takes over arrow/enter/escape while open
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        mentionActive = (mentionActive + 1) % mentionMatches.length;
        renderMentionMenu();
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        mentionActive = (mentionActive - 1 + mentionMatches.length) % mentionMatches.length;
        renderMentionMenu();
        return;
      }
      if (e.key === 'Enter' || e.key === 'Tab') {
        e.preventDefault();
        insertMention(mentionMatches[mentionActive].name);
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        closeMentionMenu();
        return;
      }
    }
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {   // Enter sends, Shift+Enter is a new line
      e.preventDefault();
      send();
    } else if (e.key === 'Escape' && replyTo) {
      clearReply();
    }
  });

  input.addEventListener('input', function () { updateCounter(); autosize(); updateMentionMenu(); });
  input.addEventListener('click', updateMentionMenu);   // moving the caret by clicking can also start/end a mention
  input.addEventListener('blur', function () { closeMentionMenu(); });
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