# group-chats: Per-Room Sequence Numbers and Gap-Only Catch-Up — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop every open tab from sending `GET /rooms/<slug>/messages/?after=<id>` about 1 s after every live burst; fetch only when a gap is actually detected, or on join, reconnect or tab focus.

**Architecture:** Each message gets a per-room sequence number `seq` (1, 2, 3… within its room), assigned under a row lock on the room when the message is saved, and carried in every payload. The browser keeps `syncedSeq`, the highest seq it holds with no gaps before it. A live or own message with `seq === syncedSeq + 1` advances it with no request. A larger seq, or an unknown one (`null`), means something was missed, so it runs the existing id-based catch-up. The per-burst timer (`LIVE_SYNC_DELAY`) is removed.

**Tech Stack:** Django 6.1 (PostgreSQL in prod, SQLite in tests), vanilla JS, `node --test` (Node 22, no npm dependencies) for the pure client logic.

**Spec:** the 2026-11-22 conversation with Emmanuel. Problem: N readers in a room → N GETs to Django per message burst, almost all empty, which defeats Columba's fan-out. Decision: per-room seq plus gap-only catch-up; keep the join, reconnect and visibility catch-ups. The Columba contract is unchanged (the payload is opaque to Columba; the 64 KB cap is unaffected).

## Global Constraints

- Migrations must be expand/contract: the release before this one (94b1bd7) must keep working on the new schema, because a failed health gate reverts the image without reverting the schema. The old code inserts `Message` rows without `seq` and `Room` rows without `last_seq`.
- The catch-up endpoint stays `GET ?after=<id>` with page size 100 (`CATCH_UP_LIMIT`), unchanged.
- No npm `package.json` or dependencies; the JS tests use only `node:test` and `node:assert`.
- Client code builds DOM with `textContent` only (existing XSS rule).

## Review Focus

