# roomsync

Peer-driven deadline tracker for classroom rooms. Frontend-only build for Intro to Web Programming: rooms, TODOs with type-based priority (Exam, Quiz, Case Study, Seatwork, Assignment), calendar, notes, and admin approval workflow. HTML, CSS, JavaScript.

Backend/database is a separate personal project, not part of this class scope.

## Structure

```
index.html          entry point — login, hardcoded admin/admin per prof
pages/
  register.html
  rooms.html         room list / create / join
  home.html          room feed, ranked by type + deadline (home + dashboard merged)
  calendar.html      month grid
  notes.html         shared notes
  approve.html       admin approval queue
css/
  style.css          uniform stylesheet — everything except auth
  auth.css           login/register pages only
js/
  data.js            shared fake in-memory data — swap for real API later
  rooms.js
  todos.js           home feed + priority ranking
  calendar.js
  notes.js
  approve.js
assets/
  images/
  icons/
```

## Auth

Login is hardcoded as `admin` / `admin` per instructions — no JS auth logic, no auth.js. The form on `index.html` just navigates to `pages/rooms.html`. Focus stays on design and frontend integration.

## Status

Scaffold only. Each JS file has `TODO Week N` comments marking what to build and when — see the 10-week plan doc.

## Local dev

No build step. Open `index.html` in a browser, or serve the folder with any static server (e.g. VS Code Live Server).
