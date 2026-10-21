# RoomSync API contract (source of truth)

Base URL: `http://localhost:8000` locally. In production the API and the frontend are served from the same domain, `https://roomsync.me` (LIVE since Oct 19: Render + Neon, deployed from `feat/backend-skeleton`). The server also serves the frontend files (`/pages`, `/css`, `/js`, `/assets`), and `/` redirects to `/pages/index.html`. Bodies are JSON unless a section says multipart. Auth = header `Authorization: Bearer <token>`.
Errors look like `{"detail": "message"}`. Status codes: 401 not logged in, 403 not allowed, 404 not found, 409 conflict (including limits), 413 file too large, 415 file type not allowed, 422 bad input, 429 too many requests.
Datetimes are ISO 8601 UTC strings, e.g. `"2026-08-13T15:59:00Z"`. Interactive docs: `/docs`.

Tiers: **T1** = Nov 7 core, **T2** = Nov to Dec, **T3** = after launch. Build only T1 unless told otherwise. Status: DONE or TODO.

Limits (server-enforced, T1 DONE): a user can be in at most 10 rooms and a room has at most 50 members. Creating or joining a room when you are already in 10 gives 409 "Room limit reached: ...". Joining a full room gives 409 "This room is full (50 members)." Joining a room you are already in is still fine at the limit.
Rules for every endpoint: validate input, check membership/admin first, never log message content, never trust IDs from the client.

## Roles (read this first)
- A room has members. Each member is either `admin` or `member`. Roles belong to rooms, not accounts.
- The room creator is the first admin.
- Promote to admin: the creator first. Once other admins exist, any admin can promote.
- Demote to member: the creator only. The creator can never be demoted.
- Only admins approve or reject tasks (see Approvals).
- Admins manage the room (members, roles, name, invite code) and may delete tasks and files. They have NO power over message content (see Discussion).

## Auth (Thomas)
| Method | Path | Body | Returns | Tier / Status |
|---|---|---|---|---|
| POST | /auth/signup | `{email, name, password(min 8)}` | 201 `{access_token, token_type, user:{id,email,name}}` | T1 DONE |
| POST | /auth/login | `{email, password}` | `{access_token, token_type, user}` | T1 DONE |
| GET | /auth/me | none | `{id,email,name}` | T1 DONE |
| POST | /auth/forgot | `{email}` | 204 always (never reveal whether the email exists) | T2 TODO |
| POST | /auth/reset | `{token, new_password}` | 204. Token is single-use and expires in 1 hour | T2 TODO |
| POST | /auth/verify | `{token}` | 204 | T2 TODO |
| GET | /auth/google, /auth/github (+ `/callback`) | none | redirect flow, then the same token response as login | T2 TODO |

Log out = the client deletes the token (no endpoint). Rate-limit signup, login, forgot and reset (429). Social accounts link to an existing account only by a VERIFIED email. No Apple sign-in.

