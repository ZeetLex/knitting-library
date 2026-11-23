// Run after npm ci and npx playwright install chromium.
const { chromium } = require('playwright');
const { spawn } = require('node:child_process');
const path = require('node:path');
const frontend = path.resolve(__dirname, '..');
const server = spawn(process.execPath, [path.join(frontend, 'node_modules/vite/bin/vite.js'), '--host', '127.0.0.1', '--port', '5179', '--strictPort'], { cwd: frontend, stdio: 'ignore', windowsHide: true });
let browser;
process.on('exit', () => server.kill());
const assert = require('node:assert/strict');
(async () => {
 const deadline=Date.now()+20000;
 while(true) { try { const response=await fetch('http://127.0.0.1:5179'); if(response.ok) break; } catch {} if(Date.now()>deadline) throw Error('Vite did not start'); await new Promise(resolve=>setTimeout(resolve,200)); }
 browser=await chromium.launch({headless:true});
 let fixtureLanguage='no', fixtureTheme='light', fixtureText=true, fixtureAI=false, fixtureSource='both';
 const page=await browser.newPage({viewport:{width:390,height:844}});
 const errors=[]; page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/src/App.jsx*',async route=>{ const original=await (await route.fetch()).text(); const contextPath=original.match(/from "([^"]*AppContext[^"]*)"/)[1]; return route.fulfill({contentType:'application/javascript',body:
   "import React from '/node_modules/.vite/deps/react.js'; import {AppProvider} from 'CONTEXT_PATH'; import RecipeViewer from '/src/pages/RecipeViewer.jsx'; import '/src/components/AppShell.css'; export default function App(){return React.createElement(AppProvider,null,React.createElement('div',{className:'app-shell app-shell--recipe'},React.createElement('main',{className:'app-content'},React.createElement(RecipeViewer,{recipeId:'qa',onBack:()=>{}}))));}".replace("CONTEXT_PATH",contextPath)});});
 await page.route('**/api/**', async route=>{
  const p=new URL(route.request().url()).pathname;
  if (/pdf-pages\/|images\//.test(p)) return route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="600" height="900"><rect width="600" height="900" fill="#faf5ed"/><text x="30" y="80" font-size="28">Knitting pattern test page</text></svg>'});
  let data={};
  if(p==='/api/recipes/qa') data={id:'qa',title:'QA recipe',file_type:fixtureSource==='pdf'?'pdf':'images',has_pdf:fixtureSource!=='images',has_images:fixtureSource!=='pdf',images:fixtureSource==='pdf'?[]:['one.jpg','two.jpg'],tags:[],categories:[],project_status:'not_started',sessions:[]};
  else if(p.endsWith('/pdf-pages')) data={pages:['one.jpg','two.jpg','three.jpg']};
  else if(p.endsWith('/annotations')) data=[];
  else if(p.includes('/annotations/')) data=[];
  else if(p.endsWith('/text-version')) data={exists:fixtureText,ai_enabled:fixtureAI,format_version:'gfm-v1',content_markdown:('# Pattern\n\nKnit every row.\n\n').repeat(80)};
  else if(p==='/api/auth/me') data={id:1,username:'QA',language:fixtureLanguage,theme:fixtureTheme};
  else if(p.includes('work-queue')) data={jobs:[]};
  return route.fulfill({json:data});
 });
 await page.goto('http://127.0.0.1:5179');
 await page.locator('.pdf-page-block canvas').first().waitFor().catch(async e=>{console.log('errors',errors);console.log(await page.locator('body').innerText());throw e;});
 await page.waitForTimeout(800);
 console.log('errors',errors);
 await page.evaluate(()=>{document.documentElement.style.setProperty('--safe-top','59px');document.documentElement.style.setProperty('--safe-bottom','34px');});
 for (const width of [320,375,390,430,768,844,899,900]) {
  await page.setViewportSize({width,height:width>768?430:844}); await page.waitForTimeout(150);
  const geometry=await page.evaluate(()=>{const v=document.querySelector('.viewer'),r=document.querySelector('.pdf-pages-wrap');return {width:innerWidth,documentWidth:document.documentElement.scrollWidth,viewer:v.getBoundingClientRect().toJSON(),reader:r.getBoundingClientRect().toJSON()};});
  assert(geometry.documentWidth<=width,'horizontal overflow '+width);
  assert(geometry.reader.y>=59,'top safe area '+width);
  assert(geometry.reader.bottom<= (width>768?430:844),'bottom clipping '+width);
  console.log('geometry',JSON.stringify(geometry));
 }
 await page.setViewportSize({width:390,height:844});
 await page.locator('.pdf-pages-wrap').evaluate(el=>{el.dispatchEvent(new WheelEvent('wheel'));el.scrollTop=400;});
 await page.locator('.recipe-reading-compact').waitFor({state:'visible'});
 assert.equal(await page.locator('.recipe-reading-compact button[aria-pressed]').count(),3);
 const before=await page.locator('.pdf-pages-wrap').evaluate(el=>el.scrollTop);
 await page.waitForTimeout(150);
 assert.equal(await page.locator('.pdf-pages-wrap').evaluate(el=>el.scrollTop),before);
 if(process.env.QA_SCREENSHOT) await page.screenshot({path:process.env.QA_SCREENSHOT,fullPage:true});
 await page.locator('.recipe-reading-compact button[aria-pressed]').last().click();
 await page.locator('.text-version-panel').waitFor();
 await page.locator('.text-version-panel').evaluate(el=>{el.dispatchEvent(new WheelEvent('wheel'));el.scrollTop=400;});
 await page.locator('.recipe-reading-compact').waitFor({state:'visible'});
 await page.locator('.recipe-reading-compact button[aria-pressed]').first().click();
 await page.locator('.pdf-pages-wrap').waitFor();
 await page.locator('.pdf-pages-wrap').evaluate(el=>el.scrollTop=0);
 await page.locator('.recipe-reading-compact').waitFor({state:'detached'});
 await page.locator('.recipe-reading-expanded button[aria-pressed]').nth(1).click();
 await page.locator('.image-viewer-main').waitFor();
 assert.equal(await page.locator('.recipe-reading-compact').count(),0);
 await page.locator('.recipe-reading-fullscreen').click();
 await page.locator('.image-viewer.fullscreen').waitFor();
 await page.locator('.fullscreen-exit-btn').click();

 for (const language of ['no','en','de','fr','es','hu']) {
  for (const theme of ['light','dark']) {
   fixtureLanguage=language; fixtureTheme=theme;
   await page.reload(); await page.locator('.pdf-page-block canvas').first().waitFor();
   await page.waitForTimeout(800);
   console.log('checking', language, theme);
   await page.evaluate(()=>{const style=document.documentElement.style;style.setProperty('--safe-top','59px');style.setProperty('--safe-left','20px');style.setProperty('--safe-right','20px');});
   await page.setViewportSize({width:320,height:844});
   await page.locator('.pdf-pages-wrap').evaluate(el=>{el.dispatchEvent(new WheelEvent('wheel'));el.scrollTop=400;});
   await page.locator('.recipe-reading-compact').waitFor({state:'visible'});
   const bounds=await page.locator('.recipe-reading-compact .recipe-reading-controls').evaluate(el=>({width:el.getBoundingClientRect().width,overflow:el.scrollWidth>el.clientWidth,text:el.textContent}));
   assert(!bounds.overflow && bounds.width<=260, 'compact overflow '+language+' '+theme);
   assert(!bounds.text.includes('readingTextView'), 'missing translation');
   await page.locator('.pdf-pages-wrap').evaluate(el=>el.scrollTop=0);
   await page.locator('.recipe-reading-compact').waitFor({state:'detached'});
   assert(await page.locator('.recipe-reading-expanded .recipe-reading-controls').evaluate(el=>el.scrollWidth<=el.clientWidth), 'expanded overflow '+language);
  }
 }
 for (const [source,saved,ai,count] of [['pdf',false,false,0],['images',false,false,0],['both',false,false,2],['pdf',true,false,2],['pdf',false,true,2]]) {
  fixtureSource=source; fixtureText=saved; fixtureAI=ai;
  await page.reload(); await page.locator('.recipe-reading-expanded').waitFor({state:'visible'});
  assert.equal(await page.locator('.recipe-reading-expanded button[aria-pressed]').count(),count,'availability '+[source,saved,ai]);
 }
 assert.deepEqual(errors,[]);
 console.log('PASS responsive geometry, PDF/Text compact transitions, direct switching, Images and fullscreen');
 await browser.close();
})().catch(async e=>{console.error(e); await browser?.close(); process.exitCode=1;}).finally(()=>server.kill());
