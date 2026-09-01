# roomsync

Peer-driven deadline tracker for classroom rooms. Frontend-only build for Intro to Web Programming: rooms, TODOs with type-based priority (Exam, Quiz, Case Study, Activity, Seatwork, Assignment), calendar, notes, and admin approval workflow. HTML, CSS, JavaScript — no framework, no build step.

Backend/database is a separate personal project, not part of this class scope.

## Structure

```
index.html            entry point — hardcoded login page
pages/
  login.html           log in card, quick login + OAuth buttons (visual only)
  home.html            room feed — Board view, responsive sidebar/nav, task legend
css/
  styles.css           main stylesheet (mobile-first, tablet 768px+, desktop 1200px+)
  styles_login.css      login page only
js/
  rooms.js             sidebar/hamburger toggle, Grid/Scroll view toggle, task-complete toggle
assets/
  roomsync_logo.png     brand logo
  TheBozos_Logo.jpg     room icon
  Auroninc_Logo.jpg     room icon
  CYB201_Logo.jpg       room icon
  IMG_1783.jpg
```

## Responsive behavior

Three distinct layouts driven by the same markup:

- **Mobile (< 768px):** black top bar with hamburger menu -> slide-in drawer nav. Floating room pill, bottom action bar (Today / Search / New TODO).
- **Tablet (768-1199px):** collapsed icon-only sidebar rail; click it to expand into full labeled nav (overlay). Room switcher as a floating pill.
- **Desktop (>= 1200px):** persistent full-width sidebar (logo, room list; nav removed here since the top bar carries nav links instead), black top bar with text nav right-aligned, New TODO button beside the page title.

Task-priority colors (Exam, Quiz, Case Study, Activity, Seatwork, Assignment) are defined once as CSS custom properties in `:root` and reused across badges and the legend, so a color only needs to change in one place.

## Interactivity

- Sidebar / hamburger drawer open-close (`rooms.js`)
- Grid <-> Scroll board view toggle
- Click a task's circle to mark it complete (fills green, strikes through the title)
- New TODO button is wired to a click handler (`console.log` placeholder) - swap in the real modal/form when it's built

## Auth

Login is hardcoded per instructions - no real auth logic. Focus stays on design and frontend integration.

## Status

`pages/login.html` and `pages/home.html` are both built and styled across all three breakpoints. Room content (task list, room list) is static/hardcoded - no dynamic data yet.

**Still placeholder:**
- Room avatar images (`TheBozos_Logo.jpg`, `Auroninc_Logo.jpg`, `CYB201_Logo.jpg`) - swap for real room photos/icons when available
- New TODO button has no modal/form yet - logs to console only
- `calendar.html`, `notes.html`, `discussion.html`, `approve.html`, `about.html` are linked from nav but not yet built

## Local dev

No build step. Open `index.html` in a browser, or serve the folder with any static server (e.g. VS Code Live Server).

## License

MIT - see `LICENSE`.