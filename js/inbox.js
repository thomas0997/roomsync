/* ============================================================
   ROOMSYNC — inbox.js
   The Inbox page: private messages between room-mates (docs/api-contract.md, "Inbox").
   - folders: Inbox, Sent, Archived; open a message to read it (that marks it read)
   - write a new message to a classmate by email, reply, archive, delete (only your copy), block a sender
   Everything a person wrote (names, subjects, messages) is set with textContent and shown as plain text.
   Links in messages are NOT clickable on purpose (phishing risk). Messages are not end-to-end encrypted.
   Needs: js/sidebar_rooms.js (window.RoomSyncHome) and js/inbox_badge.js loaded first.
   ============================================================ */
(function () {
  'use strict';

  var home = window.RoomSyncHome;
  var list = document.getElementById('inboxList');
  if (!home || !list) { return; }

  var PAGE = 50;
  var COLORS = ['#0073ec', '#7a2b2b', '#1e8e4e', '#8a5a00', '#6a3fb5', '#007c89', '#b0306a'];

  var folder = 'inbox';
  var messages = [];       // what the list shows
  var hasMore = false;
  var openId = null;
  var openMsg = null;
  var loadCounter = 0;
  var cfg = window.ROOMSYNC || {};

  function byId(id) { return document.getElementById(id); }
  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) { node.className = cls; }
    if (text !== undefined) { node.textContent = text; }
    return node;
  }
  function myId() {
    try { return JSON.parse(localStorage.getItem(cfg.USER_KEY || 'roomsync_user') || 'null').id; } catch (e) { return null; }
  }
  function initial(name) { var c = Array.from((name || '?').trim()); return c.length ? c[0].toUpperCase() : '?'; }
  function colorFor(name) {
    var sum = 0;
    for (var i = 0; i < name.length; i++) { sum = (sum + name.charCodeAt(i)) % 997; }
    return COLORS[sum % COLORS.length];
  }
  function avatar(name, small) {
    var a = el('span', 'inbox-av' + (small ? ' inbox-av-sm' : ''), initial(name));
    a.style.background = colorFor(name);
    a.setAttribute('aria-hidden', 'true');
    return a;
  }
  var MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  function clock(d) {
    var h = d.getHours();
    return (h % 12 || 12) + ':' + String(d.getMinutes()).padStart(2, '0') + ' ' + (h >= 12 ? 'PM' : 'AM');
  }
  function shortTime(iso) {
    var d = new Date(iso), now = new Date();
    var days = Math.round((new Date(now.getFullYear(), now.getMonth(), now.getDate()) -
                           new Date(d.getFullYear(), d.getMonth(), d.getDate())) / 86400000);
    if (days <= 0) { return clock(d); }
    if (days === 1) { return 'Yesterday'; }
    return MONTHS[d.getMonth()] + ' ' + d.getDate();
  }
  function longTime(iso) {
    var d = new Date(iso);
    return MONTHS[d.getMonth()] + ' ' + d.getDate() + ', ' + d.getFullYear() + ' · ' + clock(d);
  }
  // The person on the other end of this message, from my point of view.
  function other(m) { return m.from_user_id === myId() ? m.to_name : m.from_name; }
  function otherId(m) { return m.from_user_id === myId() ? m.to_user_id : m.from_user_id; }
  function isMine(m) { return m.from_user_id === myId(); }

  function say(text) { var n = byId('inboxEmpty'); n.textContent = text || ''; n.hidden = !text; }

  /* ---------- the list ---------- */
  function row(m) {
    var unread = !isMine(m) && !m.read_at;
    var item = el('button', 'inbox-row' + (unread ? ' inbox-unread' : '') + (m.id === openId ? ' inbox-selected' : ''));
    item.type = 'button';
    item.dataset.id = String(m.id);
    var who = folder === 'sent' ? 'To: ' + m.to_name : m.from_name;
    item.appendChild(avatar(folder === 'sent' ? m.to_name : m.from_name));
    var text = el('span', 'inbox-row-text');
    var top = el('span', 'inbox-row-top');
    top.appendChild(el('span', 'inbox-row-name', who));
    top.appendChild(el('span', 'inbox-row-time', shortTime(m.created_at)));
    text.appendChild(top);
    text.appendChild(el('span', 'inbox-row-subject', m.subject));
    text.appendChild(el('span', 'inbox-row-preview', m.body.replace(/\s+/g, ' ').slice(0, 90)));
    item.appendChild(text);
    item.addEventListener('click', function () { openMessage(m.id); });
    return item;
  }

  function renderList() {
    list.textContent = '';
    messages.forEach(function (m) { list.appendChild(row(m)); });
    if (hasMore) {
      var more = el('button', 'inbox-more', 'Load older messages');
      more.type = 'button';
      more.addEventListener('click', function () { load(true); });
      list.appendChild(more);
    }
    if (!messages.length) {
      say(folder === 'inbox' ? 'Nothing here yet. Messages from your classmates will show up here.'
        : folder === 'sent' ? "You haven't sent any messages yet."
        : 'Nothing archived.');
    } else { say(''); }
  }

  async function load(older, silent) {
    var mine = ++loadCounter;
    var path = '/inbox?folder=' + folder + '&limit=' + PAGE;
    if (older && messages.length) { path += '&before_id=' + messages[messages.length - 1].id; }
    if (!older && !silent) { say('Loading...'); }
    var r = await home.api(path);
    if (mine !== loadCounter) { return; }
    if (!r.ok) { if (r.status !== 401) { say("Couldn't load your messages."); home.showToast(home.errorText(r)); } return; }
    messages = older ? messages.concat(r.body) : r.body;
    hasMore = r.body.length === PAGE;
    renderList();
  }

  function setFolder(name) {
    folder = name;
    openId = null; openMsg = null;
    document.querySelectorAll('.inbox-tab').forEach(function (b) {
      var on = b.dataset.folder === name;
      b.classList.toggle('notes-filter-active', on);
      b.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    showReader(null);
    messages = [];
    load(false);
  }

  /* ---------- reading ---------- */
  function showReader(m) {
    openMsg = m;
    var box = byId('inboxReader');
    box.textContent = '';
    byId('inboxWrap').classList.toggle('inbox-open', !!m);
    if (!m) {
      box.appendChild(el('p', 'inbox-hint', 'Select a message to read it, or press New message.'));
      return;
    }
    var back = el('button', 'inbox-back', '‹ Back');
    back.type = 'button';
    back.addEventListener('click', function () { openId = null; showReader(null); renderList(); });
    box.appendChild(back);
    box.appendChild(el('h2', 'inbox-subject', m.subject));
    var who = el('div', 'inbox-who');
    who.appendChild(avatar(other(m)));
    var meta = el('div', 'inbox-who-text');
    meta.appendChild(el('div', 'inbox-who-name', isMine(m) ? 'To ' + m.to_name : m.from_name));
    meta.appendChild(el('div', 'inbox-who-sub', (isMine(m) ? 'From you' : 'To you') + ' · ' + longTime(m.created_at)));
    who.appendChild(meta);
    box.appendChild(who);
    box.appendChild(el('div', 'inbox-body', m.body));   // pre-wrap + textContent: plain text, links stay dead

    var actions = el('div', 'inbox-actions');
    var replyBtn = el('button', 'abt-btn-submit', 'Reply');
    replyBtn.type = 'button';
    actions.appendChild(replyBtn);
    if (!isMine(m)) {
      var arch = el('button', 'abt-btn-reset', m.archived ? 'Move to Inbox' : 'Archive');
      arch.type = 'button';
      arch.addEventListener('click', function () { archive(m, !m.archived); });
      actions.appendChild(arch);
    }
    var del = el('button', 'abt-btn-reset', 'Delete');
    del.type = 'button';
    del.addEventListener('click', function () { remove(m); });
    actions.appendChild(del);
    if (!isMine(m)) {
      var block = el('button', 'inbox-link-danger', 'Block ' + m.from_name);
      block.type = 'button';
      block.addEventListener('click', function () { blockSender(m); });
      actions.appendChild(block);
    }
    box.appendChild(actions);

    var reply = el('div', 'inbox-reply');
    reply.hidden = true;
    var ta = el('textarea');
    ta.id = 'inboxReplyText';
    ta.maxLength = 2000;
    ta.rows = 4;
    ta.placeholder = 'Write your reply';
    ta.setAttribute('aria-label', 'Your reply');
    var err = el('p', 'abt-form-error');
    err.hidden = true;
    err.setAttribute('role', 'alert');
    var send = el('button', 'abt-btn-submit', 'Send reply');
    send.type = 'button';
    send.addEventListener('click', function () { sendReply(m, ta, err, send); });
    reply.appendChild(ta);
    reply.appendChild(err);
    reply.appendChild(send);
    box.appendChild(reply);
    replyBtn.addEventListener('click', function () { reply.hidden = false; replyBtn.hidden = true; ta.focus(); });

    box.appendChild(el('p', 'inbox-note', 'Only you and ' + (isMine(m) ? m.to_name : m.from_name) +
      ' can open this message. It is not end-to-end encrypted.'));
  }

  async function openMessage(id) {
    openId = id;
    var r = await home.api('/inbox/' + id);
    if (openId !== id) { return; }
    if (!r.ok) {
      if (r.status === 404) { home.showToast('That message is no longer available.'); load(false, true); showReader(null); }
      else if (r.status !== 401) { home.showToast(home.errorText(r)); }
      return;
    }
    for (var i = 0; i < messages.length; i++) { if (messages[i].id === id) { messages[i] = r.body; } }
    showReader(r.body);
    renderList();
    if (window.RoomSyncInbox) { window.RoomSyncInbox.refresh(); }
  }

  /* ---------- actions ---------- */
  async function sendReply(m, ta, err, btn) {
    var text = ta.value.trim();
    err.hidden = true;
    if (!text) { err.textContent = 'Write something first.'; err.hidden = false; return; }
    btn.disabled = true;
    var r = await home.api('/inbox/' + m.id + '/reply', 'POST', { body: text });
    btn.disabled = false;
    if (!r.ok) { if (r.status !== 401) { err.textContent = home.errorText(r); err.hidden = false; } return; }
    home.showToast('Reply sent.');
    ta.value = '';
    showReader(m);
    if (folder === 'sent') { load(false, true); }
  }

  async function archive(m, want) {
    var r = await home.api('/inbox/' + m.id, 'PATCH', { archived: want });
    if (!r.ok) { if (r.status !== 401) { home.showToast(home.errorText(r)); } return; }
    home.showToast(want ? 'Archived.' : 'Moved back to your Inbox.');
    openId = null; showReader(null);
    load(false, true);
    if (window.RoomSyncInbox) { window.RoomSyncInbox.refresh(); }
  }

  async function remove(m) {
    if (!window.confirm('Delete this message? It only disappears for you; ' + other(m) + ' keeps their copy.')) { return; }
    var r = await home.api('/inbox/' + m.id, 'DELETE');
    if (!r.ok && r.status !== 404) { if (r.status !== 401) { home.showToast(home.errorText(r)); } return; }
    home.showToast('Message deleted.');
    openId = null; showReader(null);
    load(false, true);
    if (window.RoomSyncInbox) { window.RoomSyncInbox.refresh(); }
  }

  async function blockSender(m) {
    if (!window.confirm('Block ' + m.from_name + '? They can still try to write to you, but you will never see their messages, and they are not told.')) { return; }
    var r = await home.api('/inbox/blocks/' + m.from_user_id, 'PUT');
    if (!r.ok) { if (r.status !== 401) { home.showToast(home.errorText(r)); } return; }
    home.showToast(m.from_name + ' is blocked.');
  }

  /* ---------- compose ---------- */
  var overlay = byId('composeOverlay');
  var toInput = byId('composeTo');
  var subjectInput = byId('composeSubject');
  var bodyInput = byId('composeBody');
  var counter = byId('composeCount');
  var composeErr = byId('composeError');
  var sendBtn = byId('composeSend');

  function updateCounter() { counter.textContent = bodyInput.value.length + ' / 2000'; }
  function openCompose() {
    composeErr.hidden = true;
    overlay.hidden = false;
    toInput.focus();
  }
  function closeCompose() { overlay.hidden = true; }

  async function send(e) {
    e.preventDefault();
    composeErr.hidden = true;
    var to = toInput.value.trim(), subject = subjectInput.value.trim(), body = bodyInput.value.trim();
    if (!to || !subject || !body) { composeErr.textContent = 'Fill in the email, a subject and a message.'; composeErr.hidden = false; return; }
    sendBtn.disabled = true;
    var r = await home.api('/inbox', 'POST', { to_email: to, subject: subject, body: body });
    sendBtn.disabled = false;
    if (!r.ok) {
      if (r.status === 401) { return; }
      composeErr.textContent = r.status === 422 && !(r.body && typeof r.body.detail === 'string')
        ? 'Check the email address, subject (up to 120 characters) and message (up to 2000).'
        : home.errorText(r);
      composeErr.hidden = false;
      return;
    }
    closeCompose();
    byId('composeForm').reset();
    updateCounter();
    home.showToast('Message sent.');
    if (folder === 'sent') { load(false, true); }
  }

  /* ---------- wiring ---------- */
  document.querySelectorAll('.inbox-tab').forEach(function (b) {
    b.addEventListener('click', function () { setFolder(b.dataset.folder); });
  });
  byId('inboxNew').addEventListener('click', openCompose);
  byId('inboxNewSmall').addEventListener('click', openCompose);
  byId('composeClose').addEventListener('click', closeCompose);
  byId('composeCancel').addEventListener('click', closeCompose);
  overlay.addEventListener('click', function (e) { if (e.target === overlay) { closeCompose(); } });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !overlay.hidden) { closeCompose(); } });
  bodyInput.addEventListener('input', updateCounter);
  byId('composeForm').addEventListener('submit', send);
  document.addEventListener('roomsync:inbox-unread', function (e) {
    if (e.detail && e.detail.grew && folder === 'inbox') { load(false, true); }   // a new message arrived: refresh the list
  });

  updateCounter();
  showReader(null);
  load(false);
})();
