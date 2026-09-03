/* ============================================================
   ROOMSYNC — rooms.js
   Handles: mobile hamburger drawer, tablet sidebar expand-on-click,
   and the desktop Grid/Scroll board view toggle.
   ============================================================ */

document.addEventListener('DOMContentLoaded', function () {

  var sidebar = document.getElementById('sidebar');
  var overlay = document.getElementById('sidebarOverlay');
  var hamburgerBtn = document.getElementById('hamburgerBtn');

  function isTabletWidth() {
    return window.innerWidth >= 768 && window.innerWidth < 1200;
  }
  function isMobileWidth() {
    return window.innerWidth < 768;
  }

  function openSidebar() {
    if (isTabletWidth()) {
      sidebar.classList.add('expanded');
    } else {
      sidebar.classList.add('open');
    }
    overlay.classList.add('open');
    if (hamburgerBtn) {
      hamburgerBtn.classList.add('open');
      hamburgerBtn.setAttribute('aria-expanded', 'true');
    }
  }

  function closeSidebar() {
    sidebar.classList.remove('open');
    sidebar.classList.remove('expanded');
    overlay.classList.remove('open');
    if (hamburgerBtn) {
      hamburgerBtn.classList.remove('open');
      hamburgerBtn.setAttribute('aria-expanded', 'false');
    }
  }

  function toggleSidebar() {
    var isOpen = sidebar.classList.contains('open') || sidebar.classList.contains('expanded');
    if (isOpen) {
      closeSidebar();
    } else {
      openSidebar();
    }
  }

  // Mobile hamburger button
  if (hamburgerBtn) {
    hamburgerBtn.addEventListener('click', toggleSidebar);
  }

  // Tablet: clicking the collapsed icon rail expands it
  sidebar.addEventListener('click', function (e) {
    if (isTabletWidth() && !sidebar.classList.contains('expanded')) {
      // Only expand if the click landed on the rail itself, not a link navigating away
      var link = e.target.closest('a');
      if (!link) {
        openSidebar();
      }
    }
  });

  // Clicking the overlay closes either drawer
  overlay.addEventListener('click', closeSidebar);

  // Escape key closes
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeSidebar();
  });

  // Reset state on resize across breakpoints so nothing gets stuck open
  window.addEventListener('resize', function () {
    closeSidebar();
  });

  /* ---------- Grid / Scroll board view toggle (desktop) ---------- */
  var layoutButtons = document.querySelectorAll('.layout-btn');
  var boards = document.querySelectorAll('.board');

  layoutButtons.forEach(function (btn) {
    btn.addEventListener('click', function () {
      var view = btn.getAttribute('data-view');

      layoutButtons.forEach(function (b) { b.classList.remove('layout-btn-active'); });
      btn.classList.add('layout-btn-active');

      boards.forEach(function (board) {
        board.classList.toggle('view-scroll', view === 'scroll');
      });
    });
  });

  /* ---------- Task complete toggle (click the circle to strike through) ---------- */
  var reminderBullets = document.querySelectorAll('.reminder-bullet');
  reminderBullets.forEach(function (bullet) {
    bullet.addEventListener('click', function () {
      var card = bullet.closest('.reminder-card');
      var nowComplete = bullet.classList.toggle('is-complete');
      if (card) card.classList.toggle('is-complete', nowComplete);
      bullet.setAttribute('aria-pressed', nowComplete ? 'true' : 'false');
    });
  });

  /* ---------- Room switcher (mobile + tablet pill) ---------- */
  var roomPillButtons = [
    document.getElementById('roomPillBtnMobile'),
    document.getElementById('roomPillBtnTablet')
  ].filter(Boolean);
  var roomDropdowns = [
    document.getElementById('roomDropdownMobile'),
    document.getElementById('roomDropdownTablet')
  ].filter(Boolean);

  function closeAllRoomDropdowns() {
    roomDropdowns.forEach(function (dd) { dd.hidden = true; });
    roomPillButtons.forEach(function (btn) { btn.setAttribute('aria-expanded', 'false'); });
  }

  roomPillButtons.forEach(function (btn, i) {
    btn.addEventListener('click', function (e) {
      e.stopPropagation();
      var thisDropdown = roomDropdowns[i];
      var isOpen = !thisDropdown.hidden;
      closeAllRoomDropdowns();
      if (!isOpen) {
        thisDropdown.hidden = false;
        btn.setAttribute('aria-expanded', 'true');
      }
    });
  });

  // Selecting a room updates both pill instances (mobile + tablet) so they stay in sync,
  // and marks the chosen room active in whichever dropdown was used.
  document.querySelectorAll('.room-dropdown-item').forEach(function (item) {
    item.addEventListener('click', function () {
      var roomName = item.dataset.room;
      var avatarClass = item.dataset.avatarClass || '';
      var avatarSrc = item.dataset.avatarSrc || '';

      document.querySelectorAll('[data-room-name]').forEach(function (el) { el.textContent = roomName; });
      document.querySelectorAll('[data-room-avatar]').forEach(function (el) {
        el.className = 'room-avatar' + (avatarClass ? ' ' + avatarClass : '');
        if (avatarSrc) {
          el.src = avatarSrc;
          el.alt = roomName;
        }
      });

      document.querySelectorAll('.room-dropdown-item').forEach(function (el) {
        el.classList.toggle('active', el.dataset.room === roomName);
      });

      closeAllRoomDropdowns();
    });
  });

  document.addEventListener('click', function (e) {
    if (!e.target.closest('.room-switcher')) closeAllRoomDropdowns();
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeAllRoomDropdowns();
  });

  /* ---------- New TODO buttons (all three breakpoints) — placeholder handler ---------- */
  var todoButtons = [
    document.getElementById('newTodoBtnDesktop'),
    document.getElementById('newTodoBtnTablet'),
    document.getElementById('newTodoBtnMobile')
  ];
  todoButtons.forEach(function (btn) {
    if (btn) {
      btn.addEventListener('click', function () {
        // TODO: replace with the real "new TODO" modal/form once built
        console.log('New TODO clicked — hook up the create-TODO modal here.');
      });
    }
  });

  /* ---------- Settings button — routes to settings.html ---------- */
  var settingsBtn = document.getElementById('settingsBtn');
  if (settingsBtn) {
    settingsBtn.addEventListener('click', function () {
      window.location.href = 'settings.html';
    });
  }

});