/* ============================================================
   ROOMSYNC — config.js
   Where the API lives. In production the site and the API share
   one address, so API_BASE is empty (same origin). When a page is
   opened with a dev server on another port (Live Server 5500), the
   API is the local backend on port 8000.
   ============================================================ */
window.ROOMSYNC = {
  API_BASE: ['5500', '5501', '3000'].indexOf(location.port) !== -1 ? 'http://localhost:8000' : '',
  TOKEN_KEY: 'roomsync_token',
  USER_KEY: 'roomsync_user'
};