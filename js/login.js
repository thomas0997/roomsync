/* ============================================================
   ROOMSYNC — login.js
   Hardcoded check: email "admin" + password "admin" -> home.html
   No real auth. Per instructions, this is visual/flow only.
   ============================================================ */

document.addEventListener('DOMContentLoaded', function () {

  var emailField = document.getElementById('email');
  var passwordField = document.getElementById('password');
  var loginBtn = document.getElementById('loginBtn');
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

  loginBtn.addEventListener('click', tryLogin);

  // Allow pressing Enter in either field to submit
  [emailField, passwordField].forEach(function (field) {
    field.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') tryLogin();
    });
  });

  // Quick login shortcuts skip the admin/admin check entirely
  if (quickAdminBtn) {
    quickAdminBtn.addEventListener('click', function () {
      window.location.href = 'home.html';
    });
  }
  if (quickMemberBtn) {
    quickMemberBtn.addEventListener('click', function () {
      window.location.href = 'home.html';
    });
  }

});