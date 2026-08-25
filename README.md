# roomsync

Peer-driven deadline tracker for classroom rooms. Frontend-only build for Intro to Web Programming: rooms, TODOs with type-based priority (Exam, Quiz, Case Study, Seatwork, Assignment), calendar, notes, and admin approval workflow. HTML, CSS, JavaScript.

Backend/database is a separate personal project, not part of this class scope.

## Structure

```
index.html          entry point — "ADMIN"/"ADMIN" login page
pages/
  login.html         log in card, quick login + OAuth buttons (visual only)
  home.html          room feed
css/
  styles.css         main stylesheet
  styles_login.css   login page only
js/
  rooms.js           room list / create / join
assets/
  IMG_1783.jpg
```

## Auth

Login is hardcoded per instructions — no real auth logic. Focus stays on design and frontend integration.

## Status

Early build. `pages/home.html` and `js/rooms.js` are still placeholders. Login page is built and styled.

**Known issue:** `pages/login.html` currently links `../assets/styles_login.css`, but the file lives at `css/styles_login.css` — fix the path or the page loads unstyled.

## Local dev

No build step. Open `index.html` in a browser, or serve the folder with any static server (e.g. VS Code Live Server).

## License

MIT — see `LICENSE`.
