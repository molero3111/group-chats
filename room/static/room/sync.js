// Gap detection for the room page, kept free of the DOM so node can test it
// (node --test 'room/static/room/*.test.mjs'). The browser gets it as window.ChatSync.
(function (root) {
    'use strict';

    // Where a message's per-room seq stands against the highest seq held with no gaps before it:
    // 'next' extends that run, 'old' was already covered, and 'gap' means something may be
    // missing. An unknown seq on either side (rows from before seq existed) counts as a gap.
    function classify(syncedSeq, seq) {
        if (typeof syncedSeq !== 'number' || typeof seq !== 'number') {
            return 'gap';
        }
        if (seq === syncedSeq + 1) {
            return 'next';
        }
        return seq <= syncedSeq ? 'old' : 'gap';
    }

    // Runs `run` one at a time. A call while a run is in flight queues exactly one more run
    // after it, however many calls arrive, because the in-flight request may have been sent
    // before the gap that prompted the call existed. Errors are swallowed: the next trigger retries.
    function createCatchUp(run) {
        let current = null;
        let queued = null;
        const start = () => {
            current = (async () => run())()
                .catch(() => {})
                .finally(() => { current = null; });
            return current;
        };
        return function catchUp() {
            if (!current) {
                return start();
            }
            queued ||= current.then(() => {
                queued = null;
                return start();
            });
            return queued;
        };
    }

    const api = {classify, createCatchUp};
    if (typeof module === 'object' && module.exports) {
        module.exports = api;
    } else {
        root.ChatSync = api;
    }
})(typeof window === 'undefined' ? globalThis : window);
