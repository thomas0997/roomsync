/* ============================================================
   ROOMSYNC - task_alert.js
   A task that is past its deadline and not ticked off gets an ALERT look:
   a red card with an "ALERT" tag on Home, an outlined chip on the Calendar.
   Ticking the task turns it off. This is only a look; nothing is sent.
   ============================================================ */
(function () {
  'use strict';

  function isPastDue(task) {
    if (!task || task.done || !task.due_at) { return false; }
    var due = Date.parse(task.due_at);
    return !isNaN(due) && due < Date.now();
  }

  // Turns the alert look on or off for a card, based on the task.
  function applyCard(card, task) {
    var on = isPastDue(task);
    card.classList.toggle('is-alert', on);
    var tag = card.querySelector('.alert-tag');
    if (on && !tag) {
      tag = document.createElement('p');
      tag.className = 'alert-tag';
      tag.textContent = '\u26A0 ALERT';
      card.insertBefore(tag, card.querySelector('.reminder-tags'));
    } else if (!on && tag) {
      tag.remove();
    }
  }

  window.RoomSyncAlert = { isPastDue: isPastDue, applyCard: applyCard };
})();
