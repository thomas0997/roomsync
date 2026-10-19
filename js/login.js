/* ============================================================
   ROOMSYNC — login.js
   Hardcoded check: email "admin" + password "admin" -> home.html
   No real auth. Per instructions, this is visual/flow only.
   ============================================================ */

document.addEventListener('DOMContentLoaded', function () {

  var form = document.getElementById('loginForm');
  var emailField = document.getElementById('email');
  var passwordField = document.getElementById('password');
  var pwToggle = document.getElementById('pwToggle');
  var errorMsg = document.getElementById('login-error');
  var quickAdminBtn = document.getElementById('quickAdmin');
  var quickMemberBtn = document.getElementById('quickMember');

  function tryLogin() {
    var email = emailField.value.trim().toLowerCase();
    var password = passwordField.value;

    if (email === 'admin' && password === 'admin') {
      window.location.href = 'home.html';
    } else {
      errorMsg.hidden = false;
    }
  }

  // Submit by button click or by pressing Enter in either field
  form.addEventListener('submit', function (e) {
    e.preventDefault();
    tryLogin();
  });

  // Show / hide password
  pwToggle.addEventListener('click', function () {
    var show = passwordField.type === 'password';
    passwordField.type = show ? 'text' : 'password';
    pwToggle.textContent = show ? 'Hide' : 'Show';
    pwToggle.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
    pwToggle.setAttribute('aria-pressed', String(show));
  });

  // Quick login shortcuts skip the admin/admin check entirely
  quickAdminBtn.addEventListener('click', function () {
    window.location.href = 'home.html';
  });
  quickMemberBtn.addEventListener('click', function () {
    window.location.href = 'home.html';
  });

});