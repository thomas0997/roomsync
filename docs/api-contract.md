# RoomSync API contract (source of truth)

Base URL: `http://localhost:8000` locally. All bodies are JSON. Auth = header `Authorization: Bearer <token>`.
Errors look like `{"detail": "message"}`. Status codes: 401 not logged in, 403 not allowed, 404 not found, 409 conflict, 422 bad input.
Datetimes are ISO 8601 strings (UTC), e.g. `"2026-08-13T15:59:00Z"`. Interactive docs: `/docs`.

## Roles (read this first)
- A room has members. Each member is either `admin` or `member`.
- The room creator is the first admin.
- Promote to admin: the creator first. Once other admins exist, any admin can promote.
- Demote to member: the creator only. The creator can never be demoted.
- Only admins approve or reject tasks (see Approvals).

## Auth (Thomas): DONE
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | /auth/signup | `{email, name, password(min 8)}` | 201 `{access_token, token_type, user:{id,email,name}}` |
| POST | /auth/login | `{email, password}` | `{access_token, token_type, user}` |
| GET | /auth/me | none | `{id,email,name}` |

## Rooms (Thomas)
| Method | Path | Body | Returns | Status |
|---|---|---|---|---|
| POST | /rooms | `{name}` | 201 `{id,name,invite_code,role:"admin",member_count}` | DONE |
| GET | /rooms | none | `[{id,name,invite_code,role,member_count}]` (rooms I'm in) | DONE |
| POST | /rooms/join | `{invite_code}` | `{id,name,invite_code,role,member_count}` | DONE |
| GET | /rooms/{room_id}/members | none | `[{user_id,name,role,joined_at}]` | DONE |
| POST | /rooms/{room_id}/leave | none | 204. Last member out deletes the room. The only admin can't leave while others remain (400). | DONE |
| POST | /rooms/{room_id}/members/{user_id}/role | `{role: "admin" or "member"}` | `{user_id,name,role,joined_at}`. Admin only. Promote: creator, or any admin once others are admins. Demote: creator only; the creator can never be demoted. | TODO |

## Tasks (Daniel): TODO
Task object: `{id, room_id, title, type, subject, due_at, status:"pending|approved|rejected", created_by, created_by_name}`
`type` is one of `exam, quiz, case-study, activity, seatwork, assignment` or a custom type name.
Only `approved` tasks appear on the board and calendar.
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | /rooms/{room_id}/tasks | `{title, type, subject?, due_at?}` | 201 task. Status is `pending`, EXCEPT `approved` immediately when the creator is the room's only admin. |
| GET | /rooms/{room_id}/tasks?week_start=YYYY-MM-DD | none | `[task]` approved tasks due that Sun to Sat week, sorted by due_at |
| GET | /rooms/{room_id}/calendar?month=YYYY-MM | none | `[task]` approved tasks due that month |
| DELETE | /tasks/{task_id} | none | 204 (creator or room admin only) |

## Approvals (Daniel): TODO
Rules:
- Only room admins approve or reject tasks. Members submit tasks as `pending`.
- A task created by a member: any admin can decide it.
- A task created by an admin: another admin must decide it. An admin cannot approve or reject their own task, UNLESS they are the room's only admin. If the room has exactly one admin, that admin's new tasks are auto-approved at creation.
- The first admin decision is final.
- The Approve tab = pending tasks in the room, visible to admins only.

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | /rooms/{room_id}/approvals | none | `[task]` with status `pending` (admin only) |
| POST | /tasks/{task_id}/approve | none | task (updated). Admin only. |
| POST | /tasks/{task_id}/reject | none | task (updated). Admin only. |

## Notes (Daniel): TODO
Note: `{id, room_id, title, content, author_id, author_name, created_at}`
| Method | Path | Body | Returns |
|---|---|---|---|
| GET | /rooms/{room_id}/notes | none | `[note]` newest first |
| POST | /rooms/{room_id}/notes | `{title, content}` | 201 note |
| DELETE | /notes/{note_id} | none | 204 (author or admin only) |

## Discussion (Daniel): TODO
Message: `{id, room_id, author_id, author_name, body, created_at}`
| Method | Path | Body | Returns |
|---|---|---|---|
| GET | /rooms/{room_id}/messages?limit=50 | none | `[message]` oldest first |
| POST | /rooms/{room_id}/messages | `{body}` | 201 message |

## Profile and custom task types (Daniel): TODO
| Method | Path | Body | Returns |
|---|---|---|---|
| PATCH | /users/me | `{name?}` | `{id,email,name}` |
| GET | /users/me/task-types | none | `[{id,name,color}]` |
| POST | /users/me/task-types | `{name(max 20), color:"#rrggbb"}` | 201 `{id,name,color}` (409 if name exists) |
| DELETE | /users/me/task-types/{id} | none | 204 |

## Settings (later, if time)
Per-user preferences (show-empty-days, task colour overrides) currently live in browser `localStorage`. Moving them to the account is a Week 2 stretch goal.