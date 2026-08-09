import test from 'node:test';
import assert from 'node:assert/strict';

import { createLatestPayloadThrottle, mergeLocalViewerPresentation, normalizeViewerResume, pdfPagesReadyForAnchor, pdfScrollTopForAnchor, resolveRecipeSourceMode, resolveViewerResume } from './viewerResume.mjs';

test('prefers PDF when both formats exist and no source preference is saved', () => {
  const recipe = { has_pdf: true, has_images: true, preferred_source: 'pdf' };
  assert.equal(resolveRecipeSourceMode('', recipe), 'pdf');
});

test('PDF availability always wins over a saved image preference on open', () => {
  const recipe = { has_pdf: true, has_images: true, preferred_source: 'pdf' };
  assert.equal(resolveRecipeSourceMode('images', recipe), 'pdf');
});

test('falls back to images when a saved PDF no longer exists', () => {
  const recipe = { has_pdf: false, has_images: true, preferred_source: 'images' };
  assert.equal(resolveRecipeSourceMode('pdf', recipe), 'images');
});

test('restores a saved image source when there is no PDF at all', () => {
  const recipe = { has_pdf: false, has_images: true };
  assert.equal(resolveRecipeSourceMode('images', recipe), 'images');
});

test('normalizes PDF scroll and source mode safely', () => {
  const resume = normalizeViewerResume({
    sourceMode: 'pdf', pdfScrollY: 1234, fullscreen: true,
    pdfAnchor: { pageIndex: 3, offsetRatio: 0.25 }, revision: 42,
  }, 'original');
  assert.equal(resume.sourceMode, 'pdf');
  assert.equal(resume.pdfScrollY, 1234);
  assert.equal(resume.fullscreen, true);
  assert.deepEqual(resume.pdfAnchor, { pageIndex: 3, offsetRatio: 0.25 });
  assert.equal(resume.revision, 42);

  const invalid = normalizeViewerResume({ sourceMode: 'other', pdfScrollY: -20, pdfAnchor: { pageIndex: -1, offsetRatio: 'bad' } }, 'original');
  assert.equal(invalid.sourceMode, '');
  assert.equal(invalid.pdfScrollY, 0);
  assert.equal(invalid.fullscreen, false);
  assert.equal(invalid.pdfAnchor, null);
  assert.equal(invalid.revision, 0);
});

test('calculates a centered PDF scroll target after page resizing', () => {
  const target = pdfScrollTopForAnchor(
    { pageIndex: 2, offsetRatio: 0.25 },
    2000,
    1200,
    800,
    5000,
  );
  assert.equal(target, 1900);
  assert.equal(pdfScrollTopForAnchor({ pageIndex: 0, offsetRatio: 0 }, 0, 1000, 800, 5000), 0);
});

test('waits for the target PDF page and every preceding page to finish resizing', () => {
  const ready = [
    { isSized: true, canvasWidth: 800, canvasHeight: 1100, wrapWidth: 800 },
    { isSized: true, canvasWidth: 799.5, canvasHeight: 1100, wrapWidth: 800 },
    { isSized: true, canvasWidth: 800, canvasHeight: 1100, wrapWidth: 800 },
  ];
  assert.equal(pdfPagesReadyForAnchor({ pageIndex: 1, offsetRatio: 0.5 }, ready), true);

  const precedingPageStillResizing = ready.map(layout => ({ ...layout }));
  precedingPageStillResizing[0].canvasWidth = 640;
  assert.equal(pdfPagesReadyForAnchor({ pageIndex: 1, offsetRatio: 0.5 }, precedingPageStillResizing), false);

  const laterPageStillResizing = ready.map(layout => ({ ...layout }));
  laterPageStillResizing[2].canvasWidth = 640;
  assert.equal(pdfPagesReadyForAnchor({ pageIndex: 1, offsetRatio: 0.5 }, laterPageStillResizing), true);
  const targetPageNotLoaded = ready.map(layout => ({ ...layout }));
  targetPageNotLoaded[1].isSized = false;
  assert.equal(pdfPagesReadyForAnchor({ pageIndex: 1, offsetRatio: 0.5 }, targetPageNotLoaded), false);
  assert.equal(pdfPagesReadyForAnchor({ pageIndex: 3, offsetRatio: 0.5 }, ready), false);
});

test('keeps fullscreen local and only reuses a PDF anchor for current progress', () => {
  const local = { fullscreen: true, pdfAnchor: { pageIndex: 4, offsetRatio: 0.5 }, revision: 42 };
  const same = mergeLocalViewerPresentation({ sourceMode: 'pdf', revision: 42 }, local);
  assert.equal(same.fullscreen, true);
  assert.deepEqual(same.pdfAnchor, local.pdfAnchor);

  const newerServer = mergeLocalViewerPresentation({ sourceMode: 'pdf', revision: 43 }, local);
  assert.equal(newerServer.fullscreen, true);
  assert.equal(newerServer.pdfAnchor, null);
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