1. **Revert window:** messages created by the previous image after the migration have `seq = NULL`. The client must treat a `null` seq (on a payload or as the page's `latest_seq`) as "unknown": catch up, never compare numbers. Test in Task 3 (`unknown seq triggers catch-up`) and Task 1 (`test_payload_seq_is_none_for_legacy_rows`).
2. **Concurrent sends in one room** must not get the same seq. The row lock (`select_for_update`) is a no-op on SQLite, so tests can't prove the race; the `UniqueConstraint(room, seq)` makes a lost race fail loudly instead of silently. Task 1 asserts the constraint exists; a reviewer checks the lock is taken inside the same `transaction.atomic` block as the insert.
3. **Out-of-order publish** (A commits seq 5 and B seq 6, but B's publish lands first): the client sees 6 with `syncedSeq = 4`, catches up (gets 5 and 6), and then ignores the late 5 as a duplicate. Task 3 (`late duplicate is ignored`).
4. **Live event during an in-flight catch-up** must not be lost. Today `catchUp()` returns the running promise, so a gap revealed mid-fetch is never fetched. A call during a run must schedule exactly one more run after it. Task 3 (`catch-up requested while running runs once more`).
5. **Own message after missed messages:** the POST 201 response goes through the same gap check, so sending after a silent gap also repairs it. Task 3 (`own message with a gap triggers catch-up`).

**As built (after final review):** the migrations are 0002 (fields, `editable=False`), 0003 (set-based `ROW_NUMBER()` backfill) and 0004 (unique index built `CONCURRENTLY` on PostgreSQL, then attached as the constraint). Each send also numbers any rows the previous release left without a seq, so a deploy-overlap row with a lost publish shows up as a skipped seq. Steps below describe the original plan.

Accepted trade-off (no test): if the *last* message of a burst is lost, no later event reveals the gap until the next message, reconnect or tab focus. Publish failures are logged server-side (`Columba publish failed/answered`).

---

### Task 1: `seq` on Message and `last_seq` on Room, with backfill

**Files:**
- Modify: `room/models.py`
- Create: `room/migrations/0002_room_last_seq_message_seq.py` (schema), `room/migrations/0003_backfill_message_seq.py` (data)
- Modify: `room/payloads.py`
- Test: `room/tests/test_seq.py` (new)

**Interfaces:**
- Produces: `Room.last_seq: PositiveIntegerField(default=0, db_default=0)`; `Message.seq: PositiveIntegerField(null=True, blank=True)`; `Meta.constraints = [UniqueConstraint(fields=['room', 'seq'], name='message_room_seq_unique')]`; `message_payload(m)` gains `'seq': m.seq` (int or `None`).

- [ ] **Step 1: Write failing tests** in `room/tests/test_seq.py`:
  - `test_payload_includes_seq`: a Message saved with `seq=3` → `message_payload(m)['seq'] == 3`.
  - `test_payload_seq_is_none_for_legacy_rows`: `seq=None` → `'seq' in payload and payload['seq'] is None`.
  - `test_room_seq_unique`: two Messages in one room with `seq=1` → `IntegrityError`.
  - `test_null_seq_not_unique`: two Messages in one room with `seq=None` save fine (the revert window).
  - `test_backfill_numbers_per_room_by_id`: use `django.db.migrations.executor.MigrationExecutor` (migrate to `0002`, create rooms A and B, messages A1 B1 A2 A3 B2 in that id order with `seq=None`, migrate to `0003`) → A's seqs `[1, 2, 3]`, B's `[1, 2]`, A `last_seq == 3`, B `last_seq == 2`, and a room with no messages keeps `last_seq == 0`.
- [ ] **Step 2: Run** `python manage.py test room.tests.test_seq --settings=groupchats.settings_test` → FAIL (no field `seq`).
- [ ] **Step 3: Implement.** Add the fields and constraint; `makemigrations room` for 0002 (rename it to `0002_room_last_seq_message_seq.py`). In 0003, `RunPython(backfill, migrations.RunPython.noop)`: per room, iterate messages `order_by('id')` and number them with `bulk_update(..., ['seq'], batch_size=500)`, then set `last_seq` to the count. Numbering every row per room, including any pre-existing seqs, is fine: 0003 runs once, before any new code writes seq. Add `'seq'` to `message_payload`.
- [ ] **Step 4: Run** the same command → PASS; then `python manage.py makemigrations --check --dry-run --settings=groupchats.settings_test` → "No changes detected".
- [ ] **Step 5: Commit** `feat(room): add per-room message sequence numbers`.

### Task 2: Assign seq on send; expose it to the page

**Files:**
- Modify: `room/views.py` (`RoomMessagesView.post`, `RoomView.get`)
- Test: `room/tests/test_api.py` (`RoomMessagesPostTests`), `room/tests/test_views.py` (`RoomPageConfigTests`)

**Interfaces:**
- Consumes: Task 1 fields.
- Produces: POST 201 body and published payload carry `seq`; `chat_config['latest_seq']` is the newest message's seq in the room: `0` for an empty room, and `None` when the newest row has a NULL seq.

- [ ] **Step 1: Write failing tests:**
  - `RoomMessagesPostTests.test_seq_increments_per_room`: POST twice to room A and once to room B → the response `seq`s are `1, 2` and `1`; `Room A.last_seq == 2`.
  - `RoomMessagesPostTests.test_published_payload_has_seq`: the mocked transport's `publish` payload has the same `seq` as the 201 body.
  - `RoomMessagesPostTests.test_rejected_message_does_not_consume_seq`: an empty body (400) and a rate-limited POST (429) leave `last_seq` unchanged.
  - `RoomPageConfigTests.test_latest_seq_in_config`: a room with messages seq 1..3 → the config's `latest_seq == 3`; an empty room → `0`; a room whose newest message has `seq=None` → `None`.
- [ ] **Step 2: Run** `python manage.py test room --settings=groupchats.settings_test` → the new tests FAIL.
- [ ] **Step 3: Implement.** In `post`, after all validation, inside `with transaction.atomic():` do `locked = Room.objects.select_for_update().get(pk=room.pk)`, increment `locked.last_seq` in Python (the lock makes that safe, and we need the value), `save(update_fields=['last_seq'])`, then `Message.objects.create(..., seq=locked.last_seq)`. Register the `on_commit` publish inside that block, as now. In `RoomView.get`, take `latest_id` and `latest_seq` from one `values_list('id', 'seq').first()` on the existing `messages_query`; empty → `(0, 0)`.
- [ ] **Step 4: Run** the full suite → PASS.
- [ ] **Step 5: Commit** `feat(room): assign a per-room seq when a message is sent`.

### Task 3: Gap-only catch-up in the client

**Files:**
- Create: `room/static/room/sync.js` (pure logic, no DOM)
- Create: `room/static/room/sync.test.mjs`
- Modify: `room/static/room/chat.js`, `room/templates/room.html` (load `sync.js` before `chat.js`), `.github/workflows/ci.yml` (add `actions/setup-node@v5` with `node-version: '22'` and `node --test 'room/static/room/*.test.mjs'`)
- Test: `room/tests/test_views.py` (the page includes `room/sync.js` before `room/chat.js`)

**Interfaces:**
- Produces `sync.js`, exposed as `window.ChatSync` and as `module.exports` when `module` exists (so `sync.test.mjs` can `import` it via `createRequire`):
  - `classify(syncedSeq: number|null, seq: number|null) -> 'next' | 'gap' | 'old'`: `'next'` iff both are numbers and `seq === syncedSeq + 1`; `'old'` iff both are numbers and `seq <= syncedSeq`; otherwise `'gap'` (including any `null`).
  - `createCatchUp(run: () => Promise<void>) -> () => Promise<void>`: coalesces calls; a call while `run` is in flight makes exactly one more `run` start after the current one settles (however many calls arrived); it returns a promise for the run that will cover the call. Errors from `run` are swallowed.
- `chat.js` state: `syncedSeq` (init `config.latest_seq`) alongside `syncedId`.

- [ ] **Step 1: Write failing tests** in `sync.test.mjs`:
  - `classify`: `(4,5)→'next'`, `(4,7)→'gap'`, `(4,4)→'old'`, `(4,2)→'old'`, `(0,1)→'next'` (empty room), `(null,5)→'gap'`, `(4,null)→'gap'` (unknown seq triggers catch-up).
  - `late duplicate is ignored`: `(6,5)→'old'`.
  - `createCatchUp`: `catch-up requested while running runs once more`: `run` resolves on a manual deferred; call 3 times during the first run → `run` was called 2 times total after both settle. `idle calls run once each`: 2 sequential awaited calls → 2 runs. `a rejected run is swallowed and the next call still runs`.
- [ ] **Step 2: Run** `node --test 'room/static/room/*.test.mjs'` → FAIL (module not found).
- [ ] **Step 3: Implement `sync.js`.**
- [ ] **Step 4: Wire `chat.js`.**
  - Replace `catchingUp` with `const catchUp = ChatSync.createCatchUp(fetchMissing)`, where `fetchMissing` is today's loop body. After each page it sets `syncedId` to the last id and `syncedSeq` to the last message's `seq` (which may be `null`).
  - Add `accept(payload)`: `renderMessage(payload)`, then switch on `classify(syncedSeq, payload.seq)`:
    - `'next'`: set `syncedSeq = payload.seq` and `syncedId = max(syncedId, payload.id)`, with no request.
    - `'gap'`: call `catchUp()`.
    - `'old'`: do nothing.
  - Use `accept` for Channels `message.new`, Columba `message.new`, and the POST 201 body.
  - Delete `LIVE_SYNC_DELAY`, `liveSyncTimer` and `renderLive`.
  - Keep the catch-ups on Channels `onopen`/`onclose`, Columba join `ok`, and `visibilitychange`.
  - Update the header comment to say catch-up runs on connect, on tab focus and when a seq gap is seen.
- [ ] **Step 5: Run** `node --test 'room/static/room/*.test.mjs'` and the Django suite → PASS. Manual check with `runserver` and two tabs in Channels mode: DevTools → Fetch/XHR shows no `messages/?after=` after a live message; stopping Redis publish (or a temporary `raise` in `publish`) for one message, then sending another, shows exactly one catch-up GET that fills the gap.
- [ ] **Step 6: Commit** `feat(room): catch up only when a message gap is detected`.

### Task 4: Docs

**Files:**
- Modify: `README.md`, the paragraph under the transport table ("Columba stores nothing…").

- [ ] **Step 1:** Replace "After every connect or reconnect, the page catches up…" with: the page catches up with `GET …?after=<last id>` after every connect or reconnect, on tab focus, and when a message's per-room `seq` skips a number. In-order live messages cause no requests. Duplicates are dropped by id.
- [ ] **Step 2: Commit** `docs(readme): describe gap-only catch-up`.
