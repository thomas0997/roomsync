/* Landing page: if you're already logged in, skip it and go to home.html. */
(function () {
  var cfg = window.ROOMSYNC;
  if (!cfg) return;

  function read(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function drop(k) { try { localStorage.removeItem(k); } catch (e) {} }

  var token = read(cfg.TOKEN_KEY);
  if (!token) return; // logged out: show the landing page as normal

  // Hide the page while we check, so a logged-in user never sees a flash of it.
  var root = document.documentElement;
  root.style.visibility = 'hidden';
  function show() { root.style.visibility = ''; }

  fetch(cfg.API_BASE + '/auth/me', { headers: { Authorization: 'Bearer ' + token } })
    .then(function (res) {
      if (res.ok) { window.location.replace('home.html'); return; }
      drop(cfg.TOKEN_KEY);
      drop(cfg.USER_KEY);
      show();
    })
    .catch(show); // server unreachable: just show the landing page
})();