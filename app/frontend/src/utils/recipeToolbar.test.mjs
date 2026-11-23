import test from 'node:test';
import assert from 'node:assert/strict';
import { recipeReadingViews, readingViewSelection } from './recipeToolbar.mjs';
import { recipeViewAvailability } from './viewerResume.mjs';

test('reading choices reflect actual sources without duplicate Original', () => {
  assert.deepEqual(recipeReadingViews({ file_type: 'pdf' }, false), ['pdf']);
  assert.deepEqual(recipeReadingViews({ images: ['page.jpg'] }, false), ['images']);
  assert.deepEqual(recipeReadingViews({ has_pdf: true, has_images: true }, true), ['pdf', 'images', 'text']);
  assert.deepEqual(recipeReadingViews({}, false), ['original']);
});
test('saved text remains selectable without enabling AI review', () => {
  for (const [ai, saved, expected] of [[false,false,false], [false,true,true], [true,false,true], [true,true,true]]) {
    const available = recipeViewAvailability('original', ai, saved);
    assert.equal(recipeReadingViews({ file_type: 'pdf' }, available.showText).includes('text'), expected);
  }
});
test('flat choices preserve the existing persistence contract', () => {
  assert.deepEqual(readingViewSelection('text'), { viewMode: 'text' });
  assert.deepEqual(readingViewSelection('pdf'), { viewMode: 'original', sourceMode: 'pdf' });
  assert.deepEqual(readingViewSelection('images'), { viewMode: 'original', sourceMode: 'images' });
});
