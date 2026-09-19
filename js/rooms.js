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

  /* ---------- Task complete toggle (click anywhere on the task bar to strike through) ---------- */
  var reminderCards = document.querySelectorAll('.reminder-card');
  reminderCards.forEach(function (card) {
    var bullet = card.querySelector('.reminder-bullet');
    card.addEventListener('click', function () {
      var nowComplete = card.classList.toggle('is-complete');
      if (bullet) {
        bullet.classList.toggle('is-complete', nowComplete);
        bullet.setAttribute('aria-pressed', nowComplete ? 'true' : 'false');
      }
    });
  });

  /* ---------- Online users list + empty-state (per room) ---------- */
  var roomMembers = {
    'The Bozos': [
      { name: 'Thomas Franco', initials: 'TF', online: true },
      { name: 'Mary Rose Bayani', initials: 'MB', online: true },
      { name: 'Daniel Rodriguez', initials: 'DR', online: false },
      { name: 'Sean Dayrit', initials: 'SD', online: true },
      { name: 'Charlie Kim', initials: 'CK', online: false },
      { name: 'Hans Santos', initials: 'HS', online: true },
      { name: 'Phem Cruz', initials: 'PC', online: false }
    ],
    'Auron Inc.': [
      { name: 'Julia Santos', initials: 'JS', online: true },
      { name: 'Marco Reyes', initials: 'MR', online: false }
    ],
    'CYB201': [
      { name: 'Kevin Tan', initials: 'KT', online: true },
      { name: 'Bea Fernandez', initials: 'BF', online: true },
      { name: 'Miguel Cruz', initials: 'MC', online: false }
    ]
  };

  var ONLINE_USERS_MAX = 5;

  function renderOnlineUsers(roomName, expanded) {
    var list = document.getElementById('onlineUsersList');
    if (!list) return;
    var members = roomMembers[roomName] || [];
    var visible = expanded ? members : members.slice(0, ONLINE_USERS_MAX);
    var overflowCount = members.length - visible.length;

    var html = visible.map(function (m) {
      return '<li class="online-user">' +
        '<span class="online-user-avatar">' + m.initials +
        '<span class="online-dot' + (m.online ? ' online-dot-active' : '') + '"></span>' +
        '</span>' +
        '<span class="online-user-name">' + m.name + '</span>' +
        '</li>';
    }).join('');

    if (overflowCount > 0) {
      html += '<li><button type="button" class="online-user-more" data-room="' + roomName + '">+' + overflowCount + ' other' + (overflowCount === 1 ? '' : 's') + '</button></li>';
    } else if (expanded && members.length > ONLINE_USERS_MAX) {
      html += '<li><button type="button" class="online-user-more" data-room="' + roomName + '" data-collapse="true">Show less</button></li>';
    }

    list.innerHTML = html;

    var moreBtn = list.querySelector('.online-user-more');
    if (moreBtn) {
      moreBtn.addEventListener('click', function () {
        renderOnlineUsers(moreBtn.dataset.room, moreBtn.dataset.collapse !== 'true');
      });
    }
  }

  function updateRoomEmptyState(roomName) {
    // Structure (headers, controls, dates, legend, input bar) always stays visible —
    // this just flags the room on <body> so CSS can hide the actual data items
    // (task cards, chips, files, messages, submissions) when the room isn't The Bozos.
    document.body.setAttribute('data-current-room', roomName);
  }

  function switchRoom(roomName) {
    renderOnlineUsers(roomName);
    updateRoomEmptyState(roomName);
  }

  // Set the default room's state on load
  updateRoomEmptyState('The Bozos');
  renderOnlineUsers('The Bozos');

  // Desktop's persistent room list (sidebar) didn't have a click handler before — add one
  document.querySelectorAll('.room-buttons .room-pill').forEach(function (pill) {
    pill.addEventListener('click', function () {
      var roomName = pill.querySelector('.room-name').textContent.trim();
      document.querySelectorAll('.room-buttons .room-pill').forEach(function (p) {
        p.classList.toggle('room-pill-active', p === pill);
      });
      document.querySelectorAll('[data-room-name]').forEach(function (el) { el.textContent = roomName; });
      switchRoom(roomName);
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
      document.querySelectorAll('.room-buttons .room-pill').forEach(function (pill) {
        var pillName = pill.querySelector('.room-name').textContent.trim();
        pill.classList.toggle('room-pill-active', pillName === roomName);
      });

      switchRoom(roomName);
      closeAllRoomDropdowns();
    });
  });

  document.addEventListener('click', function (e) {
    if (!e.target.closest('.room-switcher')) closeAllRoomDropdowns();
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeAllRoomDropdowns();
  });

  /* ---------- New TODO buttons — opens the shared modal ---------- */
  var todoButtons = [
    document.getElementById('newTodoBtnDesktop'),
    document.getElementById('newTodoBtnTablet'),
    document.getElementById('newTodoBtnMobile')
  ];
  var todoModalOverlay = document.getElementById('todoModalOverlay');
  var todoModalForm = document.getElementById('todoModalForm');
  var todoModalRoom = document.getElementById('todoModalRoom');
  var todoModalClose = document.getElementById('todoModalClose');
  var todoModalCancel = document.getElementById('todoModalCancel');

  function showToast(message) {
    var toast = document.createElement('div');
    toast.className = 'abt-toast';
    toast.textContent = message;
    document.body.appendChild(toast);
    requestAnimationFrame(function () { toast.classList.add('abt-toast-show'); });
    setTimeout(function () {
      toast.classList.remove('abt-toast-show');
      setTimeout(function () { toast.remove(); }, 250);
    }, 2200);
  }

  function openTodoModal() {
    if (!todoModalOverlay) return;
    if (todoModalRoom) {
      var currentRoom = document.querySelector('[data-room-name]');
      if (currentRoom) todoModalRoom.value = currentRoom.textContent.trim();
    }
    todoModalOverlay.hidden = false;
  }
  function closeTodoModal() {
    if (!todoModalOverlay) return;
    todoModalOverlay.hidden = true;
  }

  todoButtons.forEach(function (btn) {
    if (btn) btn.addEventListener('click', openTodoModal);
  });
  if (todoModalClose) todoModalClose.addEventListener('click', closeTodoModal);
  if (todoModalCancel) todoModalCancel.addEventListener('click', closeTodoModal);
  if (todoModalOverlay) {
    todoModalOverlay.addEventListener('click', function (e) {
      if (e.target === todoModalOverlay) closeTodoModal();
    });
  }
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && todoModalOverlay && !todoModalOverlay.hidden) closeTodoModal();
  });
  if (todoModalForm) {
    todoModalForm.addEventListener('submit', function (e) {
      e.preventDefault();
      // TODO: actually create the TODO once there's a backend — for now just confirm and close
      console.log('New TODO submitted (not persisted anywhere yet).');
      closeTodoModal();
      showToast('TODO created!');
      todoModalForm.reset();
    });
  }

  /* ---------- Settings button — routes to settings.html ---------- */
  var settingsBtn = document.getElementById('settingsBtn');
  if (settingsBtn) {
    settingsBtn.addEventListener('click', function () {
      window.location.href = 'settings.html';
    });
  }

  /* ---------- Calendar "+N More" popover ---------- */
  document.querySelectorAll('.cal-chip-more').forEach(function (btn) {
    btn.addEventListener('click', function (e) {
      e.stopPropagation();
      var popover = btn.nextElementSibling;
      var isOpen = !popover.hidden;
      document.querySelectorAll('.cal-more-popover').forEach(function (p) { p.hidden = true; });
      if (popover) popover.hidden = isOpen;
    });
  });
  document.addEventListener('click', function () {
    document.querySelectorAll('.cal-more-popover').forEach(function (p) { p.hidden = true; });
  });

});