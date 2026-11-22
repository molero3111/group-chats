// Room page client. Receives over Django Channels or Columba (receive-only), sends over HTTP.
// Django is the source of truth for history, and the transports store nothing, so the page
// catches up over HTTP after every (re)connect, when the tab is shown again, and when a
// message's per-room seq skips a number. Messages that arrive in order cost no request.
(() => {
    'use strict';

    const config = JSON.parse(document.getElementById('chat-config').textContent);
    const list = document.getElementById('chat-messages');
    const form = document.getElementById('chat-form');
    const input = document.getElementById('chat-message-input');
    const button = document.getElementById('chat-message-btn');
    const status = document.getElementById('chat-status');
    const errorBox = document.getElementById('chat-error');

    const CATCH_UP_PAGE = 100; // the server's page size for ?after=
    const rendered = new Set();
    let lastId = 0; // highest id on screen, from any source; only used to keep id order
    // Highest id known to have no gaps before it. Only HTTP results move it: a live event can
    // arrive after an earlier one was lost (failed publish), so it proves nothing about gaps.
    let syncedId = 0;
    // The seq that goes with syncedId; null while unknown (rows from before seq), which makes
    // the next message catch up instead of trusting the order.
    let syncedSeq = config.latest_seq;
    let signedOut = false;

    for (const el of list.querySelectorAll('[data-id]')) {
        const id = Number(el.dataset.id);
        rendered.add(id);
        lastId = Math.max(lastId, id);
    }
    // The room's newest id when the page was rendered, which is higher than lastId on an older ?page.
    syncedId = Math.max(lastId, config.latest_id);

    function setStatus(text) {
        status.textContent = text;
    }

    function showError(text) {
        errorBox.textContent = text;
        errorBox.hidden = !text;
    }

    function markSignedOut() {
        signedOut = true;
        setStatus('signed out');
        showError('You were signed out. Reload the page to sign in again.');
        input.disabled = true;
        button.disabled = true;
    }

    function isNearBottom() {
        return list.scrollHeight - list.scrollTop - list.clientHeight < 80;
    }

    // Builds nodes with textContent only: message and user name are never parsed as HTML.
    function renderMessage(payload) {
        if (rendered.has(payload.id)) {
            return;
        }
        rendered.add(payload.id);
        const mine = payload.user.id === config.user_id;
        const stick = mine || isNearBottom();

        const item = document.createElement('div');
        item.className = mine ? 'msg msg-mine' : 'msg';
        item.dataset.id = String(payload.id);
        const meta = document.createElement('div');
        meta.className = 'msg-meta';
        const author = document.createElement('span');
        author.className = 'msg-author';
        author.textContent = payload.user.username;
        const time = document.createElement('time');
        time.dateTime = payload.created_at;
        time.textContent = new Date(payload.created_at).toISOString().slice(11, 16); // UTC, like history
        meta.append(author, time);
        const body = document.createElement('div');
        body.className = 'msg-body';
        body.textContent = payload.content;
        item.append(meta, body);

        // Keep id order even when a catch-up page and a live event interleave.
        const next = payload.id < lastId
            ? [...list.querySelectorAll('[data-id]')].find((el) => Number(el.dataset.id) > payload.id)
            : null;
        list.insertBefore(item, next || null);
        lastId = Math.max(lastId, payload.id);
        if (stick) {
            list.scrollTop = list.scrollHeight;
        }
    }

    async function fetchMissing() {
        for (;;) {
            const res = await fetch(`${config.messages_url}?after=${syncedId}`, {credentials: 'same-origin'});
            if (res.status === 401) {
                markSignedOut();
                return;
            }
            if (!res.ok) {
                return;
            }
            const {messages} = await res.json();
            messages.forEach(renderMessage);
            if (messages.length) {
                const newest = messages[messages.length - 1];
                if (newest.id > syncedId) {
                    syncedId = newest.id;
                    syncedSeq = newest.seq;
                }
            }
            if (messages.length < CATCH_UP_PAGE) {
                return;
            }
        }
    }
    const catchUp = ChatSync.createCatchUp(fetchMissing);

    // Every message from the socket or our own send passes here. One that follows the last
    // seq we hold moves the synced point with no request; a skipped seq means one was lost
    // (failed publish, dropped socket), so fetch what is missing. Duplicates are dropped by id.
    function accept(payload) {
        renderMessage(payload);
        const order = ChatSync.classify(syncedSeq, payload.seq);
        if (order === 'next') {
            syncedSeq = payload.seq;
            syncedId = Math.max(syncedId, payload.id);
        } else if (order === 'gap' && !signedOut) {
            catchUp();
        }
    }
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible' && !signedOut) {
            catchUp();
        }
    });

    function connectChannels(transport) {
        let backoff = 1;
        const url = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}${transport.path}`;
        const open = () => {
            const ws = new WebSocket(url);
            ws.onopen = () => {
                backoff = 1;
                setStatus('live');
                catchUp();
            };
            ws.onmessage = (e) => {
                const frame = JSON.parse(e.data);
                if (frame.event === 'message.new') {
                    accept(frame.payload);
                }
            };
            ws.onclose = () => {
                if (signedOut) {
                    return;
                }
                setStatus('reconnecting…');
                // A rejected socket may mean the session ended; the catch-up call finds out.
                catchUp();
                setTimeout(open, backoff * 1000);
                backoff = Math.min(backoff * 2, 30);
            };
        };
        open();
    }

    // The Columba client pattern (Columba docs, A-09): the token is fetched from our own
    // endpoint before connecting and again after any socket error, and `params` is a function
    // so every reconnect sends the latest token.
    function connectColumba(transport) {
        let token = null;
        let refreshing = null;
        const socket = new Phoenix.Socket(transport.socket_url, {params: () => ({token})});

        async function fetchToken() {
            const res = await fetch(transport.token_url, {credentials: 'same-origin'});
            if (res.status === 401) {
                markSignedOut();
                socket.disconnect(); // stop reconnecting
            }
            if (!res.ok) {
                throw new Error(`token endpoint answered ${res.status}`);
            }
            return (await res.json()).token;
        }
        const refreshToken = () =>
            (refreshing ||= fetchToken()
                .then((fresh) => { token = fresh; })
                .finally(() => { refreshing = null; }));

        // A refused connect (expired token) looks like a network drop: refresh while Phoenix retries.
        socket.onError(() => {
            if (!signedOut) {
                setStatus('reconnecting…');
            }
            refreshToken().catch(() => {});
        });
        socket.onOpen(() => setStatus('live'));

        const channel = socket.channel(`topic:${transport.topic}`);
        channel.on('event', (event) => {
            if (event.name === 'message.new') {
                accept(event.payload);
            }
        });
        // Phoenix rejoins after every reconnect; each successful join catches up.
        channel.join()
            .receive('ok', () => catchUp())
            .receive('error', (reply) => {
                if (reply && reply.reason === 'unauthorized') {
                    refreshToken().catch(() => {});
                }
            });

        // Connect even if this first fetch failed (offline, server error): onError retries it.
        refreshToken().catch(() => {}).then(() => signedOut || socket.connect());
    }

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const content = input.value;
        if (!content.trim() || signedOut) {
            return;
        }
        button.disabled = true;
        showError('');
        try {
            const res = await fetch(config.messages_url, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken},
                body: JSON.stringify({content}),
            });
            if (res.status === 201) {
                accept(await res.json()); // the broadcast copy is then a duplicate and skipped
                input.value = '';
            } else if (res.status === 401) {
                markSignedOut();
            } else if (res.status === 429) {
                showError("You're sending messages too fast. Wait a moment and try again.");
            } else if (res.status === 400) {
                const {error} = await res.json();
                showError(error === 'too_long' ? 'That message is too long (4000 characters max).' : 'Write something first.');
            } else {
                showError('Could not send the message. Try again.');
            }
        } catch {
            showError('Could not send the message. Check your connection and try again.');
        } finally {
            button.disabled = signedOut;
            input.focus();
        }
    });

    list.scrollTop = list.scrollHeight;
    setStatus('connecting…');
    if (config.transport.kind === 'columba') {
        connectColumba(config.transport);
    } else {
        connectChannels(config.transport);
    }
})();
