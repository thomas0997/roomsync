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

});