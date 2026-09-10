/* ============================================================
   ROOMSYNC — discussion.js
   Click any message bubble to set up a reply. Sending appends a
   new message bubble as the current user. No backend yet, so
   nothing persists across a reload.
   ============================================================ */

document.addEventListener('DOMContentLoaded', function () {

  var thread = document.getElementById('discThread');
  var replyIndicator = document.getElementById('discReplyIndicator');
  var replyNameEl = document.getElementById('discReplyName');
  var replyCancelBtn = document.getElementById('discReplyCancel');
  var form = document.getElementById('discInputForm');
  var input = document.getElementById('discMessageInput');

  var activeReplyName = null;

  function setReply(name) {
    activeReplyName = name;
    replyNameEl.textContent = name;
    replyIndicator.hidden = false;
    input.focus();
  }

  function clearReply() {
    activeReplyName = null;
    replyIndicator.hidden = true;
  }

  // Click any message bubble to reply to it
  document.querySelectorAll('.disc-bubble').forEach(function (bubble) {
    bubble.addEventListener('click', function () {
      var name = bubble.dataset.replyName;
      if (name) setReply(name);
    });
  });

  if (replyCancelBtn) {
    replyCancelBtn.addEventListener('click', clearReply);
  }

  // Sending a message appends it to the thread as the current user
  if (form) {
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var text = input.value.trim();
      if (!text) return;

      var group = document.createElement('div');
      group.className = 'disc-msg-group disc-msg-own';

      var now = new Date();
      var hours = now.getHours();
      var minutes = now.getMinutes().toString().padStart(2, '0');
      var ampm = hours >= 12 ? 'PM' : 'AM';
      var hour12 = hours % 12 || 12;
      var timeStr = hour12 + ':' + minutes + ' ' + ampm;

      var replyHtml = '';
      if (activeReplyName) {
        replyHtml =
          '<div class="disc-reply-tag">' +
          '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 14 4 9l5-5M4 9h11a4 4 0 0 1 4 4v7" stroke-linecap="round" stroke-linejoin="round"/></svg>' +
          'Replying to ' + activeReplyName +
          '</div>';
      }

      group.innerHTML =
        '<div class="disc-msg-meta">' +
        '<span class="disc-name">Thomas Franco</span>' +
        '<span class="disc-time">' + timeStr + '</span>' +
        '<span class="disc-avatar">TF</span>' +
        '</div>' +
        '<div class="disc-bubble-row">' +
        '<div class="disc-bubble-stack">' +
        '<button class="disc-bubble" type="button" data-reply-name="Thomas Franco" data-reply-text="' + text.replace(/"/g, '&quot;') + '">' + text + '</button>' +
        replyHtml +
        '</div>' +
        '</div>';

      // Insert before the typing indicator / seen-by line, so new messages land above them
      var seenBy = thread.querySelector('.disc-seenby');
      if (seenBy) {
        thread.insertBefore(group, seenBy);
      } else {
        thread.appendChild(group);
      }

      group.querySelector('.disc-bubble').addEventListener('click', function () {
        setReply('Thomas Franco');
      });

      input.value = '';
      clearReply();
      group.scrollIntoView({ behavior: 'smooth', block: 'end' });
    });
  }

});