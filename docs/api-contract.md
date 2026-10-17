# RoomSync API contract (source of truth)

Base URL: `http://localhost:8000` locally. All bodies are JSON. Auth = header `Authorization: Bearer <token>`.
Errors look like `{"detail": "message"}`. Status codes: 401 not logged in, 403 not allowed, 404 not found, 409 conflict, 422 bad input.
Datetimes are ISO 8601 strings (UTC), e.g. `"2026-08-13T15:59:00Z"`. Interactive docs: `/docs`.

## Auth (Thomas): DONE in skeleton
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | /auth/signup | `{email, name, password(min 8)}` | 201 `{access_token, token_type, user:{id,email,name}}` |
| POST | /auth/login | `{email, password}` | `{access_token, token_type, user}` |
| GET | /auth/me | none | `{id,email,name}` |

## Rooms (Thomas): DONE in skeleton
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | /rooms | `{name}` | 201 `{id,name,invite_code,role:"admin",member_count}` |
| GET | /rooms | none | `[{id,name,invite_code,role,member_count}]` (rooms I'm in) |
| POST | /rooms/join | `{invite_code}` | `{id,name,invite_code,role,member_count}` |
| GET | /rooms/{room_id}/members | none | `[{user_id,name,role,joined_at}]` |
| POST | /rooms/{room_id}/leave | none | 204. Last member out deletes the room. Sole admin can't leave while others remain (400). |

## Tasks (Friend): TODO
Task object: `{id, room_id, title, type, subject, due_at, status:"pending|approved|rejected", created_by, created_by_name}`
`type` is one of `exam, quiz, case-study, activity, seatwork, assignment` or a custom type name.
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | /rooms/{room_id}/tasks | `{title, type, subject?, due_at?}` | 201 task (status starts `pending`) |
| GET | /rooms/{room_id}/tasks?week_start=YYYY-MM-DD | none | `[task]` approved tasks due that Sun to Sat week, sorted by due_at |
| GET | /rooms/{room_id}/calendar?month=YYYY-MM | none | `[task]` approved tasks due that month |
| DELETE | /tasks/{task_id} | none | 204 (creator or room admin only) |

## Approvals (Friend): TODO
Default rule (change here first if we decide otherwise): a task is approved when ONE room member other than the creator approves; rejected when one other member rejects; first vote decides. Creator can't vote on own task. One vote per member per task.
| Method | Path | Body | Returns |
|---|---|---|---|
| GET | /rooms/{room_id}/approvals | none | `[task]` with status `pending` |
| POST | /tasks/{task_id}/approve | none | task (updated) |
| POST | /tasks/{task_id}/reject | none | task (updated) |

## Notes (Friend): TODO
Note: `{id, room_id, title, content, author_id, author_name, created_at}`
| Method | Path | Body | Returns |
|---|---|---|---|
| GET | /rooms/{room_id}/notes | none | `[note]` newest first |
| POST | /rooms/{room_id}/notes | `{title, content}` | 201 note |
| DELETE | /notes/{note_id} | none | 204 (author or admin only) |

## Discussion (Friend): TODO
Message: `{id, room_id, author_id, author_name, body, created_at}`
| Method | Path | Body | Returns |
|---|---|---|---|
| GET | /rooms/{room_id}/messages?limit=50 | none | `[message]` oldest first |
| POST | /rooms/{room_id}/messages | `{body}` | 201 message |

## Profile and custom task types (Friend): TODO
| Method | Path | Body | Returns |
|---|---|---|---|
| PATCH | /users/me | `{name?}` | `{id,email,name}` |
| GET | /users/me/task-types | none | `[{id,name,color}]` |
| POST | /users/me/task-types | `{name(max 20), color:"#rrggbb"}` | 201 `{id,name,color}` (409 if name exists) |
| DELETE | /users/me/task-types/{id} | none | 204 |

## Settings (later, if time)
Per-user preferences (show-empty-days, task colour overrides) currently live in browser `localStorage`. Moving them to the account is a Week 2 stretch goal.
