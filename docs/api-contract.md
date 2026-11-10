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
| POST | /auth/signup | `{email, name, password(min 8)}` | 201 `{access_token, token_type, user:{id,email,name,email_verified}}`. Also sends a verification email in the background. | T1 DONE |
| POST | /auth/login | `{email, password}` | `{access_token, token_type, user}` | T1 DONE |
| GET | /auth/me | none | `{id,email,name,email_verified}` | T1 DONE |
| POST | /auth/forgot | `{email}` | 204 always, same answer and similar speed whether or not the email exists. Sends a reset email only to a real, active account. | T2 DONE |
| POST | /auth/reset | `{token, new_password(min 8)}` | 204. 400 "Invalid or expired link" for any bad, used or expired token. | T2 DONE |
| POST | /auth/verify | `{token}` | 204. 400 "Invalid or expired link" for any bad, used or expired token. | T2 DONE |
| POST | /auth/resend-verification | none (logged in) | 204 always, even if already verified (no-op, no second email). | T2 DONE |
| GET | /auth/google, /auth/github (+ `/callback`) | none | redirect flow, then the same token response as login | T2 TODO |

Password reset rules: the emailed link is `APP_URL/pages/reset.html#token=...` (the token is in the URL fragment so it never reaches server logs or Referer headers). Only a SHA-256 hash of the token is stored. A token works once, expires after 30 minutes, and a newer request replaces the older one. Rate limits: forgot 5/hour per address and 3/hour per email; reset 10/hour per address. A successful reset bumps the user's `token_version`, so every older login token stops working (401), and a "Your password was changed" email is sent. The reset response does NOT log the user in.

Email verification rules: same shape as password reset (own `email_verifications` table, SHA-256 hash only, link in the URL fragment: `APP_URL/pages/verify.html#token=...`). A token works once and expires after 24 hours; a new request (signup, or `/auth/resend-verification`) replaces the older one. Rate limits: verify 10/hour per address; resend-verification 3/hour per account. Verifying does NOT log the user in or out, and an unverified account can still log in and use the app normally — `email_verified` only gates features that depend on reaching a real inbox (deadline reminders).

Log out = the client deletes the token (no endpoint). Rate-limit signup, login, forgot, reset, verify and resend-verification (429). Social accounts link to an existing account only by a VERIFIED email. No Apple sign-in.

