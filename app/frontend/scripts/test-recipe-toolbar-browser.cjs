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
 let fixtureLanguage='no', fixtureTheme='light', fixtureText=true, fixtureAI=true, fixtureSource='both';
 const page=await browser.newPage({viewport:{width:390,height:844}});
 const errors=[]; page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/src/App.jsx*',async route=>{ const original=await (await route.fetch()).text(); const contextPath=original.match(/from "([^"]*AppContext[^"]*)"/)[1]; return route.fulfill({contentType:'application/javascript',body:
   "import React from '/node_modules/.vite/deps/react.js'; import {AppProvider} from 'CONTEXT_PATH'; import RecipeViewer from '/src/pages/RecipeViewer.jsx'; import AppShell from '/src/components/AppShell.jsx'; export default function App(){const [recipe,setRecipe]=React.useState(true);return React.createElement(AppProvider,null,React.createElement(AppShell,{activeView:recipe?'recipes':'home',recipeMode:recipe,onNavigate:()=>setRecipe(false),onRecipeBack:()=>setRecipe(false)},recipe?React.createElement(RecipeViewer,{recipeId:'qa',onBack:()=>setRecipe(false)}):React.createElement('div',{className:'surface-home'},'Home')));}".replace("CONTEXT_PATH",contextPath)});});
 await page.route('**/api/**', async route=>{
  const p=new URL(route.request().url()).pathname;
  if (/pdf-pages\/|images\//.test(p)) return route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="600" height="900"><rect width="600" height="900" fill="#faf5ed"/><text x="30" y="80" font-size="28">Knitting pattern test page</text></svg>'});
  let data={};
  if(p==='/api/recipes/qa') data={id:'qa',title:'QA recipe',file_type:fixtureSource==='pdf'?'pdf':'images',has_pdf:fixtureSource!=='images',has_images:fixtureSource!=='pdf',images:fixtureSource==='pdf'?[]:['one.jpg','two.jpg'],tags:[],categories:[],project_status:'not_started',sessions:[]};
  else if(p.endsWith('/pdf-pages')) data={pages:['one.jpg','two.jpg','three.jpg']};
  else if(p.endsWith('/annotations')) data=[];
  else if(p.includes('/annotations/')) data=[];
  else if(p.endsWith('/text-version')) data={exists:fixtureText,ai_enabled:fixtureAI,is_outdated:true,format_version:'legacy',content_markdown:('# Pattern\n\nKnit every row.\n\n').repeat(80)};
  else if(p==='/api/auth/me') data={id:1,username:'QA',language:fixtureLanguage,theme:fixtureTheme};
  else if(p.includes('work-queue')) data={jobs:[]};
  return route.fulfill({json:data});
 });
 await page.goto('http://127.0.0.1:5179');
 await page.locator('.pdf-page-block canvas').first().waitFor().catch(async e=>{console.log('errors',errors);console.log(await page.locator('body').innerText());throw e;});
 await page.waitForTimeout(800);
 const assertRecipeNav = async () => {
  const result=await page.locator('.mobile-nav--recipe').evaluate(nav=>{
   const back=nav.querySelector('.mobile-nav-back'), style=getComputedStyle(back), bounds=nav.getBoundingClientRect();
   const luminance=color=>color.match(/[\d.]+/g).slice(0,3).map(Number).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;}).reduce((sum,v,i)=>sum+v*[.2126,.7152,.0722][i],0);
   const a=luminance(style.color), b=luminance(style.backgroundColor);
   return {contrast:(Math.max(a,b)+.05)/(Math.min(a,b)+.05),label:back.textContent,buttons:[...nav.querySelectorAll('.mobile-nav-item-main,.mobile-nav-recipe-split-btn')].map(el=>{const r=el.getBoundingClientRect();return {width:r.width,height:r.height,left:r.left,right:r.right,top:r.top};}),left:bounds.left,right:bounds.right};
  });
  assert(result.contrast>=4.5,'Back contrast '+result.contrast);
  assert(result.label.trim(),'Back has a visible label');
  assert.equal(result.buttons.length,5,'five balanced reader actions');
  for(const [i,button] of result.buttons.entries()) {
   assert(button.width>=44 && button.height>=44,'touch target '+JSON.stringify(button));
   assert(button.left>=result.left && button.right<=result.right,'action stays inside bar');
   if(i) assert(button.left>=result.buttons[i-1].right && Math.abs(button.top-result.buttons[0].top)<1,'actions form one aligned row');
  }
 };
 const assertSurface = async (type, selector) => {
  await page.waitForFunction(()=>document.querySelector('meta[name="theme-color"]').content===getComputedStyle(document.documentElement).backgroundColor);
  const surface=await page.evaluate(selector=>{
   const style=el=>getComputedStyle(el);
   const root=style(document.documentElement), body=style(document.body), shell=style(document.querySelector('.app-shell'));
   return {type:document.documentElement.dataset.recipeSurface,root:root.backgroundColor,body:body.backgroundColor,shell:shell.backgroundColor,reader:style(document.querySelector(selector)).backgroundColor,wallpaper:body.backgroundImage,backdrop:getComputedStyle(document.querySelector('.app-shell'),'::before').backgroundImage};
  },selector);
  assert.equal(surface.type,type);
  assert.equal(surface.root,surface.body,'safe areas match the page canvas');
  assert.equal(surface.root,surface.shell,'navigation space matches the page canvas');
  assert.equal(surface.root,surface.reader,'reader matches the surrounding canvas');
  assert.equal(surface.wallpaper,'none','wallpaper hidden while reading');
  assert.equal(surface.backdrop,'none','fixed shell backdrop has no wallpaper');
  await assertRecipeNav();
 };
 await assertSurface('document','.pdf-pages-wrap');
 console.log('errors',errors);
 await page.evaluate(()=>{document.documentElement.style.setProperty('--safe-top','59px');document.documentElement.style.setProperty('--safe-bottom','34px');});
 for (const width of [320,375,390,430,768,844,899,900]) {
  await page.setViewportSize({width,height:width>768?430:844}); await page.waitForTimeout(150);
  const geometry=await page.evaluate(()=>{const v=document.querySelector('.viewer'),r=document.querySelector('.pdf-pages-wrap');return {width:innerWidth,documentWidth:document.documentElement.scrollWidth,viewer:v.getBoundingClientRect().toJSON(),reader:r.getBoundingClientRect().toJSON()};});
  assert(geometry.documentWidth<=width,'horizontal overflow '+width);
  assert(geometry.reader.y>=59,'top safe area '+width);
  assert(geometry.reader.bottom<= (width>768?430:844),'bottom clipping '+width);
  if(width<900) await assertRecipeNav();
  console.log('geometry',JSON.stringify(geometry));
 }
 await page.setViewportSize({width:390,height:844});
 assert.equal(await page.locator('.mobile-nav-back').innerText(),'Tilbake');
 await page.locator('.mobile-nav--recipe .mobile-nav-collapse').click();
 await page.locator('.mobile-nav-peek').waitFor();
 await page.locator('.mobile-nav-peek').click();
 await page.locator('.mobile-nav-back').waitFor();
 await page.locator('.mobile-nav--recipe .mobile-nav-item-main').last().click();
 await page.locator('.mobile-panel--actions.mobile-panel--open').waitFor();
 await page.locator('.mobile-panel--actions .mobile-panel-handle').click();
 await page.locator('.mobile-panel--actions.mobile-panel--open').waitFor({state:'detached'});
 await page.locator('.pdf-pages-wrap').evaluate(el=>{el.dispatchEvent(new WheelEvent('wheel'));el.scrollTop=400;});
 await page.locator('.recipe-reading-compact').waitFor({state:'visible'});
 assert.equal(await page.locator('.recipe-reading-compact button[aria-pressed]').count(),3);
 const before=await page.locator('.pdf-pages-wrap').evaluate(el=>el.scrollTop);
 await page.waitForTimeout(150);
 assert.equal(await page.locator('.pdf-pages-wrap').evaluate(el=>el.scrollTop),before);
 if(process.env.QA_SCREENSHOT) await page.screenshot({path:process.env.QA_SCREENSHOT,fullPage:true});
 await page.locator('.recipe-reading-compact button[aria-pressed]').last().click();
 await page.locator('.text-version-panel').waitFor();
 await page.locator('.recipe-markdown h1').first().waitFor();
 await assertSurface('text','.text-version-panel');
 assert.equal(await page.locator('.recipe-reader-settings:visible').count(),0,'settings hidden by default');
 assert.equal(await page.locator('.recipe-reader-document:visible').count(),0,'document actions hidden by default');
 assert(await page.locator('.recipe-reader-bar').evaluate(el=>el.getBoundingClientRect().height<=56),'compact reader bar');
 await page.locator('[data-reader-panel="appearance"]').click();
 for (let i=0;i<4;i++) await page.locator('.recipe-reader-settings input').press('ArrowRight');
 assert.equal(await page.locator('.recipe-markdown').evaluate(el=>getComputedStyle(el).fontSize),'22px');
 await page.locator('.recipe-reader-settings select').selectOption('2');
 assert.equal(await page.locator('.recipe-markdown').evaluate(el=>getComputedStyle(el).lineHeight),'44px');
 await page.locator('.recipe-reader-settings button').click();
 await page.locator('.recipe-reader .markdown-view').waitFor();
 await page.locator('.recipe-reader-settings button').click();
 await page.locator('.recipe-markdown h1').first().waitFor();
 await page.keyboard.press('Escape');
 assert.equal(await page.locator('[data-reader-panel="appearance"]').getAttribute('aria-expanded'),'false');
 await page.locator('[data-reader-panel="contents"]').click();
 await page.locator('.recipe-reader-contents a').first().waitFor();
 await page.locator('[data-reader-panel="document"]').click();
 assert.equal(await page.locator('.recipe-reader-contents:visible').count(),0,'only one disclosure opens');
 await page.locator('.recipe-reader-document .text-version-warning').waitFor();
 await page.locator('.recipe-reader-document-actions button').first().click();
 await page.locator('.text-version-editor').waitFor();
 await page.locator('.text-version-actions button').filter({hasText:'Avbryt'}).click();
 await page.locator('.recipe-reader-bar').waitFor();
 await page.locator('.recipe-reader-tools button[aria-pressed]').click();
 await page.locator('.recipe-reader--focus').waitFor();
 await page.keyboard.press('Shift+Tab');
 assert(await page.evaluate(()=>document.activeElement.closest('.recipe-reader--focus') && document.activeElement.getClientRects().length>0),'focus stays on visible reader controls');
 await page.keyboard.press('Escape');
 await page.locator('.recipe-reader--focus').waitFor({state:'detached'});
 if(process.env.QA_READER_SCREENSHOT) await page.screenshot({path:process.env.QA_READER_SCREENSHOT,fullPage:true});
 await page.locator('.text-version-panel').evaluate(el=>{el.dispatchEvent(new WheelEvent('wheel'));el.scrollTop=400;});
 await page.locator('.recipe-reading-compact').waitFor({state:'visible'});
 await page.locator('.recipe-reading-compact button[aria-pressed]').first().click();
 await page.locator('.pdf-pages-wrap').waitFor();
 await page.locator('.pdf-pages-wrap').evaluate(el=>{el.dispatchEvent(new WheelEvent('wheel'));el.scrollTop=0;});
 await page.locator('.recipe-reading-compact').waitFor({state:'detached'});
 await page.locator('.recipe-reading-expanded button[aria-pressed]').nth(1).click();
 await page.locator('.image-viewer-main').waitFor();
 await assertSurface('document','.image-viewer-main');
 assert.equal(await page.locator('.recipe-reading-compact').count(),0);
 await page.locator('.recipe-reading-fullscreen').click();
 await page.locator('.image-viewer.fullscreen').waitFor();
 await page.locator('.fullscreen-exit-btn').click();

 for (const language of ['no','en','de','fr','es','hu']) {
  for (const theme of ['light','dark']) {
   fixtureLanguage=language; fixtureTheme=theme;
   await page.reload(); await page.locator('.pdf-page-block canvas').first().waitFor();
   await page.waitForTimeout(800);
   await assertSurface('document','.pdf-pages-wrap');
   console.log('checking', language, theme);
   await page.evaluate(()=>{const style=document.documentElement.style;style.setProperty('--safe-top','59px');style.setProperty('--safe-left','20px');style.setProperty('--safe-right','20px');});
   await page.setViewportSize({width:320,height:844});
   await page.locator('.pdf-pages-wrap').evaluate(el=>{el.dispatchEvent(new WheelEvent('wheel'));el.scrollTop=400;});
   await page.locator('.recipe-reading-compact').waitFor({state:'visible'});
   const bounds=await page.locator('.recipe-reading-compact .recipe-reading-controls').evaluate(el=>({width:el.getBoundingClientRect().width,overflow:el.scrollWidth>el.clientWidth,text:el.textContent}));
   assert(!bounds.overflow && bounds.width<=260, 'compact overflow '+language+' '+theme);
   assert(!bounds.text.includes('readingTextView'), 'missing translation');
   await page.locator('.recipe-reading-compact button[aria-pressed]').last().click();
   await page.locator('.recipe-reader-bar').waitFor();
   await assertSurface('text','.text-version-panel');
   assert(await page.locator('.recipe-reader-bar').evaluate(el=>el.scrollWidth<=el.clientWidth),'reader toolbar overflow '+language+' '+theme);
   await page.locator('[data-reader-panel="appearance"]').click();
   assert(await page.locator('.recipe-reader-settings').evaluate(el=>el.scrollWidth<=el.clientWidth),'reader settings overflow '+language+' '+theme);
   await page.locator('[data-reader-panel="appearance"]').click();
   await page.locator('.recipe-reading-expanded button[aria-pressed]').first().click();
   await page.locator('.pdf-pages-wrap').waitFor();
   await page.locator('.pdf-pages-wrap').evaluate(el=>{el.dispatchEvent(new WheelEvent('wheel'));el.scrollTop=0;});
   await page.locator('.recipe-reading-compact').waitFor({state:'detached'});
   assert(await page.locator('.recipe-reading-expanded .recipe-reading-controls').evaluate(el=>el.scrollWidth<=el.clientWidth), 'expanded overflow '+language);
  }
 }
 await page.locator('.recipe-reading-expanded button[aria-pressed]').last().click();
 for (const width of [768,1024,1440]) {
  await page.setViewportSize({width,height:900});
  await page.locator('.recipe-reader-bar').waitFor();
  assert(await page.locator('.recipe-reader-bar').evaluate(el=>el.scrollWidth<=el.clientWidth),'wide reader toolbar '+width);
 }
 await page.locator('.viewer-mode-tab').first().click();
 await page.setViewportSize({width:390,height:844});
 for (const [source,saved,ai,count] of [['pdf',false,false,0],['images',false,false,0],['both',false,false,2],['pdf',true,false,2],['pdf',false,true,2]]) {
  fixtureSource=source; fixtureText=saved; fixtureAI=ai;
  await page.reload(); await page.locator('.recipe-reading-expanded').waitFor({state:'visible'});
  await page.waitForFunction(expected=>document.querySelectorAll('.recipe-reading-expanded button[aria-pressed]').length===expected,count);
  assert.equal(await page.locator('.recipe-reading-expanded button[aria-pressed]').count(),count,'availability '+[source,saved,ai]);
 }
 assert.deepEqual(errors,[]);
 await page.locator('.mobile-nav-back').click();
 await page.locator('.surface-home').waitFor();
 assert(await page.evaluate(()=>!document.documentElement.hasAttribute('data-recipe-surface') && getComputedStyle(document.body).backgroundImage!=='none'),'wallpaper restored after leaving the recipe');
 assert.equal(await page.locator('meta[name="theme-color"]').getAttribute('content'),'#1a1a2e','browser tint restored');
 console.log('PASS balanced reader navigation, Back contrast and navigation, 44px targets, collapse/actions, continuous PDF/Images/Text surfaces, wallpaper restoration, all locales/themes and fullscreen');
 await browser.close();
})().catch(async e=>{console.error(e); await browser?.close(); process.exitCode=1;}).finally(()=>server.kill());
