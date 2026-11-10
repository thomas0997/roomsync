/* ============================================================
   ROOMSYNC — verify.js
   Opened from the emailed link: verify.html#token=...
   Nothing to fill in -- confirms the address automatically.
   POST /auth/verify { token } -> 204.
   Text is set with textContent only.
   ============================================================ */

document.addEventListener('DOMContentLoaded', function () {

  var cfg = window.ROOMSYNC;
  var titleEl = document.getElementById('verifyTitle');
  var subEl = document.getElementById('cardSub');
  var errorBox = document.getElementById('auth-error');
  var doneBox = document.getElementById('auth-done');
  var switchRow = document.getElementById('switchRow');

  function read(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }

  function addLink(href, text) {
    switchRow.textContent = '';
    var a = document.createElement('a');
    a.className = 'link-btn';
    a.href = href;
    a.textContent = text;
    switchRow.appendChild(a);
  }

  function showDeadLink(message) {
    titleEl.textContent = 'Link expired';
    subEl.textContent = '';
    errorBox.textContent = message || 'This verification link is invalid or has expired.';
    errorBox.hidden = false;
    // Requesting a new one needs an account to attach it to, so send them to log in either way.
    addLink('login.html', read(cfg.TOKEN_KEY) ? 'Go to RoomSync' : 'Log in to request a new one');
  }

  function showVerified() {
    titleEl.textContent = 'Email verified';
    subEl.textContent = '';
    doneBox.textContent = 'Your email is verified. You’ll now get deadline reminders.';
    doneBox.hidden = false;
    addLink(read(cfg.TOKEN_KEY) ? 'home.html' : 'login.html', read(cfg.TOKEN_KEY) ? 'Go to RoomSync' : 'Log in to continue');
  }

  /* ---------- take the token out of the address bar ---------- */
  var match = /(?:^#|&)token=([^&]+)/.exec(window.location.hash);
  var token = match ? decodeURIComponent(match[1]) : '';
  try { history.replaceState(null, '', window.location.pathname + window.location.search); } catch (e) { /* ignore */ }

  if (!token) { showDeadLink(); return; }

  fetch(cfg.API_BASE + '/auth/verify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token: token })
  })
    .then(function (res) {
      if (res.status === 400) { showDeadLink(); return; }
      if (res.status === 429) { showDeadLink('Too many attempts. Please wait a while and try again.'); return; }
      if (!res.ok) { showDeadLink('Something went wrong. Please try again.'); return; }
      showVerified();
    })
    .catch(function () {
      showDeadLink('Can’t reach the server. Check your connection and try again.');
    });
});
