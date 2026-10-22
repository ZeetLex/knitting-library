import test from 'node:test';
import assert from 'node:assert/strict';
import { safeReaderUrl, readerHeadings, preserveInstructionNumbers, formatSelection } from './readerPolicy.mjs';

test('reader blocks external images, executable links and raw credential targets', () => {
  assert.equal(safeReaderUrl('https://external.test/track.png', true), '');
  assert.equal(safeReaderUrl('/api/admin/ai/chatgpt', true), '');
  assert.equal(safeReaderUrl('javascript:alert(1)'), '');
  assert.equal(safeReaderUrl('data:text/html,hello'), '');
  assert.equal(safeReaderUrl('java\nscript:alert(1)'), '');
  assert.equal(safeReaderUrl('/api/recipes/recipe/review-assets/chart.png', true), '/api/recipes/recipe/review-assets/chart.png');
  assert.equal(safeReaderUrl('#row-12'), '#row-12');
  assert.equal(safeReaderUrl('https://example.test/pattern'), 'https://example.test/pattern');
});

test('contents excludes fenced instructions and retains source line anchors', () => {
  assert.deepEqual(readerHeadings('# Body\n\n```\n# not a heading\n```\n## Sleeves'), [
    {line:1,depth:1,label:'Body'}, {line:6,depth:2,label:'Sleeves'},
  ]);
});

test('nonconsecutive instruction numbers are retained instead of renumbered', () => {
  const source='1. Knit\n3. Purl\n7. Bind off';
  const tree={type:'root',children:[{type:'list',ordered:true,children:[
    {type:'listItem',position:{start:{offset:0},end:{offset:7}}},
    {type:'listItem',position:{start:{offset:8},end:{offset:15}}},
    {type:'listItem',position:{start:{offset:16},end:{offset:27}}},
  ]}]};
  preserveInstructionNumbers()(tree,{value:source});
  assert.deepEqual(tree.children[0].children.map(item => item.data.hProperties.value),[1,3,7]);
});

test('formatting preserves size sequences, abbreviations and repeat markers', () => {
  const text='k2tog, *k1, p1*; 84 (92) 100 cm; A_1';
  assert.equal(formatSelection(text,0,text.length,'heading'),'## '+text);
  assert.equal(formatSelection(text,0,5,'bold'),'**k2tog**, *k1, p1*; 84 (92) 100 cm; A_1');
});