## Rooms (Thomas)
Room: `{id, name, type, invite_code, role, member_count, pending_count, avatar_url?}`
`type` is `classroom | study_group | team | other`. `pending_count` = number of pending tasks in that room (same number for admins and members).
`invite_code` is returned only to admins; members get `null` (DONE, so a member can't read it from the API and invite others).
| Method | Path | Body | Returns | Tier / Status |
|---|---|---|---|---|
| POST | /rooms | `{name, type?}` | 201 room (role `admin`). `type` defaults to `classroom`; an invalid type gives 422. | T1 DONE |
| GET | /rooms | none | `[room]` (rooms I'm in), including `type` and `pending_count` | T1 DONE |
| POST | /rooms/join | `{invite_code}` | room. Invalid code gives 404 "Invalid invite code". Joining a room you are already in just returns the room. Codes are case-insensitive. Limited to 10 tries per minute per user: after that 429 with a Retry-After header (stops invite-code guessing). | T1 DONE |
| GET | /rooms/{room_id}/members | none | `[{user_id,name,role,joined_at,avatar_url?,status:{kind,text},online}]` (`online` = seen in the last 2 minutes via POST /presence/ping) | T1/T2 DONE |
| POST | /rooms/{room_id}/leave | none | 204. Last member out deletes the room. The only admin can't leave while others remain (400). | T1 DONE |
| POST | /rooms/{room_id}/members/{user_id}/role | `{role: "admin" or "member"}` | member. Admin only (403 otherwise). 404 if the user is not in the room. Any admin can promote. Only the room creator can demote an admin (403 otherwise). The creator can never be demoted (400). Invalid role gives 422. | T1 DONE |
| PATCH | /rooms/{room_id} | `{name?, type?}` | room. Admin only (403 otherwise). Send at least one field and no unknown fields, otherwise 422. | T1 DONE |
| DELETE | /rooms/{room_id}/members/{user_id} | none | 204. Admin only (403 otherwise). 404 if the user is not in the room. Admins can remove members; only the creator can remove another admin (403 otherwise); the creator can never be removed (400). The removed user gets 403 on every room endpoint. | T1 DONE |
| POST | /rooms/{room_id}/invite-code/reset | none | `{invite_code}` (new code, the old one stops working). Admin only (403 otherwise). | T1 DONE |
| PUT | /rooms/{room_id}/avatar | multipart `image` | room with `avatar_url`. Admin only (403). Same image rules as profile pictures (png/jpg/webp, max 2 MB, resized to 256x256, re-encoded). | T1 TODO (was T2) |
| DELETE | /rooms/{room_id}/avatar | none | 204. Admin only (403). Back to the default icon. | T1 TODO |

## Tasks (Daniel)
Task: `{id, room_id, title, type, subject?, due_at, all_day, status:"pending|approved|rejected", created_by, created_by_name, decided_by_name?, decided_at?, note?, edited_by_name?, edited_at?, attachments, done}`
`note` is an optional plain-text note, max 300 characters. `edited_by_name` and `edited_at` are set when an admin edits an approved task; the frontend shows "Edited by <name>".
`attachments` is a list of up to 5 notes (room files) linked to the task: `[{file_id, name, size}]`, oldest first (empty list when none). It carries names only, never file contents; downloading still goes through `GET /files/{file_id}/download` and its member-only check. See "Note attachments" below.
`done` is true when the CURRENT user ticked the task off. It is per user (nobody else sees it) and is filled in on the week, calendar, removed-list and done/hidden responses; on every other response it is false.
`type` is one of `exam, quiz, case-study, activity, seatwork, assignment` or a custom type name of 1 to 15 characters (was 30; every built-in type fits). Custom types show as a neutral grey chip.
"Add another title" in the New TODO form needs no endpoint: the form shares subject, type, date and time and sends one POST /rooms/{room_id}/tasks per title, so every title is its own separate task and card.
`all_day` is true when no time was given (`due_at` is then the end of that day in Asia/Manila, which is 15:59:00Z).
Only `approved` tasks appear on the board and calendar.
A task cannot be due in the past (decided Oct 20). Admins can still approve or reject a task whose date has passed while it waited.
Time zone: until the T2 timezone setting exists, weeks and months are calculated in Asia/Manila (UTC+8).
| Method | Path | Body | Returns | Tier / Status |
|---|---|---|---|---|
| POST | /rooms/{room_id}/tasks | `{title, type, due_at, all_day?, subject?, note?, file_ids?}` | 201 task. `file_ids` is an optional list of up to 5 file ids to attach (see Note attachments); every id must be a file of THIS room, otherwise 422 "One of the files was not found in this room" (same answer for a missing file and for a file of another room). `due_at` is required (422 if missing), must include a time zone, and must be in the future (422 "due_at must be in the future"). Status is `pending`, EXCEPT `approved` immediately when the creator is the room's only admin. | T1 DONE |
| GET | /rooms/{room_id}/tasks?week_start=YYYY-MM-DD | none | `[task]` approved tasks due in that Sun to Sat week, sorted by due_at. The week runs Sun 00:00 to Sat 23:59:59 Asia/Manila. `week_start` must be a Sunday, otherwise 422. | T1 DONE |
| GET | /rooms/{room_id}/calendar?month=YYYY-MM | none | `[task]` approved tasks due that month (month boundaries in Asia/Manila). Invalid month gives 422. | T1 DONE |
| PATCH | /tasks/{task_id} | `{title?, type?, due_at?, all_day?, subject?, note?}` | task. While `pending`: the creator OR a room admin (decided Oct 21). While `approved`: room admins ONLY (members get 403); no re-approval, the status stays `approved`, and `edited_by_name` and `edited_at` are recorded. `rejected` tasks cannot be edited (403). The creator and status are never changed by an edit. Send at least one field; title, type, due_at and all_day can never be null; unknown fields (such as status) give 422. subject and note can be cleared with null. `type` is 1 to 15 characters, `note` max 300 (422 otherwise). If `due_at` is sent it must be in the future (422); changing only other fields of a task whose date has passed is allowed. | T1 TODO (approved-task edit, note, 15-char type) |
| DELETE | /tasks/{task_id} | none | 204 (creator or room admin only) | T1 DONE |
| PUT | /tasks/{task_id}/done | none | 200 task with `done: true`. Ticks the task off for me only. Approved tasks only (409 "Task is not approved yet" otherwise). Ticking twice is fine. | T1 DONE |
| DELETE | /tasks/{task_id}/done | none | 200 task with `done: false`. Same rules; unticking a task that was never ticked is fine. | T1 DONE |
| PUT | /tasks/{task_id}/hidden | none | 200 task. Removes the task from MY Home board only. The room, other members and the calendar are unaffected. Approved tasks only (409 otherwise). Doing it twice is fine. | T1 DONE |
| DELETE | /tasks/{task_id}/hidden | none | 200 task. Restores a removed task to my Home board. Same rules. | T1 DONE |
| GET | /rooms/{room_id}/tasks/removed | none | `[task]` approved tasks of this room that I removed, sorted by due_at (403 if not a member). | T1 DONE |
| GET | /rooms/{room_id}/tasks/mine?limit=50 | none | `[task]` the tasks I created in this room, any status, newest first (`limit` 1 to 100, default 50; 422 otherwise). Used for "My submissions" (pending and rejected). 403 if not a member. | T1 DONE |
| GET | /rooms/{room_id}/tasks/search?q=&type=&limit=30 | none | `[task]` approved tasks of this room whose title, subject or type contains `q` (case-insensitive; `%` and `_` are plain characters). `q` is required, 1 to 50 characters, not blank (422 otherwise). `type` optionally keeps one exact type. Upcoming tasks first (soonest first), then past ones (most recent first). `limit` 1 to 100, default 30. Tasks I removed from Home are still found. `done` is marked for me. 403 if not a member. Used by the mobile search sheet. | T1 DONE |

Done and removed are stored per user and per task and are deleted together with the task. `GET /rooms/{room_id}/tasks?week_start=` (the Home board) leaves out tasks I removed; `GET /rooms/{room_id}/calendar` still includes them. Both mark `done` for me.

Task-id endpoints (PATCH and DELETE /tasks/{task_id}, PUT and DELETE /tasks/{task_id}/done and /hidden, POST /tasks/{task_id}/approve and /reject) return 404 both when the task does not exist and when the caller is not a member of its room, so task ids cannot be probed. Room endpoints return 403.

### Note attachments (T2 DONE)
A task can link up to 5 notes (room files) so syncmates open the right file from the task card, and the Notes page shows which tasks use a file.
| Method | Path | Body | Returns | Tier / Status |
|---|---|---|---|---|
| PUT | /tasks/{task_id}/attachments/{file_id} | none | 200 task (with `attachments`). Links the file to the task. Doing it twice is fine. | T2 DONE |
| DELETE | /tasks/{task_id}/attachments/{file_id} | none | 204. Unlinks the file (the file itself is NOT deleted). Unlinking a file that was not linked is fine. | T2 DONE |
Rules:
- Same-room only. The file must belong to the task's room. A missing file and a file of another room give the same 404 "File not found", and a non-member gets the usual task-id 404, so nothing can be probed.
- Who: the task's creator or a room admin (403 for other members). Allowed on `pending` and `approved` tasks; a `rejected` task gives 403. Attaching does not count as an edit (no "Edited by").
- Limits: at most 5 notes per task (409 "A task can have at most 5 notes"). Rate limit: 60 attach or unlink calls per hour per user (429).
- Access does not change: attaching never gives anyone new access. Only room members can see a task or download a file, exactly as before.
- Cleanup: deleting a task removes its links; deleting a file removes it from every task (the tasks stay).
- Notes page: each file in `GET /rooms/{room_id}/files` also has `used_in` (up to 5 APPROVED tasks that link it, `[{task_id, title}]`) and `used_in_count`. Pending and rejected tasks are never listed there.

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
| POST | /rooms/{room_id}/approvals/approve-all | none | `{approved: n, skipped: n}`. Admin only (403). Approves every pending task in the room, except the caller's own tasks when the room has more than one admin (same rule as above; those are counted in `skipped`). Used by the Approve all button for batches. | T1 TODO |
| POST | /tasks/{task_id}/reject | none | task (updated). Admin only. | T1 DONE |

## Discussion (Daniel): room chat, text only
Message: `{id, room_id, author_id, author_name, body, reply_to_id?, reply_to?:{author_name, snippet}, created_at, mentions, attachments}`
Rules:
- Only room members can read or post (`require_member` on every endpoint). `body` is 1 to 2000 characters; rate-limit posting.
- A user can delete ONLY their own messages. Room admins can NOT delete other users' messages (403).
- Room discussion is NOT end-to-end encrypted (stored readable; disclosed in the privacy note). Never log message content.
- The frontend renders message text with `textContent`, never `innerHTML` (mentions are highlighted by wrapping the matched substring in its own text node, not by injecting markup).
- reply_to_id must point to a message in the same room, otherwise 422.
- Deleting a message that has replies is a hard delete; those replies then show reply_to as null.
- reply_to.snippet is the first 80 characters of the replied-to message.
- `body` is trimmed, then must be 1 to 2000 characters; a blank body gives 422.
- GET messages: `limit` defaults to 50 and must be 1 to 100 (422 otherwise); a bad `before_id` (not a positive integer) gives 422; a `before_id` that does not exist or belongs to another room returns an empty list.
- DELETE message: 404 when the message does not exist or is in a room the caller is not in (so ids cannot be probed); 403 for a room member who is not the author (admins included).
- **@mentions (T2 DONE).** `mentions` is a list of user ids: every current room member whose exact display name appears in `body` as `@Full Name` on a word boundary (computed on read, not stored, so a rename or a membership change changes future `mentions` on old messages too). No endpoint needed; the `notify_mentions` account setting (`GET/PUT /users/me/settings`) exists for a future notification feature but sending one is not built.
- **Attachments via the clip (T2 DONE).** Reuses the Files pipeline: `file_ids` on `POST /rooms/{room_id}/messages`, up to 5, every id must already be a file of this room (422 "One of the files was not found in this room" otherwise, same answer for a missing file and a file of another room). `attachments` on every message is `[{file_id, name, size}]`, oldest-attached first (empty list when none). Carries names only; downloading still goes through `GET /files/{file_id}/download` and its member-only check.
- **Unread counts and "seen by" (T2 DONE).** One per-user, per-room read marker (`last_read_at`), set to the room's `joined_at` the first time it is needed so history from before you joined is never "unread". Posting a message does not mark it read for the author's own other devices; only `POST .../read` does.
| Method | Path | Body | Returns | Tier / Status |
|---|---|---|---|---|
| GET | /rooms/{room_id}/messages?limit=50&before_id= | none | `[message]` oldest first (the latest page by default; `before_id` loads older ones) | T1 DONE |
| POST | /rooms/{room_id}/messages | `{body, reply_to_id?, file_ids?}` | 201 message | T1/T2 DONE |
| DELETE | /messages/{message_id} | none | 204. Author only; anyone else, including admins, gets 403. | T1 DONE |
| GET | /rooms/{room_id}/messages/unread-count | none | `{count}` messages after my read marker, not authored by me. | T2 DONE |
| POST | /rooms/{room_id}/messages/read | none | 204. Moves my read marker for this room to now. Rate-limited. | T2 DONE |
| GET | /rooms/{room_id}/messages/seen | none | `[{user_id, name}]` other room members whose read marker is at or past the newest message (empty list when there are no messages yet). | T2 DONE |
T3: WebSockets, DMs, calls (see Messaging).

## Files (Thomas): replaces Notes
File: `{id, room_id, name, kind:"docs|sheets|files", mime, size, locked, locked_by_name?, created_by, created_by_name, created_at, updated_at, updated_by_name, version, used_in, used_in_count}`
Rules:
- Only room members can list or download. Locked = read-only notes: no new version, no rename (everyone can still download). The creator or any room admin can lock or unlock. The creator or any room admin can delete (even if locked).
- Allowed: .pdf .docx .xlsx .pptx .txt .csv .md; source code of any language as plain text (.py .java .c .cpp .h .cs .js .ts .json .html .css .sql .php .rb .go .rs .sh and similar); images .png .jpg .jpeg .gif .webp; audio .mp3 .wav .m4a. Everything else is rejected with 415 (video, archives, executables and installers, macro-enabled Office files, legacy .doc/.xls/.ppt, SVG).
- Limits (defaults): 10 MB per file, images 5 MB, audio 15 MB, 250 MB per room (413 when exceeded).
- Validation order: logged in and member, size cap while streaming, extension allowlist, magic-bytes check (real type must match; text must be valid UTF-8 with no NUL bytes), sanitize the display name, store under a random key, re-encode images (strip EXIF). Never unzip or parse uploaded docx/xlsx on the server. Never execute or render uploaded files.
- Serving (T2 goal): user files never come from the roomsync.me origin. Signed short-lived links, `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`, text as `text/plain`.
- **Launch version (Oct 30, T1 DONE).** File contents are stored in a private Cloudflare R2 bucket when the `R2_*` environment values are set (the database keeps the file list and a random object key); without them, in the database table `room_files` (local development and tests). Allowed: .pdf .docx .txt .md .csv .json .sql and code (.py .java .c .cc .cpp .cxx .h .hpp .cs .js .ts). Everything else gives 415. Limits: 10 MB per file, 500 MB per room (413), 8 GB for the whole app (507), R2 unreachable (503), 20 uploads per hour per user (429). The upload is the raw file as the request body, with its name in `?name=` (not multipart). Content is checked against the name (422): PDFs must be real PDFs without scripts or embedded files, .docx must be a real Word file without macros or embedded programs (only the zip's file list is read, nothing is unpacked), text and code must be valid UTF-8. A download is the file itself, always as `application/octet-stream` with `Content-Disposition: attachment` and `nosniff`, only for room members (a file in another room is a 404). Not built yet: new blank docs and sheets, locking, rename, new versions, signed links, xlsx/pptx/images/audio.
| Method | Path | Body | Returns | Tier / Status |
|---|---|---|---|---|
| GET | /rooms/{room_id}/files?kind=&sort=modified&order=desc | none | `[file]`. `kind`: docs, sheets, files. `sort`: modified, created, name, size. `order`: asc, desc. | T1 DONE |
| POST | /rooms/{room_id}/files?name= | raw file bytes (the request body) | 201 file. 415 type not allowed, 413 too big or room full, 422 content does not match or is empty. | T1 DONE |
| POST | /rooms/{room_id}/files/new | `{kind:"doc" or "sheet", name}` | 201 file (a blank .docx or .xlsx) | T2 TODO |
| GET | /files/{file_id}/download | none | the file itself as a download (T2: becomes `{url, expires_at}`, a signed link) | T1 DONE |
| GET | /files/{file_id}/text | none | `{name, text, truncated}`: the first 200,000 bytes of a text or code file, for the in-page viewer. 415 for PDF and DOCX. | T1 DONE |
| PUT | /files/{file_id}/content | multipart `file` | file (new version). 403 if locked. | T2 TODO |
| PATCH | /files/{file_id} | `{name?, locked?}` | file. Rename: not when locked. Lock or unlock: creator or admin. | T2 TODO |
| DELETE | /files/{file_id} | none | 204 (creator or room admin; other members get 403) | T1 DONE |
T3: live co-editing docs (Yjs over WebSockets). Not defined yet.

## Users: profile, status, account
User: `{id, email, name, avatar_url?, status:{kind,text}, joined_at}`
`status.kind` is `working | brb | away | custom` (shown as "Working!", "BRB!", "Somewhere Else", or the custom text, max 40 characters). The status never expires; it stays until changed, and is visible to everyone in your rooms.
| Method | Path | Body | Returns | Tier / Status |
|---|---|---|---|---|
| GET | /users/me | none | user | T1 DONE |
| PATCH | /users/me | `{name?, status_kind?, status_text?}` | user. `status_text` required when kind is `custom` (max 40); it is cleared when the kind is not `custom`. Send at least one field; unknown fields give 422. The members list also returns each member's `status`. | T1 DONE |
| GET | /users/me/stats | none | `{submitted, approved, rejected}` (counts of my tasks across all rooms) | T1 DONE |
| GET | /users/me/history?limit=50 | none | `[{id,title,room_id,room_name,type,status,created_at,decided_at?}]` my own submitted tasks, newest first (Profile > History) | T2 DONE |
| GET | /users/{user_id} | none | `{id, name, avatar_url, status, joined_at, rooms:[{id,name}]}` for me or someone who shares a room with me; `rooms` are only the rooms we are both in; no email. Anyone else, a missing user and a deleted user all give the same 404. Non-number id gives 422. | T1 DONE |
| DELETE | /users/me | none | 204. 400 if I am the only admin of a room that still has other members (pass the admin role first). My messages and tasks stay, shown as "Deleted user". I leave all my rooms (a room with no one left is deleted), the email is freed for a new signup, and the old token stops working (401). | T1 DONE |
| PUT | /users/me/avatar | multipart `image` | user. png/jpg/webp, max 2 MB, resized to 256x256, re-encoded. | T2 TODO |
| DELETE | /users/me/avatar | none | 204 | T2 TODO |
| POST | /presence/ping | none | 204 (call every ~60 s; online = seen in the last 2 minutes). Rate-limited (120/min/user). | T2 DONE |
| GET | /users/me/task-types | none | `[{id,name,color}]` | T2 TODO |
| POST | /users/me/task-types | `{name(max 20), color:"#rrggbb"}` | 201 `{id,name,color}` (409 if name exists) | T2 TODO |
| DELETE | /users/me/task-types/{id} | none | 204 | T2 TODO |
| GET | /users/me/settings | none | `{theme, show_empty_days, notify_deadline_reminders, notify_mentions, notify_approvals, timezone, task_colors}` | T2 DONE |
| PUT | /users/me/settings | partial `{theme?:"light\|dark\|system", show_empty_days?, notify_deadline_reminders?, notify_mentions?, notify_approvals?, timezone?, task_colors?:{type:"#rrggbb"}}` (send at least one field) | settings. `task_colors` MERGES into what is saved (does not replace it); only the six built-in types are accepted (422 otherwise). Theme and the notification toggles are saved but not read by the frontend yet. | T2 DONE (theme/notify toggles: saved, not wired) |
Show-empty-days and task colors are account-level now (GET/PUT /users/me/settings), not `localStorage`.

## Email (T2)
Sent through Resend from `RoomSync <no-reply@roomsync.me>` with Reply-To `thomas@roomsync.me`. Settings live only in environment variables: `RESEND_API_KEY` (a Sending-access key limited to roomsync.me), `EMAIL_FROM`, `EMAIL_REPLY_TO`, `CONTACT_INBOX`, `APP_URL`. With no `RESEND_API_KEY` set (local dev, tests) emails are not sent. Nothing is ever logged about an email except the kind and a success or failure flag.
- Sending never blocks or breaks a request: it runs in the background, and a failed send does not turn the API answer into an error.
- Free plan limits: 100 emails per day, 3,000 per month. Emails that are not time-critical (reminders) are batched; password-reset and security emails always go first.
- Emails we send: password reset link, "password changed" notice, email verification link, deadline-reminder digest, Contact and Feedback forwards to `CONTACT_INBOX`.

## Deadline reminders (T2 DONE, no public endpoints except unsubscribe)
**DECIDED (Nov 10, replaces the earlier fixed-schedule plan): one daily digest per user, not three emails per task.** The original per-offset design (3 days, 1 day, 3 hours before `due_at`, separately) would send one email per task per offset per user -- a single 30-person room with one task is already 90 emails, which blows the Resend free plan (100/day, 3,000/month) almost immediately. A daily digest costs at most one email per verified, opted-in user per day, regardless of room size or task count.
- In-process scheduler (APScheduler, `app/scheduler.py`), one Render instance only. Runs once a day at 23:00 UTC (7:00 AM Manila) and sends each eligible user ONE email (`app/digest.py`): every task across their rooms that is APPROVED, not yet ticked done by them, due within the next 3 days, and not already overdue.
- Eligible = `email_verified` is true AND `notify_deadline_reminders` is true (or no settings row saved yet, since that column's own default is true) AND the account isn't soft-deleted. A user with nothing due soon is skipped (not emailed just to say "nothing's due").
- At most one digest per user per calendar day (`users.last_digest_sent_at`), so a retry or redeploy never double-sends the same day. No per-task "already sent" state needed, since the digest just reflects whatever is currently due soon.
- Manual test without waiting for the schedule: `python -m app.digest` (dry run, prints what would be sent) or `python -m app.digest --send` (actually sends).
- `GET /unsubscribe?token=` | none | 200 HTML confirmation, or 400 for a bad token. Turns `notify_deadline_reminders` off, no login needed. The token is `HMAC(SECRET_KEY, "unsub:<user_id>")`-based, never expires, needs no database row. Rate limited 30/hour per address.

## About (T1 DONE)
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | /feedback | `{name, room?, rating(1-5), message(max 2000), website?}` | 204 |
| POST | /contact | `{name, email, message(max 2000), website?}` | 204 |
Public endpoints: rate-limited (5 per hour per address each, 429 after that). `website` is a hidden honeypot field; if it is filled in, return 204 and save nothing. Bad input gives 422. Messages are saved in the tables `feedback` and `contact_messages` (read them in the Neon SQL editor); once the Email service is configured, each saved message is also forwarded to `CONTACT_INBOX` (Reply-To is the sender's address for Contact). A failed forward never fails the request.

## Inbox (T2 DONE): replaces direct messages
A private, one-to-one inbox, like email inside RoomSync. A person writes to a syncmate (someone who shares a room with them), picked by name, and the message lands in the recipient's Inbox tab. It is NOT a mailto link and sends no real email in v1 (a "you have a new message" email may come later). It is NOT end-to-end encrypted (see Privacy below).
Message: `{id, from_user_id, from_name, to_user_id, to_name, subject, body, created_at, read_at?, reply_to_id?, archived}`. Names only; email addresses are never returned. A deleted account shows as "Deleted user".
| Method | Path | Body | Returns | Tier / Status |
|---|---|---|---|---|
| GET | /inbox/syncmates | none | `[{user_id, name, rooms: [room name]}]` everyone who shares a room with me (not me, not deleted accounts), sorted by name. Powers the name picker. No emails. | T2 DONE |
| POST | /inbox | `{to_user_id, subject, body}` | 201 message. `subject` 1 to 120 characters, `body` 1 to 2000, both trimmed and not blank (422). Writing to yourself gives 422. | T2 DONE |
| POST | /inbox/{message_id}/reply | `{body}` | 201 message to the other person, subject "Re: ..." (reply_to_id set). Same rules and limits as a new message. | T2 DONE |
| GET | /inbox?folder=inbox&limit=50&before_id= | none | `[message]` newest first. `folder`: `inbox` (default), `sent`, `archived`. `limit` 1 to 100. `before_id` pages older messages. 422 for a bad value. | T2 DONE |
| GET | /inbox/unread-count | none | `{count}` unread messages in my inbox. The frontend polls this every 30 seconds for the dot and the toast. | T2 DONE |
| GET | /inbox/{message_id} | none | message. Opening it as the recipient marks it read (sets `read_at`). | T2 DONE |
| PATCH | /inbox/{message_id} | `{archived}` | message. Recipient only (404 for anyone else). | T2 DONE |
| DELETE | /inbox/{message_id} | none | 204. Removes it from MY view only; the other person keeps their copy. When both have removed it, it is deleted for good. | T2 DONE |
| PUT | /inbox/blocks/{user_id} | none | 204. Blocks that person from writing to me. Doing it twice is fine. | T2 DONE |
| DELETE | /inbox/blocks/{user_id} | none | 204. Unblocks. | T2 DONE |
Rules:
- Room-mates only. You can write only to someone who shares at least one room with you. An unknown id, a deleted account and a person you share no room with ALL give the same 404 "Syncmate not found", so nobody can find out who has an account. Signup and login behavior is unchanged.
- Privacy of messages: only the sender and the recipient can open a message. For any other person, and for a message that does not exist, the answer is the same 404, so ids cannot be probed. Admins have no extra access in the app.
- Blocks: a blocked sender still gets the normal 201 (they are not told) and sees the message in their Sent folder, but it is never delivered: the recipient never sees it and it never counts as unread. Blocking someone does not remove old messages. You can block someone you share a room with or who has written to you (otherwise 404).
- Limits (429 when exceeded): 20 messages per hour and 100 per day per user, and at most 10 per hour to the same person. Message size is capped as above (422).
- Plain text only. Subject and body are shown with `textContent`, links are NOT made clickable (phishing risk), and nothing is ever rendered as HTML.
- Never log message content, subjects or recipient emails (log only the kind and a success flag).
- Privacy page and Terms (PR 4): must say that Inbox messages are not end-to-end encrypted, are stored on our servers, and that RoomSync operators could technically access stored messages; room admins cannot read them in the app.
- Retention: messages stay until both people remove them or an account is deleted (then the message text may remain for the other person, shown as "Deleted user"). The retention schedule is still to be decided with the Privacy page.

## Messaging (T3: AFTER LAUNCH, do NOT build yet)
Listed so nobody invents conflicting endpoints. Exact endpoints are added here BEFORE any code is written.
- Instant delivery (WebSockets) for room chat, typing indicators, presence.
- Direct messages are replaced by the Inbox above (decided Nov 7). No end-to-end encrypted direct messages are planned for now.
- Audio and video calls (press Call, the other person is rung), 1-on-1 and room group calls, through an embedded call service. The ring uses the WebSocket.
- Live co-editing docs in Files.
- Nothing in RoomSync is end-to-end encrypted. Do not claim it anywhere in the product or docs.

## Frontend conventions (all pages)
- API address: `js/config.js` sets `window.ROOMSYNC.API_BASE` (empty in production, `http://localhost:8000` on Live Server ports).
- The login token is stored in `localStorage` as `roomsync_token`, the user as `roomsync_user`. Send `Authorization: Bearer <token>`. On any 401, clear both keys and go to `login.html`.
- Render all user text with `textContent`, never `innerHTML`.
- Pages already wired to the API: `login.html`, `home.html` (rooms, members, create, join, logout, the week board and New TODO). Marked with `<body data-api-rooms>`; other pages still show demo data.
- Frontend files are sent with `Cache-Control: no-cache`, so browsers re-check them on every load (an unchanged file costs a tiny 304 reply).

## Health
GET `/health` returns `{"status":"ok"}` (no auth).