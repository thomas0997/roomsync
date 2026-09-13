/* ============================================================
   ROOMSYNC — approve.js
   Approve/Reject buttons fade the card out and remove it from
   the pending list. No backend yet, so this doesn't persist —
   refreshing brings all submissions back.
   ============================================================ */

document.addEventListener('DOMContentLoaded', function () {

  var list = document.getElementById('apprList');
  var emptyState = document.getElementById('apprEmpty');

  function checkEmpty() {
    var remaining = list.querySelectorAll('.appr-card:not(.appr-card-resolved)').length;
    if (remaining === 0 && emptyState) {
      emptyState.hidden = false;
    }
  }

  function resolveCard(card, verb) {
    card.classList.add('appr-card-resolved');
    // TODO: send the real approve/reject decision to the backend once it exists
    console.log(verb + ':', card.querySelector('.appr-card-title').textContent);
    setTimeout(function () {
      card.style.transition = 'opacity 200ms ease, max-height 300ms ease, margin 300ms ease, padding 300ms ease';
      card.style.opacity = '0';
      card.style.maxHeight = '0';
      card.style.marginBottom = '0';
      card.style.paddingTop = '0';
      card.style.paddingBottom = '0';
      card.style.overflow = 'hidden';
      setTimeout(function () {
        card.remove();
        checkEmpty();
      }, 320);
    }, 150);
  }

  list.querySelectorAll('.appr-btn-approve').forEach(function (btn) {
    btn.addEventListener('click', function () {
      resolveCard(btn.closest('.appr-card'), 'Approved');
    });
  });

  list.querySelectorAll('.appr-btn-reject').forEach(function (btn) {
    btn.addEventListener('click', function () {
      resolveCard(btn.closest('.appr-card'), 'Rejected');
    });
  });

});