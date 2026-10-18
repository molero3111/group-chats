# group-chats: Pluggable Realtime Transport (Channels | Columba) — Implementation Plan (PR 2 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One codebase where `CHAT_TRANSPORT=channels|columba` picks the realtime transport, with the same UI and models in both modes, and with the identity-spoofing, anonymous-connect and XSS bugs fixed along the way.

**Architecture:** Sending becomes an authenticated HTTP POST in both modes: Django saves the `Message`, then publishes it through a `Transport` (Channels group send, or Columba `POST /api/v1/publish`) after the transaction commits. Browsers only receive. One `chat.js` connects either a plain WebSocket (Channels) or a Phoenix socket (Columba), renders with `textContent`, dedupes on message id, and catches up over HTTP after every (re)connect, because Columba stores nothing.

**Tech Stack:** PR 1's stack plus requests 2.34.2 and PyJWT 2.15.1; phoenix.js 1.8.15 (vendored); responses (test only, latest).

**Spec:** `~/.claude/scratch/columba/audit-2026-10-18/ideas-chat-apps.md` §1 (lines 16-114). Columba contract with file:line refs: `~/.claude/scratch/chat_in_django/scratchpad.md` § "Columba contract". Upstream: `~/Documents/projects/erlang/columba/docs/superpowers/specs/2026-10-03-columba-mvp-design.md` §6.

**Base:** branch `feat/group-chats-modernize` (PR 1). This plan's branch: `feat/pluggable-transport`.

## Global Constraints

- JWT: HS256 with `COLUMBA_SIGNING_SECRET`; claims `app` (=`COLUMBA_APP_ID`), `sub` (=`str(user.id)`), `topics` (list, no `topic:` prefix), `iat` (now), `exp` (now + 600). Exp must be ≤ 24 h.
- Topic and group names use the room **id**, not the slug (slug is a free CharField; Columba accepts only `[A-Za-z0-9:_\-.]{1,128}`). Columba topic: `room:<id>`; joined as `topic:room:<id>`. Channels group: `chat_<id>`.
- Event name `message.new`. Publish `id` = `str(message.id)`.
- Payload, identical in both transports: `{"id": int, "room": slug, "user": {"id": int, "username": str}, "content": str, "created_at": ISO 8601 UTC}`.
- Publish: `requests.post(f"{COLUMBA_URL}/api/v1/publish", json=…, headers={"Authorization": f"Bearer {COLUMBA_API_KEY}"}, timeout=2)`. Content-Type must be JSON. Payload ≤ 64 KB, so cap `content` at 4000 characters at the view.
- Publish failures (timeout, connection error, 4xx, 5xx, 429) are logged at WARNING with the status and Columba's `error.code`, never raised to the sender: the message is already saved and recipients catch up on reconnect. No retry loop in the request cycle.
- Browser: Phoenix `Socket(COLUMBA_SOCKET_URL, {params: () => ({token})})` (audit A-09). The token is fetched from Django before the first connect and again on `onError`, one request in flight at a time. A 401/403 from the token endpoint calls `socket.disconnect()`.
- Settings via decouple: `CHAT_TRANSPORT` (default `channels`), `COLUMBA_URL` (server-side base, e.g. `https://staging-columba.emmanuelcodinghub.com` or `http://columba:4000`), `COLUMBA_SOCKET_URL` (browser-facing, e.g. `wss://staging-columba.emmanuelcodinghub.com/socket`), `COLUMBA_APP_ID`, `COLUMBA_API_KEY`, `COLUMBA_SIGNING_SECRET`. With `columba` selected and any of these empty, raise `ImproperlyConfigured` at startup. Values never go in the repo; `.env.example` gets the key names with empty values.
- No Columba feature workarounds: anything Columba lacks goes to the columba coordinator session as a message.
- The A-09 client pattern is a draft (branch `fix/a-09-snippet-token-refresh`, unmerged). The coordinator will message when it merges. Before PR 2 opens, diff `chat.js` against the merged snippet and sync.
- One token per room page lists exactly one topic, so the 50-topic cap doesn't apply. A future lobby view would need a per-user topic (`user:<id>`).

