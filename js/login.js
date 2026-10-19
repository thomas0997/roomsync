/* ============================================================
   ROOMSYNC — login.js
   Real log in + sign up against the API (POST /auth/login,
   POST /auth/signup). On success the token is kept in
   localStorage and the user goes to home.html.
   Rule: text from the server is shown with textContent only.
   ============================================================ */

document.addEventListener('DOMContentLoaded', function () {

  var cfg = window.ROOMSYNC;
  var form = document.getElementById('authForm');
  var nameField = document.getElementById('nameField');
  var nameInput = document.getElementById('name');
  var emailInput = document.getElementById('email');
  var pwInput = document.getElementById('password');
  var pwToggle = document.getElementById('pwToggle');
  var pwHint = document.getElementById('pwHint');
  var errorBox = document.getElementById('auth-error');
  var submitBtn = document.getElementById('submitBtn');
  var tabLogin = document.getElementById('tabLogin');
  var tabSignup = document.getElementById('tabSignup');
  var cardSub = document.getElementById('cardSub');
  var switchRow = document.getElementById('switchRow');

  var mode = 'login';
  var busy = false;

  /* ---------- storage (wrapped: it can throw in private windows) ---------- */
  function store(key, value) { try { localStorage.setItem(key, value); return true; } catch (e) { return false; } }
  function read(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }
  function drop(key) { try { localStorage.removeItem(key); } catch (e) { /* ignore */ } }

  /* ---------- UI helpers ---------- */
  function showError(message) {
    errorBox.textContent = message;
    errorBox.hidden = false;
  }
  function clearError() {
    errorBox.textContent = '';
    errorBox.hidden = true;
  }

  function setMode(next) {
    mode = next;
    var signup = mode === 'signup';
    clearError();

    tabLogin.classList.toggle('active', !signup);
    tabSignup.classList.toggle('active', signup);
    tabLogin.setAttribute('aria-selected', String(!signup));
    tabSignup.setAttribute('aria-selected', String(signup));

    nameField.hidden = !signup;
    pwHint.hidden = !signup;
    pwInput.setAttribute('autocomplete', signup ? 'new-password' : 'current-password');
    pwInput.placeholder = signup ? 'Choose a password' : 'Your password';
    submitBtn.textContent = signup ? 'Create account' : 'Log in';
    cardSub.textContent = signup
      ? 'Make an account, then create or join a room with an invite code.'
      : 'Welcome back. Pick up where your room left off.';
    document.title = signup ? 'RoomSync | Sign up' : 'RoomSync | Log in';

    switchRow.textContent = '';
    var text = document.createTextNode(signup ? 'Already have an account? ' : 'New to RoomSync? ');
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'link-btn';
    btn.id = 'switchBtn';
    btn.textContent = signup ? 'Log in' : 'Create an account';
    btn.addEventListener('click', function () { setMode(signup ? 'login' : 'signup'); });
    switchRow.appendChild(text);
    switchRow.appendChild(btn);
  }

  tabLogin.addEventListener('click', function () { setMode('login'); });
  tabSignup.addEventListener('click', function () { setMode('signup'); });
  setMode(window.location.hash === '#signup' ? 'signup' : 'login');

  pwToggle.addEventListener('click', function () {
    var show = pwInput.type === 'password';
    pwInput.type = show ? 'text' : 'password';
    pwToggle.textContent = show ? 'Hide' : 'Show';
    pwToggle.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
    pwToggle.setAttribute('aria-pressed', String(show));
  });

  /* ---------- turn an API error into a friendly sentence ---------- */
  function friendlyError(status, body) {
    var detail = body && body.detail;
    if (status === 401) return 'Incorrect email or password.';
    if (status === 409) return 'That email already has an account. Try logging in instead.';
    if (status === 429) return 'Too many attempts. Please wait a minute and try again.';
    if (status === 422) {
      if (Array.isArray(detail) && detail.length) {
        var field = String((detail[0].loc || []).slice(-1)[0] || '');
        if (field === 'email') return 'Enter a valid email address.';
        if (field === 'password') return mode === 'signup' ? 'Password must be at least 8 characters.' : 'Enter your password.';
        if (field === 'name') return 'Enter your name.';
      }
      return 'Please check your details and try again.';
    }
    if (typeof detail === 'string' && detail) return detail;
    return 'Something went wrong. Please try again.';
  }

  /* ---------- submit ---------- */
  function validate() {
    var email = emailInput.value.trim();
    var password = pwInput.value;
    if (mode === 'signup' && !nameInput.value.trim()) { nameInput.focus(); return 'Enter your name.'; }
    if (!email || email.indexOf('@') === -1) { emailInput.focus(); return 'Enter a valid email address.'; }
    if (!password) { pwInput.focus(); return mode === 'signup' ? 'Choose a password.' : 'Enter your password.'; }
    if (mode === 'signup' && password.length < 8) { pwInput.focus(); return 'Password must be at least 8 characters.'; }
    return '';
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    if (busy) return;
    clearError();

    var problem = validate();
    if (problem) { showError(problem); return; }

    var payload = { email: emailInput.value.trim(), password: pwInput.value };
    if (mode === 'signup') payload.name = nameInput.value.trim();

    busy = true;
    submitBtn.disabled = true;
    var idleLabel = submitBtn.textContent;
    submitBtn.textContent = mode === 'signup' ? 'Creating account…' : 'Logging in…';

    fetch(cfg.API_BASE + (mode === 'signup' ? '/auth/signup' : '/auth/login'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
      .then(function (res) {
        return res.json().catch(function () { return null; }).then(function (body) {
          return { ok: res.ok, status: res.status, body: body };
        });
      })
      .then(function (r) {
        if (!r.ok) { showError(friendlyError(r.status, r.body)); return; }
        if (!store(cfg.TOKEN_KEY, r.body.access_token)) {
          showError('Your browser is blocking storage, so we can’t keep you logged in. Turn off private mode and try again.');
          return;
        }
        store(cfg.USER_KEY, JSON.stringify(r.body.user));
        window.location.href = 'home.html';
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

  /* ---------- already logged in? check the token, then skip the form ---------- */
  var existing = read(cfg.TOKEN_KEY);
  if (existing) {
    fetch(cfg.API_BASE + '/auth/me', { headers: { Authorization: 'Bearer ' + existing } })
      .then(function (res) {
        if (res.ok) { window.location.href = 'home.html'; return; }
        drop(cfg.TOKEN_KEY);
        drop(cfg.USER_KEY);
      })
      .catch(function () { /* server unreachable: stay on the form */ });
  }
});