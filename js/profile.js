/* ============================================================
   ROOMSYNC — profile.js
   Status selector (with custom text option), Edit Profile / Log out
   stubs. No backend yet — status only updates this page's own
   sidebar footer locally, doesn't broadcast to other users.
   ============================================================ */

document.addEventListener('DOMContentLoaded', function () {

  var statusSelect = document.getElementById('statusSelect');
  var statusCustomInput = document.getElementById('statusCustomInput');
  var sidebarStatusText = document.getElementById('sidebarStatusText');

  function applyStatus() {
    if (statusSelect.value === 'Custom') {
      statusCustomInput.hidden = false;
      var customValue = statusCustomInput.value.trim();
      if (sidebarStatusText) sidebarStatusText.textContent = customValue || 'Custom';
    } else {
      statusCustomInput.hidden = true;
      if (sidebarStatusText) sidebarStatusText.textContent = statusSelect.value;
    }
  }

  if (statusSelect) {
    statusSelect.addEventListener('change', applyStatus);
  }
  if (statusCustomInput) {
    statusCustomInput.addEventListener('input', function () {
      if (sidebarStatusText) sidebarStatusText.textContent = statusCustomInput.value.trim() || 'Custom';
    });
  }

  var editProfileBtn = document.getElementById('editProfileBtn');
  if (editProfileBtn) {
    editProfileBtn.addEventListener('click', function () {
      // TODO: wire up real inline editing once the backend exists
      console.log('Edit Profile clicked — hook up editable fields here.');
    });
  }

  var logoutBtn = document.getElementById('logoutBtn');
  if (logoutBtn) {
    logoutBtn.addEventListener('click', function () {
      var confirmed = confirm('Log out of RoomSync?');
      if (confirmed) {
        window.location.href = 'login.html';
      }
    });
  }

  /* ---------- Rooms list: "+N more" expands, then collapses back ---------- */
  var moreRoomsBtn = document.getElementById('profileRoomMore');
  if (moreRoomsBtn) {
    var overflowItems = document.querySelectorAll('.profile-room-overflow-item');
    var overflowCount = overflowItems.length;
    var expanded = false;
    moreRoomsBtn.addEventListener('click', function () {
      expanded = !expanded;
      overflowItems.forEach(function (item) { item.hidden = !expanded; });
      var nameEl = moreRoomsBtn.querySelector('.profile-room-name');
      var roleEl = moreRoomsBtn.querySelector('.profile-room-role');
      if (expanded) {
        nameEl.textContent = 'Show less';
        roleEl.textContent = 'Hide extra rooms';
      } else {
        nameEl.textContent = '+' + overflowCount + ' more';
        roleEl.textContent = 'Show all rooms';
      }
    });
  }

});