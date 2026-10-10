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


  // ---------- Weekly board: show/hide empty days + Task colors (browser-only) ----------
  var RT = window.RoomSyncTasks;
  var appearance = null;
  document.querySelectorAll('.settings-card legend').forEach(function (lg) {
    if (lg.textContent.trim().toLowerCase() === 'appearance') appearance = lg.parentNode;
  });

  if (RT && appearance) {
    // Empty-days toggle row (after Theme)
    var themeRow = appearance.querySelector('.settings-row-last');
    if (themeRow) themeRow.classList.remove('settings-row-last');
    var row = document.createElement('div');
    row.className = 'settings-row settings-row-last';
    row.innerHTML =
      '<div class="settings-row-text">' +
      '<div class="settings-row-label">Show empty days</div>' +
      '<div class="settings-row-sub">Show a card for days with no tasks in the weekly schedule, so free days stand out</div>' +
      '</div>' +
      '<label class="settings-toggle"><input type="checkbox" id="showEmptyDays" aria-label="Show empty days"><span class="settings-toggle-track"></span></label>';
    appearance.appendChild(row);
    var emptyBox = row.querySelector('input');
    emptyBox.checked = RT.getEmptyDays();
    emptyBox.addEventListener('change', function () { RT.setEmptyDays(emptyBox.checked); });

    // Task colors card
    var card = document.createElement('fieldset');
    card.className = 'settings-card';
    card.innerHTML =
      '<legend>Task colors</legend>' +
      '<div id="tcList"></div>' +
      '<div class="settings-row tc-add-row">' +
      '<div class="settings-row-text"><div class="settings-row-label">Add custom type</div>' +
      '<div class="settings-row-sub">Create your own task type with its own color</div></div>' +
      '<div class="tc-controls">' +
      '<input type="text" id="tcNewName" class="tc-name-input" maxlength="20" placeholder="Type name" aria-label="Custom type name">' +
      '<input type="color" id="tcNewColor" class="tc-color" value="#0073ec" aria-label="Custom type color">' +
      '<button type="button" id="tcAdd" class="tc-btn tc-btn-primary">Add</button>' +
      '</div></div>' +
      '<div class="settings-row settings-row-last">' +
      '<div class="settings-row-text"><div class="settings-row-label">Reset colors</div>' +
      '<div class="settings-row-sub">Restore the six built-in types to their original colors</div></div>' +
      '<button type="button" id="tcReset" class="tc-btn">Reset to defaults</button>' +
      '</div>';
    appearance.parentNode.insertBefore(card, appearance.nextSibling);

    var list = card.querySelector('#tcList');
    function renderList() {
      list.innerHTML = '';
      RT.all().forEach(function (t) {
        var r = document.createElement('div');
        r.className = 'settings-row';
        var txt = document.createElement('div');
        txt.className = 'settings-row-text tc-name';
        var dot = document.createElement('span');
        dot.className = 'tc-dot';
        dot.style.background = t.color;
        var lbl = document.createElement('span');
        lbl.className = 'settings-row-label';
        lbl.textContent = t.name;
        txt.appendChild(dot); txt.appendChild(lbl);
        var ctl = document.createElement('div');
        ctl.className = 'tc-controls';
        var inp = document.createElement('input');
        inp.type = 'color'; inp.className = 'tc-color'; inp.value = t.color.toLowerCase();
        inp.setAttribute('aria-label', t.name + ' color');
        inp.addEventListener('input', function () { RT.setColor(t.id, inp.value); dot.style.background = inp.value; });
        ctl.appendChild(inp);
        if (!t.builtin) {
          var rm = document.createElement('button');
          rm.type = 'button'; rm.className = 'tc-btn'; rm.textContent = 'Remove';
          rm.addEventListener('click', function () { RT.remove(t.id); renderList(); });
          ctl.appendChild(rm);
        }
        r.appendChild(txt); r.appendChild(ctl);
        list.appendChild(r);
      });
    }
    renderList();

    var nameIn = card.querySelector('#tcNewName');
    var colorIn = card.querySelector('#tcNewColor');
    function addType() {
      if (!nameIn.value.trim()) { nameIn.focus(); return; }
      RT.add(nameIn.value, colorIn.value);
      nameIn.value = '';
      renderList();
    }
    card.querySelector('#tcAdd').addEventListener('click', addType);
    nameIn.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); addType(); } });
    card.querySelector('#tcReset').addEventListener('click', function () { RT.reset(); renderList(); });
  }

  // Hamburger/sidebar toggle is now handled by rooms.js (shared with home.html)

});