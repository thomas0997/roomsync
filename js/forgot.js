/* ============================================================
   ROOMSYNC — forgot.js
   "Forgot password": POST /auth/forgot { email }.
   The server answers 204 whether or not the email has an account,
   so we always show the same message. Text is set with textContent.
   ============================================================ */

document.addEventListener('DOMContentLoaded', function () {

  var cfg = window.ROOMSYNC;
  var form = document.getElementById('forgotForm');
  var emailInput = document.getElementById('email');
  var errorBox = document.getElementById('auth-error');
  var doneBox = document.getElementById('auth-done');
  var submitBtn = document.getElementById('submitBtn');
  var busy = false;

  function showError(message) { errorBox.textContent = message; errorBox.hidden = false; }
  function clearError() { errorBox.textContent = ''; errorBox.hidden = true; }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    if (busy) return;
    clearError();

    var email = emailInput.value.trim();
    if (!email || email.indexOf('@') === -1) { emailInput.focus(); showError('Enter a valid email address.'); return; }

    busy = true;
    submitBtn.disabled = true;
    var idleLabel = submitBtn.textContent;
    submitBtn.textContent = 'Sending…';

    fetch(cfg.API_BASE + '/auth/forgot', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email })
    })
      .then(function (res) {
        if (res.status === 429) { showError('Too many requests. Please wait a while and try again.'); return; }
        if (res.status === 422) { showError('Enter a valid email address.'); return; }
        if (!res.ok) { showError('Something went wrong. Please try again.'); return; }
        form.hidden = true;
        doneBox.textContent = 'If an account exists for that email, a reset link is on its way. It works for 30 minutes. Check your spam folder if you don’t see it.';
        doneBox.hidden = false;
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