## Rooms (Thomas)
Room: `{id, name, type, invite_code, role, member_count, pending_count, avatar_url?}`
`type` is `classroom | study_group | team | other`. `pending_count` = number of pending tasks in that room (same number for admins and members).
`invite_code` is returned only to admins; members get `null` (DONE, so a member can't read it from the API and invite others).
| Method | Path | Body | Returns | Tier / Status |
|---|---|---|---|---|
| POST | /rooms | `{name, type?}` | 201 room (role `admin`). `type` defaults to `classroom`; an invalid type gives 422. | T1 DONE |
| GET | /rooms | none | `[room]` (rooms I'm in), including `type` and `pending_count` | T1 DONE |
| POST | /rooms/join | `{invite_code}` | room. Invalid code gives 404 "Invalid invite code". Joining a room you are already in just returns the room. Codes are case-insensitive. | T1 DONE |
| GET | /rooms/{room_id}/members | none | `[{user_id,name,role,joined_at,avatar_url?,status:{kind,text},online?}]` (`online` is T2) | T1 DONE, add `status` TODO |
| POST | /rooms/{room_id}/leave | none | 204. Last member out deletes the room. The only admin can't leave while others remain (400). | T1 DONE |
| POST | /rooms/{room_id}/members/{user_id}/role | `{role: "admin" or "member"}` | member. Admin only (403 otherwise). 404 if the user is not in the room. Any admin can promote. Only the room creator can demote an admin (403 otherwise). The creator can never be demoted (400). Invalid role gives 422. | T1 DONE |
| PATCH | /rooms/{room_id} | `{name?, type?}` | room. Admin only (403 otherwise). Send at least one field and no unknown fields, otherwise 422. | T1 DONE |
| DELETE | /rooms/{room_id}/members/{user_id} | none | 204. Admin only (403 otherwise). 404 if the user is not in the room. Admins can remove members; only the creator can remove another admin (403 otherwise); the creator can never be removed (400). The removed user gets 403 on every room endpoint. | T1 DONE |
| POST | /rooms/{room_id}/invite-code/reset | none | `{invite_code}` (new code, the old one stops working). Admin only (403 otherwise). | T1 DONE |
| PUT | /rooms/{room_id}/avatar | multipart `image` | room. Admin only. Same image rules as profile pictures. | T2 TODO |

## Tasks (Daniel)
Task: `{id, room_id, title, type, subject?, due_at, all_day, status:"pending|approved|rejected", created_by, created_by_name, decided_by_name?, decided_at?, done}`
`done` is true when the CURRENT user ticked the task off. It is per user (nobody else sees it) and is filled in on the week, calendar, removed-list and done/hidden responses; on every other response it is false.
`type` is one of `exam, quiz, case-study, activity, seatwork, assignment` or a custom type name.
`all_day` is true when no time was given (`due_at` is then the end of that day in Asia/Manila, which is 15:59:00Z).
Only `approved` tasks appear on the board and calendar.
A task cannot be due in the past (decided Oct 20). Admins can still approve or reject a task whose date has passed while it waited.
Time zone: until the T2 timezone setting exists, weeks and months are calculated in Asia/Manila (UTC+8).
| Method | Path | Body | Returns | Tier / Status |
|---|---|---|---|---|
| POST | /rooms/{room_id}/tasks | `{title, type, due_at, all_day?, subject?}` | 201 task. `due_at` is required (422 if missing), must include a time zone, and must be in the future (422 "due_at must be in the future"). Status is `pending`, EXCEPT `approved` immediately when the creator is the room's only admin. | T1 DONE |
| GET | /rooms/{room_id}/tasks?week_start=YYYY-MM-DD | none | `[task]` approved tasks due in that Sun to Sat week, sorted by due_at. The week runs Sun 00:00 to Sat 23:59:59 Asia/Manila. `week_start` must be a Sunday, otherwise 422. | T1 DONE |
| GET | /rooms/{room_id}/calendar?month=YYYY-MM | none | `[task]` approved tasks due that month (month boundaries in Asia/Manila). Invalid month gives 422. | T1 DONE |
| PATCH | /tasks/{task_id} | `{title?, type?, due_at?, all_day?, subject?}` | task. The creator OR a room admin (decided Oct 21, so an admin can fix a task before deciding on it), and only while `pending` (403 otherwise). The creator and status are never changed by an edit. Send at least one field; title, type, due_at and all_day can never be null; unknown fields (such as status) give 422. subject can be cleared with null. Editing never changes the status. If `due_at` is sent it must be in the future (422); changing only other fields of a task whose date has passed is allowed. | T1 DONE |
| DELETE | /tasks/{task_id} | none | 204 (creator or room admin only) | T1 DONE |
| PUT | /tasks/{task_id}/done | none | 200 task with `done: true`. Ticks the task off for me only. Approved tasks only (409 "Task is not approved yet" otherwise). Ticking twice is fine. | T1 DONE |
| DELETE | /tasks/{task_id}/done | none | 200 task with `done: false`. Same rules; unticking a task that was never ticked is fine. | T1 DONE |
| PUT | /tasks/{task_id}/hidden | none | 200 task. Removes the task from MY Home board only. The room, other members and the calendar are unaffected. Approved tasks only (409 otherwise). Doing it twice is fine. | T1 DONE |
| DELETE | /tasks/{task_id}/hidden | none | 200 task. Restores a removed task to my Home board. Same rules. | T1 DONE |
| GET | /rooms/{room_id}/tasks/removed | none | `[task]` approved tasks of this room that I removed, sorted by due_at (403 if not a member). | T1 DONE |
| GET | /rooms/{room_id}/tasks/mine?limit=50 | none | `[task]` the tasks I created in this room, any status, newest first (`limit` 1 to 100, default 50; 422 otherwise). Used for "My submissions" (pending and rejected). 403 if not a member. | T1 DONE |

Done and removed are stored per user and per task and are deleted together with the task. `GET /rooms/{room_id}/tasks?week_start=` (the Home board) leaves out tasks I removed; `GET /rooms/{room_id}/calendar` still includes them. Both mark `done` for me.

Task-id endpoints (PATCH and DELETE /tasks/{task_id}, PUT and DELETE /tasks/{task_id}/done and /hidden, POST /tasks/{task_id}/approve and /reject) return 404 both when the task does not exist and when the caller is not a member of its room, so task ids cannot be probed. Room endpoints return 403.

## Approvals (Daniel)
Rules:
- Only room admins approve or reject tasks. Members submit tasks as `pending`.
- A task created by a member: any admin can decide it.
- A task created by an admin: another admin must decide it. An admin cannot approve or reject their own task, UNLESS they are the room's only admin. If the room has exactly one admin, that admin's new tasks are auto-approved at creation.
- The first admin decision is final.
- Approving or rejecting a task that is not pending returns 409 "Task already decided".
- The sole-admin check happens at decision time: if a room is down to one admin, that admin can decide their own older pending tasks.
- The pending list is oldest first. History is newest decision first; `limit` defaults to 50 and must be 1 to 200 (422 otherwise).
- The Approve tab = pending tasks in the room, admins only. History = tasks an admin explicitly decided (auto-approved tasks are not in history).

| Method | Path | Body | Returns | Tier / Status |
|---|---|---|---|---|
| GET | /rooms/{room_id}/approvals | none | `[task]` with status `pending` (admin only) | T1 DONE |
| GET | /rooms/{room_id}/approvals/history?limit=50 | none | `[task]` tasks an admin explicitly approved or rejected, newest decision first, with `decided_by_name` and `decided_at` (admin only). Auto-approved tasks (sole admin) are NOT included. | T1 DONE |
| POST | /tasks/{task_id}/approve | none | task (updated). Admin only. | T1 DONE |
| POST | /tasks/{task_id}/reject | none | task (updated). Admin only. | T1 DONE |

## Discussion (Daniel): room chat, text only
Message: `{id, room_id, author_id, author_name, body, reply_to_id?, reply_to?:{author_name, snippet}, created_at}`
Rules:
- Only room members can read or post (`require_member` on every endpoint). `body` is 1 to 2000 characters; rate-limit posting.
- A user can delete ONLY their own messages. Room admins can NOT delete other users' messages (403).
- Room discussion is NOT end-to-end encrypted (stored readable; disclosed in the privacy note). Never log message content.
- The frontend renders message text with `textContent`, never `innerHTML`.
- reply_to_id must point to a message in the same room, otherwise 422.
- Deleting a message that has replies is a hard delete; those replies then show reply_to as null.
- reply_to.snippet is the first 80 characters of the replied-to message.
- `body` is trimmed, then must be 1 to 2000 characters; a blank body gives 422.
- GET messages: `limit` defaults to 50 and must be 1 to 100 (422 otherwise); a bad `before_id` (not a positive integer) gives 422; a `before_id` that does not exist or belongs to another room returns an empty list.
- DELETE message: 404 when the message does not exist or is in a room the caller is not in (so ids cannot be probed); 403 for a room member who is not the author (admins included).
| Method | Path | Body | Returns | Tier / Status |
|---|---|---|---|---|
| GET | /rooms/{room_id}/messages?limit=50&before_id= | none | `[message]` oldest first (the latest page by default; `before_id` loads older ones) | T1 TODO |
| POST | /rooms/{room_id}/messages | `{body, reply_to_id?}` | 201 message | T1 TODO |
| DELETE | /messages/{message_id} | none | 204. Author only; anyone else, including admins, gets 403. | T1 TODO |
T2 (not defined yet): @mentions, attachments, unread counts, "seen by". T3: WebSockets, DMs, calls (see Messaging).

## Files (Daniel): replaces Notes
File: `{id, room_id, name, kind:"docs|sheets|files", mime, size, locked, locked_by_name?, created_by, created_by_name, created_at, updated_at, updated_by_name, version}`
Rules:
- Only room members can list or download. Locked = read-only notes: no new version, no rename (everyone can still download). The creator or any room admin can lock or unlock. The creator or any room admin can delete (even if locked).
- Allowed: .pdf .docx .xlsx .pptx .txt .csv .md; source code of any language as plain text (.py .java .c .cpp .h .cs .js .ts .json .html .css .sql .php .rb .go .rs .sh and similar); images .png .jpg .jpeg .gif .webp; audio .mp3 .wav .m4a. Everything else is rejected with 415 (video, archives, executables and installers, macro-enabled Office files, legacy .doc/.xls/.ppt, SVG).
- Limits (defaults): 10 MB per file, images 5 MB, audio 15 MB, 250 MB per room (413 when exceeded).
- Validation order: logged in and member, size cap while streaming, extension allowlist, magic-bytes check (real type must match; text must be valid UTF-8 with no NUL bytes), sanitize the display name, store under a random key, re-encode images (strip EXIF). Never unzip or parse uploaded docx/xlsx on the server. Never execute or render uploaded files.
- Serving: user files never come from the roomsync.me origin. Signed short-lived links, `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`, text as `text/plain`.
| Method | Path | Body | Returns | Tier / Status |
|---|---|---|---|---|
| GET | /rooms/{room_id}/files?kind=&sort=modified&order=desc | none | `[file]`. `kind`: docs, sheets, files. `sort`: modified, created, name, size. `order`: asc, desc. | T2 TODO |
| POST | /rooms/{room_id}/files | multipart `file` | 201 file | T2 TODO |
| POST | /rooms/{room_id}/files/new | `{kind:"doc" or "sheet", name}` | 201 file (a blank .docx or .xlsx) | T2 TODO |
| GET | /files/{file_id}/download | none | `{url, expires_at}` (short-lived signed link) | T2 TODO |
| PUT | /files/{file_id}/content | multipart `file` | file (new version). 403 if locked. | T2 TODO |
| PATCH | /files/{file_id} | `{name?, locked?}` | file. Rename: not when locked. Lock or unlock: creator or admin. | T2 TODO |
| DELETE | /files/{file_id} | none | 204 (creator or room admin) | T2 TODO |
T3: live co-editing docs (Yjs over WebSockets). Not defined yet.

## Users: profile, status, account
User: `{id, email, name, avatar_url?, status:{kind,text}, joined_at}`
`status.kind` is `working | brb | away | custom` (shown as "Working!", "BRB!", "Somewhere Else", or the custom text, max 40 characters). The status never expires; it stays until changed, and is visible to everyone in your rooms.
| Method | Path | Body | Returns | Tier / Status |
|---|---|---|---|---|
| GET | /users/me | none | user | T1 DONE |
| PATCH | /users/me | `{name?, status_kind?, status_text?}` | user. `status_text` required when kind is `custom` (max 40); it is cleared when the kind is not `custom`. Send at least one field; unknown fields give 422. The members list also returns each member's `status`. | T1 DONE |
| GET | /users/me/stats | none | `{submitted, approved, rejected}` (counts of my tasks across all rooms) | T1 DONE |
| DELETE | /users/me | none | 204. 400 if I am the only admin of a room that still has other members (pass the admin role first). My messages and tasks stay, shown as "Deleted user". I leave all my rooms (a room with no one left is deleted), the email is freed for a new signup, and the old token stops working (401). | T1 DONE |
| PUT | /users/me/avatar | multipart `image` | user. png/jpg/webp, max 2 MB, resized to 256x256, re-encoded. | T2 TODO |
| DELETE | /users/me/avatar | none | 204 | T2 TODO |
| POST | /presence/ping | none | 204 (call every ~60 s; online = seen in the last 2 minutes) | T2 TODO |
| GET | /users/me/task-types | none | `[{id,name,color}]` | T2 TODO |
| POST | /users/me/task-types | `{name(max 20), color:"#rrggbb"}` | 201 `{id,name,color}` (409 if name exists) | T2 TODO |
| DELETE | /users/me/task-types/{id} | none | 204 | T2 TODO |
| GET | /users/me/settings | none | settings | T2 TODO |
| PUT | /users/me/settings | `{theme:"light|dark|system", show_empty_days, notify_deadline_reminders, notify_mentions, notify_approvals, timezone:"Asia/Manila", task_colors?:{type:"#rrggbb"}}` | settings | T2 TODO |
Until T2, theme, show-empty-days and task colors stay in browser `localStorage`.

## Deadline reminders (T2, no public endpoints except unsubscribe)
- A background job emails users before an APPROVED task is due: defaults 3 days, 1 day and 3 hours before `due_at`.
- Each user, task and offset is emailed at most once. Respects `notify_deadline_reminders`. Every email has an unsubscribe link: GET `/unsubscribe?token=` turns the setting off.

## About (T2)
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | /feedback | `{name, room?, rating(1-5), message(max 2000), website?}` | 204 |
| POST | /contact | `{name, email, message(max 2000), website?}` | 204 |
Public endpoints: rate-limited. `website` is a hidden honeypot field; if it is filled in, return 204 and save nothing.

## Messaging (T3: AFTER LAUNCH, do NOT build yet)
Listed so nobody invents conflicting endpoints. Exact endpoints are added here BEFORE any code is written.
- Instant delivery (WebSockets) for room chat, typing indicators, presence.
- Direct messages: private between two users, END-TO-END ENCRYPTED. The server stores only ciphertext. Room admins and developers can NOT read DMs. Users still see history. Users can delete only their own DMs.
- Audio and video calls (press Call, the other person is rung), 1-on-1 and room group calls, through an embedded call service. The ring uses the WebSocket.
- Live co-editing docs in Files.
- Until DMs ship, do not claim end-to-end encryption anywhere in the product or docs.

## Frontend conventions (all pages)
- API address: `js/config.js` sets `window.ROOMSYNC.API_BASE` (empty in production, `http://localhost:8000` on Live Server ports).
- The login token is stored in `localStorage` as `roomsync_token`, the user as `roomsync_user`. Send `Authorization: Bearer <token>`. On any 401, clear both keys and go to `login.html`.
- Render all user text with `textContent`, never `innerHTML`.
- Pages already wired to the API: `login.html`, `home.html` (rooms, members, create, join, logout, the week board and New TODO). Marked with `<body data-api-rooms>`; other pages still show demo data.
- Frontend files are sent with `Cache-Control: no-cache`, so browsers re-check them on every load (an unchanged file costs a tiny 304 reply).

## Health
GET `/health` returns `{"status":"ok"}` (no auth).