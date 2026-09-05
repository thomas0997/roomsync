/* ============================================================
   ROOMSYNC — settings.js
   Handles toggle switches, theme select, leave room, delete
   account confirmation, and the save-changes flow.
   ============================================================ */

document.addEventListener('DOMContentLoaded', function () {

  var form = document.getElementById('settingsForm');
  var deleteBtn = document.getElementById('deleteAccountBtn');
  var leaveButtons = document.querySelectorAll('.btn-leave-room');

  // Leave Room — confirm before acting (destructive-ish action)
  leaveButtons.forEach(function (btn) {
    btn.addEventListener('click', function () {
      var roomName = btn.closest('.settings-row').querySelector('.settings-row-label').textContent;
      var confirmed = confirm('Leave "' + roomName + '"? You can rejoin later with an invite.');
      if (confirmed) {
        // TODO: wire up to the real leave-room endpoint once the backend exists
        btn.closest('.settings-row').style.opacity = '0.4';
        btn.disabled = true;
        btn.textContent = 'Left';
      }
    });
  });

  // Delete Account — requires typed confirmation, since this is permanent
  if (deleteBtn) {
    deleteBtn.addEventListener('click', function () {
      var typed = prompt('This permanently removes you from every room. Type DELETE to confirm.');
      if (typed === 'DELETE') {
        // TODO: wire up to the real delete-account endpoint once the backend exists
        alert('Account deletion confirmed. (Not yet wired to a real backend.)');
      }
    });
  }

  // Save Changes
  if (form) {
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      // TODO: persist toggle states + theme selection to the real backend once it exists
      var saveBtn = form.querySelector('.btn-save-changes');
      var originalText = saveBtn.textContent;
      saveBtn.textContent = 'Saved ✓';
      setTimeout(function () { saveBtn.textContent = originalText; }, 1500);
    });
  }

  // Hamburger/sidebar toggle is now handled by rooms.js (shared with home.html)

});