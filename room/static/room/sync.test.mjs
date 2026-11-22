// Run with: node --test 'room/static/room/*.test.mjs'
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {test} from 'node:test';

const {classify, createCatchUp} = createRequire(import.meta.url)('./sync.js');

function deferred() {
    let resolve;
    let reject;
    const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
    return {promise, resolve, reject};
}

test('next seq is in order', () => {
    assert.equal(classify(4, 5), 'next');
    assert.equal(classify(0, 1), 'next'); // empty room
});

test('skipped seq is a gap', () => {
    assert.equal(classify(4, 7), 'gap');
});

test('seen or older seq is old', () => {
    assert.equal(classify(4, 4), 'old');
    assert.equal(classify(4, 2), 'old');
});

test('late duplicate is ignored', () => {
    assert.equal(classify(6, 5), 'old');
});

test('unknown seq triggers catch-up', () => {
    assert.equal(classify(null, 5), 'gap');
    assert.equal(classify(4, null), 'gap');
    assert.equal(classify(undefined, 5), 'gap');
    assert.equal(classify(4, undefined), 'gap');
});

test('catch-up requested while running runs once more', async () => {
    const runs = [];
    const catchUp = createCatchUp(() => {
        const d = deferred();
        runs.push(d);
        return d.promise;
    });

    const first = catchUp();
    const second = catchUp();
    const third = catchUp();
    const fourth = catchUp();
    assert.equal(runs.length, 1);

    runs[0].resolve();
    await first;
    await Promise.resolve();
    assert.equal(runs.length, 2);

    runs[1].resolve();
    await Promise.all([second, third, fourth]);
    assert.equal(runs.length, 2);
});

test('idle calls run once each', async () => {
    let count = 0;
    const catchUp = createCatchUp(async () => { count += 1; });

    await catchUp();
    await catchUp();

    assert.equal(count, 2);
});

test('a rejected run is swallowed and the next call still runs', async () => {
    let count = 0;
    const catchUp = createCatchUp(async () => {
        count += 1;
        if (count === 1) {
            throw new Error('offline');
        }
    });

    await catchUp();
    await catchUp();

    assert.equal(count, 2);
});

test('runs never overlap when a caller re-requests from its continuation', async () => {
    let active = 0;
    let maxActive = 0;
    const runs = [];
    const catchUp = createCatchUp(() => {
        active += 1;
        maxActive = Math.max(maxActive, active);
        const d = deferred();
        runs.push(d);
        return d.promise.finally(() => { active -= 1; });
    });

    const first = catchUp();
    // This continuation is registered before the queued run's, so it runs first.
    const again = first.then(() => catchUp());
    catchUp(); // queues a run behind the first

    runs[0].resolve();
    await first;
    for (let i = 0; i < 5; i += 1) {
        await Promise.resolve();
    }
    runs.forEach((d) => d.resolve());
    await again;
    for (let i = 0; i < 5; i += 1) {
        await Promise.resolve();
    }
    runs.forEach((d) => d.resolve());

    assert.equal(maxActive, 1);
});
