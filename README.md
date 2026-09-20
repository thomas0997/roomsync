# RoomSync

A peer-approval-gated deadline tracker, built around rooms instead of classrooms.

RoomSync organizes deadlines the way students actually work: not one calendar per class, but "rooms" that map to whoever a person actually coordinates with (a friend group, a study team, an org). Every task carries a type (Exam, Quiz, Case Study, Activity, Seatwork, Assignment) with type-weighted priority, and nothing gets accepted into the room without a peer approving it first.

> Status: Frontend complete. This repository is currently a fully responsive, fully interactive HTML, CSS, and JavaScript frontend with no backend. A backend (authentication, persistence, real multi-user sync) is planned as an ongoing side project beyond the original course scope. See Roadmap below.

## Features

- Home: a week-by-week task board ("This Week," "Next Week," "Week After"), grouped by day and color-coded by task type
- Calendar: full month grid with color-coded event chips, an expandable "+N More" popover per day, and a dedicated exam schedule board
- Notes: a shared file space with Docs, Sheets, and Files, sortable filters, and a Grid/Scroll layout toggle
- Discussion: a per-room chat thread with reply-to-message threading and a live typing indicator
- Approve: the peer-approval queue for accepting or rejecting pending submissions, filterable by type, with a decision history log
- Profile and Settings: account details, room memberships, activity stats, notification preferences, and a customizable status
- About: team info, platform stats, and a feedback and contact form
- Room switching: every page reflects whichever room is active, including a live "online now" member list with click-to-view profile
- Fully responsive across mobile, tablet, and desktop, with breakpoint-specific navigation (bottom action bar, collapsible icon rail, persistent sidebar)

## Tech Stack

Vanilla HTML5, CSS3, and JavaScript (ES5+). No frameworks, no build step, no dependencies. Every interaction (task completion, room switching, modals, filtering, form validation) is hand-written DOM manipulation, by design, to keep the project framework-agnostic and easy to hand off to a future backend of any stack.

## Project Structure

```
roomsync/
├── pages/          home, calendar, notes, discussion, approve, profile, settings, about, login
├── css/            styles.css (shared design system), styles_login.css
├── js/             one script per page, plus rooms.js (shared: sidebar, room switching, modals)
├── assets/         logos, avatars, icons
└── README.md
```

## Design System

A single locked token set drives every page. Colors, spacing, radii, and typography are centralized in css/styles.css, so the whole app reads as one consistent product rather than a set of separate pages. Task-type colors are fixed by design decision and used consistently across the board view, calendar, and approval queue.

| Type | Color |
|---|---|
| Exam | #DF0000 |
| Quiz | #F2B84B |
| Case Study | #C79ADB |
| Activity | #F2795A |
| Seatwork | #009CDF |
| Assignment | #8F8F97 |

## Getting Started

No build step required; it is static HTML.

```bash
git clone https://github.com/<your-org>/roomsync.git
cd roomsync
# Open pages/login.html in a browser, or serve the folder with any static server:
npx serve .
```

## Roadmap

RoomSync was built as a course capstone with a deliberately frontend-only scope. Development continues past that scope as an independent side project.

- [ ] Backend API (authentication, persistence, real-time sync)
- [ ] Database-backed rooms, tasks, and approval history
- [ ] Real multi-user Discussion (WebSocket-based)
- [ ] File upload and storage for Notes
- [ ] Role-based access (admin-only Approve view)
- [ ] Customizable task types and colors per room, for non-student use cases

## Team

Built by Thomas Franco, Mary Rose Bayani, and Daniel Rodriguez. Section CYB-201, School of Computing, Holy Angel University.

Course: Introduction to Web Programming. Instructor: Dr. Raquel B. Rivera.

## License

See LICENSE.