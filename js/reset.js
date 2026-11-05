/* ============================================================
   ROOMSYNC — reset.js
   Opened from the emailed link: reset.html#token=...
   The secret is read from the URL fragment, then removed from the
   address bar. POST /auth/reset { token, new_password } -> 204.
   Text is set with textContent only.
   ============================================================ */

document.addEventListener('DOMContentLoaded', function () {

  var cfg = window.ROOMSYNC;
  var form = document.getElementById('resetForm');
  var pwInput = document.getElementById('password');
  var pw2Input = document.getElementById('password2');
  var pwToggle = document.getElementById('pwToggle');
  var errorBox = document.getElementById('auth-error');
  var doneBox = document.getElementById('auth-done');
  var submitBtn = document.getElementById('submitBtn');
  var switchRow = document.getElementById('switchRow');
  var busy = false;

  /* ---------- take the token out of the address bar ---------- */
  var match = /(?:^#|&)token=([^&]+)/.exec(window.location.hash);
  var token = match ? decodeURIComponent(match[1]) : '';
  try { history.replaceState(null, '', window.location.pathname + window.location.search); } catch (e) { /* ignore */ }

  function showError(message) { errorBox.textContent = message; errorBox.hidden = false; }
  function clearError() { errorBox.textContent = ''; errorBox.hidden = true; }

  function showDeadLink() {
    form.hidden = true;
    showError('This reset link is invalid or has expired.');
    switchRow.textContent = '';
    var a = document.createElement('a');
    a.className = 'link-btn';
    a.href = 'forgot.html';
    a.textContent = 'Get a new link';
    switchRow.appendChild(a);
  }

  if (!token) { showDeadLink(); return; }

  pwToggle.addEventListener('click', function () {
    var show = pwInput.type === 'password';
    pwInput.type = show ? 'text' : 'password';
    pw2Input.type = show ? 'text' : 'password';
    pwToggle.textContent = show ? 'Hide' : 'Show';
    pwToggle.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
    pwToggle.setAttribute('aria-pressed', String(show));
  });

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    if (busy) return;
    clearError();

    var pw = pwInput.value;
    if (pw.length < 8) { pwInput.focus(); showError('Password must be at least 8 characters.'); return; }
    if (pw !== pw2Input.value) { pw2Input.focus(); showError('The two passwords don’t match.'); return; }

    busy = true;
    submitBtn.disabled = true;
    var idleLabel = submitBtn.textContent;
    submitBtn.textContent = 'Changing…';

    fetch(cfg.API_BASE + '/auth/reset', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: token, new_password: pw })
    })
      .then(function (res) {
        if (res.status === 400) { showDeadLink(); return; }
        if (res.status === 429) { showError('Too many attempts. Please wait a while and try again.'); return; }
        if (res.status === 422) { showError('Choose a password of 8 to 72 characters.'); return; }
        if (!res.ok) { showError('Something went wrong. Please try again.'); return; }
        try { localStorage.removeItem(cfg.TOKEN_KEY); localStorage.removeItem(cfg.USER_KEY); } catch (e) { /* ignore */ }
        form.hidden = true;
        doneBox.textContent = 'Your password was changed. You’ve been logged out everywhere, so log in with the new one.';
        doneBox.hidden = false;
        switchRow.textContent = '';
        var a = document.createElement('a');
        a.className = 'link-btn';
        a.href = 'login.html';
        a.textContent = 'Go to log in';
        switchRow.appendChild(a);
      })
      .catch(function () {
        showError('Can’t reach the server. Check your connection and try again.');
      })
      .then(function () {
        busy = false;
        submitBtn.disabled = false;
        submitBtn.textContent = idleLabel;
      });
  });
});
