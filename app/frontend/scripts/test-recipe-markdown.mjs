// Exercise the actual JSX renderer without browser state or app providers.
import assert from 'node:assert/strict';
import { build } from 'esbuild';
const bundle = await build({
  stdin: { contents: `import React from 'react'; import {renderToStaticMarkup} from 'react-dom/server';
    import {RecipeMarkdown} from './src/components/RecipeReader.jsx';
    export function render(content) {return renderToStaticMarkup(React.createElement(RecipeMarkdown,{content}));}`,
    resolveDir: process.cwd(), loader: 'jsx' },
  bundle: true, platform: 'node', format: 'esm', write: false,
  banner: {js: `import {createRequire as createTestRequire} from 'node:module'; const require=createTestRequire(${JSON.stringify(import.meta.url)});`},
  plugins: [{name:'test-context',setup(builder) {
    builder.onResolve({filter:/AppContext$/}, () => ({path:'context',namespace:'test'}));
    builder.onLoad({filter:/.*/,namespace:'test'}, () => ({contents:'export function useApp() {return {t:key=>key};}'}));
  }}], loader:{'.css':'empty'},
});
let render;
try { ({render} = await import('data:text/javascript;base64,'+Buffer.from(bundle.outputFiles[0].text).toString('base64'))); }
catch (error) { console.error(error.message); process.exit(1); }
const html = render('# Body\n\n1. Knit\n3. Purl\n7. Bind off\n\n\\*k1, p1\\*; A\\_1; 84 (92) 100 cm\n\n| Size | XS | S |\n| --- | --- | --- |\n| Sts | 84 | 92 |\n\n**k2tog**\n\n![Chart](/api/recipes/test/review-assets/chart.png)\n\n![Bad](https://external.test/track.png)\n\n<script>alert(1)</script>\n\n[Bad link](javascript:alert)');
assert.match(html,/<li value="3">/);
assert.match(html,/<li value="7">/);
assert.match(html,/\*k1, p1\*/);
assert.match(html,/A_1/);
assert.match(html,/84 \(92\) 100 cm/);
assert.match(html,/<table>/);
assert.match(html,/<strong>k2tog<\/strong>/);
assert.match(html,/src="\/api\/recipes\/test\/review-assets\/chart.png"/);
assert.doesNotMatch(html,/<script|src="https:\/\/external|href="javascript:/);
console.log('PASS: actual recipe renderer preserves symbols, explicit numbers, tables, diagrams and safe content.');
