import test from 'node:test';
import assert from 'node:assert/strict';

import { createLatestPayloadThrottle, normalizeViewerResume, resolveRecipeSourceMode, resolveViewerResume } from './viewerResume.mjs';

test('prefers PDF when both formats exist and no source preference is saved', () => {
  const recipe = { has_pdf: true, has_images: true, preferred_source: 'pdf' };
  assert.equal(resolveRecipeSourceMode('', recipe), 'pdf');
});

test('restores an available saved image source for the current user', () => {
  const recipe = { has_pdf: true, has_images: true, preferred_source: 'pdf' };
  assert.equal(resolveRecipeSourceMode('images', recipe), 'images');
});

test('falls back to images when a saved PDF no longer exists', () => {
  const recipe = { has_pdf: false, has_images: true, preferred_source: 'images' };
  assert.equal(resolveRecipeSourceMode('pdf', recipe), 'images');
});

test('normalizes PDF scroll and source mode safely', () => {
  const resume = normalizeViewerResume({ sourceMode: 'pdf', pdfScrollY: 1234, revision: 42 }, 'original');
  assert.equal(resume.sourceMode, 'pdf');
  assert.equal(resume.pdfScrollY, 1234);
  assert.equal(resume.revision, 42);

  const invalid = normalizeViewerResume({ sourceMode: 'other', pdfScrollY: -20 }, 'original');
  assert.equal(invalid.sourceMode, '');
  assert.equal(invalid.pdfScrollY, 0);
  assert.equal(invalid.revision, 0);
});

test('throttled viewer progress sends the latest queued payload', () => {
  let now = 2000;
  let timer = null;
  const sent = [];
  const throttle = createLatestPayloadThrottle(
    payload => sent.push(payload),
    1500,
    {
      now: () => now,
      setTimer: callback => { timer = callback; return 1; },
      clearTimer: () => { timer = null; },
    },
  );

  throttle.queue({ revision: 1 });
  now = 2100;
  throttle.queue({ revision: 2 });
  now = 2200;
  throttle.queue({ revision: 3 });
  assert.deepEqual(sent, [{ revision: 1 }]);

  now = 3500;
  timer();
  assert.deepEqual(sent, [{ revision: 1 }, { revision: 3 }]);
});

test('newer local progress wins over stale server progress by revision', () => {
  const local = { sourceMode: 'images', imageIndex: 7, revision: 42 };
  const server = { exists: true, sourceMode: 'pdf', imageIndex: 1, revision: 41 };
  assert.equal(resolveViewerResume(local, server).sourceMode, 'images');
  assert.equal(resolveViewerResume(local, server).imageIndex, 7);
});

test('server progress wins ties and newer revisions', () => {
  const local = { sourceMode: 'images', revision: 42 };
  assert.equal(resolveViewerResume(local, { exists: true, sourceMode: 'pdf', revision: 42 }).sourceMode, 'pdf');
  assert.equal(resolveViewerResume(local, { exists: true, sourceMode: 'pdf', revision: 43 }).sourceMode, 'pdf');
});