## Review Focus

1. Columba down or rate-limited (timeout, 503, 429) while a user sends: the sender gets 201, the message persists, a WARNING is logged, and nothing raises. Tested in Task 1.
2. Token expiry on a long-open tab: after a disconnect, the client must reconnect with a fresh token, not loop on the stale one. Tested in Task 2 (endpoint) and checked in QA (wait past the 10-min token life, toggle the browser offline/online, and confirm the reconnect fetched a new token and succeeded).
3. Duplicate delivery (optimistic append + broadcast echo + catch-up overlap): each message renders exactly once. Checked in QA. The dedupe key is `payload.id`.
4. Hostile content `<img src=x onerror=alert(1)>` as message body or username renders as text in history, live and catch-up. Tested in Task 3 (history/catch-up JSON) and checked in QA (live).
5. Access control: anonymous users and unknown rooms get 401/404 on token, send and catch-up, and an anonymous websocket is rejected. Tested in Tasks 2-4.

---

### Task 1: Transport seam and both publishers

**Files:**
- Create: `room/transports/__init__.py` (`get_transport() -> Transport`, cached per process, picks by `settings.CHAT_TRANSPORT`)
- Create: `room/transports/base.py` (`class Transport(Protocol)`: `publish(room: Room, event: str, payload: dict) -> None`, `client_config(request, room: Room) -> dict`)
- Create: `room/transports/channels.py` (`ChannelsTransport`)
- Create: `room/transports/columba.py` (`ColumbaTransport`, `mint_token(user, room, now: int | None = None) -> str`)
- Create: `room/payloads.py` (`message_payload(message: Message) -> dict`, `room_topic(room) -> str` = `f"room:{room.id}"`, `room_group(room) -> str` = `f"chat_{room.id}"`)
- Modify: `groupchats/settings.py` (the six settings; `ImproperlyConfigured` check), `requirements.txt` (+requests, PyJWT), `requirements-dev.txt` (+responses)
- Test: `room/tests/test_transports.py` (turn `room/tests.py` into a `room/tests/` package; move PR 1's tests to `room/tests/test_views.py`)

**Interfaces:**
- Produces: `get_transport()`, `message_payload()`, `room_topic()`, `room_group()`, `mint_token()`. `client_config` returns `{"kind": "channels", "path": "/ws/<slug>/"}` or `{"kind": "columba", "socket_url": COLUMBA_SOCKET_URL, "topic": "room:<id>", "token_url": reverse("room-token", slug)}`.

- [ ] **Step 1: Write the failing tests:**
  - `test_message_payload_shape` checks exact keys and types, and that `created_at` ends with `Z` or `+00:00`.
  - `test_columba_publish_request` uses `responses` to capture the POST and asserts the URL `…/api/v1/publish`, the `Authorization: Bearer <key>` header, the JSON body `{"topics": ["room:<id>"], "event": "message.new", "payload": …, "id": "<id>"}` and `timeout=2` (wrap with `mock.patch("room.transports.columba.requests.post", wraps=requests.post)` and assert the call kwargs).
  - `test_columba_publish_failures_are_logged_not_raised` is parametrized over 429 `{"error": {"code": "rate_limited", "retry_after": 3}}`, 503, `requests.Timeout` and `ConnectionError`. Each case asserts `assertLogs("room.transports", "WARNING")` and that nothing raises.
  - `test_mint_token_claims` decodes with the secret and asserts `app`, `sub == str(user.id)`, `topics == ["room:<id>"]`, `exp - iat == 600`, alg HS256.
  - `test_channels_publish_group_send` uses the in-memory layer: `group_add` a test channel to `chat_<id>`, publish, `receive` → `{"type": "chat.message", "payload": …}`.
  - `test_columba_misconfigured_raises` checks that `override_settings(CHAT_TRANSPORT="columba", COLUMBA_API_KEY="")` → `ImproperlyConfigured` from `get_transport()` (clear its cache first).
- [ ] **Step 2: Run the verify command, expect FAIL.**
- [ ] **Step 3: Implement.** Logger name `room.transports`. Never log the API key, the token or the payload content.
- [ ] **Step 4: Run the verify command → PASS. Step 5: Commit.**

### Task 2: Token endpoint

**Files:**
- Modify: `room/views.py` (`RoomTokenView`), `room/urls.py` (`<slug:slug>/token/` name `room-token`)
- Test: `room/tests/test_views.py`

- [ ] **Step 1: Write the failing tests:**
  - Anonymous GET gives 401 JSON `{"error": "unauthenticated"}`, not a 302.
  - An unknown slug gives 404.
  - Authenticated in columba mode gives 200 `{"token": …}`, and the token decodes with the claims from Task 1.
  - In channels mode it gives 404.
  - The response has `Cache-Control: no-store`.
- [ ] **Step 2-4: Run to fail, implement, then run the verify command → PASS. Step 5: Commit.**

### Task 3: Send and catch-up endpoints

**Files:**
- Modify: `room/views.py` (`RoomMessagesView`: GET + POST), `room/urls.py` (`<slug:slug>/messages/` name `room-messages`); `RoomView` uses `get_object_or_404`
- Test: `room/tests/test_views.py`

**Interfaces:**
- POST takes form-encoded or JSON `{"content": str}` and a CSRF header. It returns 201 with `message_payload`, and calls `transaction.on_commit(lambda: get_transport().publish(room, "message.new", payload))`. It returns 400 `{"error": "empty"}` or `{"error": "too_long"}` (> 4000 chars after strip).
- GET `?after=<id>` returns 200 `{"messages": [payload…]}` ascending by id, max 100, for messages with `id > after`. A non-integer `after` gives 400.

- [ ] **Step 1: Write the failing tests:**
  - The author comes from `request.user` even if the body carries `username`/`user` fields (spoofing fix).
  - Missing CSRF gives 403 (use `Client(enforce_csrf_checks=True)`).
  - Anonymous gives 401. An unknown room gives 404.
  - Empty and whitespace-only content gives 400 `empty`. 4001 characters gives 400 `too_long`.
  - Publish is called once with the payload after commit (`self.captureOnCommitCallbacks(execute=True)` + a mock transport).
  - Catch-up returns only newer messages, in order, capped at 100. Hostile content comes back verbatim in JSON, never HTML-rendered.
  - An unknown room page gives 404, not 500.
- [ ] **Step 2-4: Run to fail, implement, then run the verify command → PASS. Step 5: Commit.**

### Task 4: Channels consumer becomes receive-only

**Files:**
- Modify: `room/consumers.py` (`ChatConsumer`), `room/routing.py`
- Test: `room/tests/test_consumers.py` (`channels.testing.WebsocketCommunicator`, `TransactionTestCase` or `database_sync_to_async` fixtures)

- [ ] **Step 1: Write the failing tests:**
  - An anonymous connect is rejected (`connected is False`), and no group membership is left behind.
  - An unknown room is rejected.
  - An authenticated connect accepts. A `ChannelsTransport().publish(...)` then arrives as a text frame equal to `json.dumps({"event": "message.new", "payload": payload})`.
  - Client text frames are ignored: no `Message` is created and nothing is broadcast.
- [ ] **Step 2-4: Run to fail, implement** (`connect` returns right after `close()`; group `room_group(room)`; `receive` is a no-op; handler `chat_message(event)` sends the wrapped frame; no `print`). **Then run the verify command → PASS. Step 5: Commit.**

### Task 5: `chat.js`, vendored Phoenix client, room template

**Files:**
- Create: `room/static/room/vendor/phoenix-1.8.15.js` (`priv/static/phoenix.js` from the npm tarball, with its MIT header kept; record its sha256 in the commit message)
- Create: `room/static/room/chat.js`
- Modify: `room/templates/room.html` (delete the inline socket script; `{{ chat_config|json_script:"chat-config" }}`; load `phoenix-1.8.15.js` only when `kind == "columba"`), `room/views.py` (`RoomView` passes `chat_config = get_transport().client_config(request, room)` plus `messages_url` and `current_user_id`)

**Behaviour of `chat.js`** (an IIFE, no build step, no globals except reading `window.Phoenix`):
- `renderMessage(payload)` builds nodes with `textContent` only. It skips the message if `payload.id` is already in a `Set` of rendered ids. History rendered server-side seeds the set from `data-id` attributes. Own messages get the right-aligned class from PR 1's styles.
- `catchUp()` GETs `messages_url?after=<max rendered id>` and renders the results. It runs after every successful (re)connect: the `onopen` of the WebSocket, and the `join().receive("ok")` of the Phoenix channel.
- **Channels:** connect to `` `${wsProto}://${location.host}${config.path}` ``. On close, reconnect with backoff of 1, 2, 4… seconds, capped at 30. Frames with `event === "message.new"` call `renderMessage(frame.payload)`.
- **Columba:** `fetchToken()` returns the existing in-flight promise if there is one. On 401/403 it disconnects and shows a "signed out, reload" notice. `socket.onError(() => fetchToken())`. Connect only after the first token. `channel = socket.channel("topic:" + config.topic)`. `channel.on("event", e => e.name === "message.new" && renderMessage(e.payload))`. A join `error` of `unauthorized` triggers a token refresh and rejoin. The client never calls `channel.push`.
- **Send:** POST to `messages_url` with `X-CSRFToken`. On 201, render the response payload (the optimistic append is the server's echo, so dedupe makes the broadcast a no-op). On 4xx, show the error inline and keep the input text.
- A banner shows the transport: a small badge in the room header reading "Realtime: Django Channels" or "Realtime: Columba", from `chat_config.kind`.

- [ ] **Step 1: Write the failing test** `test_room_page_config` checks that the room page contains a `chat-config` json_script with the right `kind`, that `phoenix-1.8.15.js` is present only in columba mode, and that no inline `new WebSocket` remains in the HTML.
- [ ] **Step 2-4: Run to fail, implement, then run the verify command → PASS.**
- [ ] **Step 5: Browser check in both modes** (two users, two tabs). The message appears once in each tab. A hostile body renders as text. Toggling the network offline and online catches up the messages sent meanwhile.
- [ ] **Step 6: Commit.**

### Task 6: Run modes, env, docs

**Files:**
- Modify: `start.sh` (`CHAT_TRANSPORT=columba` and non-local → `gunicorn groupchats.wsgi:application -b 0.0.0.0:8000 -w ${WEB_CONCURRENCY:-3}`; channels → daphne as before; local → runserver either way)
- Modify: `.env.example` (`CHAT_TRANSPORT=channels` and the five `COLUMBA_*` keys, empty), `kubernetes/django/config-map.yml.example` (`CHAT_TRANSPORT`, `COLUMBA_URL`, `COLUMBA_SOCKET_URL`), `.env-kuber.example` (`COLUMBA_API_KEY=`, `COLUMBA_SIGNING_SECRET=`, `COLUMBA_APP_ID=`)
- Modify: `README.md`, adding a "Realtime transports" section: how each mode works, the env keys, local Columba (`http://columba.localhost`, socket `ws://columba.localhost/socket`), staging Columba, and that Columba keeps no history so Django is the source of truth.

- [ ] **Step 1: Write the failing test** `test_settings_example_lists_columba_keys`: `.env.example` contains each of the six key names, and every `COLUMBA_*` value is empty.
- [ ] **Step 2-4: Run to fail, implement, then run the verify command → PASS.**
- [ ] **Step 5: Commit.**
