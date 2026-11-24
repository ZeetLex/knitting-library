// Real AppShell controls with lightweight page fixtures; no household data.
const { chromium } = require('playwright');
const { spawn } = require('node:child_process');
const path = require('node:path');
const assert = require('node:assert/strict');
const frontend = path.resolve(__dirname, '..');
const url = 'http://127.0.0.1:5183';
const server = spawn(process.execPath, [path.join(frontend, 'node_modules/vite/bin/vite.js'), '--host', '127.0.0.1', '--port', '5183', '--strictPort'], { cwd: frontend, stdio: 'ignore', windowsHide: true });
process.on('exit', () => server.kill());
let browser;
(async () => {
  const deadline = Date.now() + 20000;
  while (true) {
    try { if ((await fetch(url)).ok) break; } catch {}
    if (Date.now() > deadline) throw Error('Vite did not start');
    await new Promise(resolve => setTimeout(resolve, 200));
  }
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  let language = 'en', theme = 'light';
  await page.route('**/src/App.jsx*', async route => {
    const original = await (await route.fetch()).text();
    const contextPath = original.match(/from "([^"]*AppContext[^"]*)"/)[1];
    await route.fulfill({ contentType: 'application/javascript', body: `
      import React from '/node_modules/.vite/deps/react.js';
      import {AppProvider,useApp} from '${contextPath}';
      import AppShell from '/src/components/AppShell.jsx';
      import Library from '/src/pages/Library.jsx';
      function Fixture() {
        const {user}=useApp();
        const [view,setView]=React.useState('home'), [tools,setTools]=React.useState(false), [action,setAction]=React.useState(''), [uploads,setUploads]=React.useState(0);
        return React.createElement(AppShell,{activeView:view,onNavigate:setView,toolsOpen:tools,onOpenTools:()=>setTools(true),
          onImportRecipe:()=>setAction('import'),onAddYarn:()=>setAction('yarn'),onAddTool:()=>setAction('tool')},
          React.createElement('div',{className:'surface-view','data-view':view,'data-action':action,'data-uploads':uploads,'data-user':user?.username,style:{padding:view==='recipes'?0:'80px 20px'}},
            view==='recipes'?React.createElement(Library,{onRecipeClick:()=>{},onUploadClick:()=>{setAction('recipe');setUploads(n=>n+1);}}):React.createElement('h1',null,view),
            tools&&React.createElement('button',{className:'surface-tools-close',onClick:()=>setTools(false)},'Close tools')));
      }
      export default function App(){return React.createElement(AppProvider,null,React.createElement(Fixture));}
    ` });
  });
  await page.route('**/api/**', route => {
    const pathname = new URL(route.request().url()).pathname;
    const data = pathname === '/api/auth/me' ? { id: 1, username: 'QA', language, theme }
      : pathname === '/api/setup/status' ? { setup_required: false }
      : ['/api/categories','/api/tags'].includes(pathname) ? []
      : pathname === '/api/recipes' ? { recipes: Array.from({length:40},(_,i)=>({id:'qa-'+i,title:'Test pattern '+i,file_type:'pdf',categories:[],tags:[],project_status:'none',created_date:'2026-11-24'})),total:40,pages:1,page:1 } : {};
    return route.fulfill({ json: data });
  });
  const nav = page.locator('.mobile-nav');
  const main = nav.locator('.mobile-nav-item-main');
  const verify = async selectedIndex => {
    const result = await nav.evaluate(nav => {
      const rect = nav.getBoundingClientRect();
      const luminance = color => color.match(/[\d.]+/g).slice(0, 3).map(Number).map(v => {
        v /= 255; return v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4;
      }).reduce((sum, v, i) => sum + v * [.2126, .7152, .0722][i], 0);
      const buttons = [...nav.querySelectorAll('.mobile-nav-item-main,.mobile-nav-main-split-btn')].map(el => {
        const r = el.getBoundingClientRect(), style = getComputedStyle(el), label = getComputedStyle(el.querySelector('span'));
        const text=el.querySelector('span');
        return { left: r.left, right: r.right, top: r.top, width: r.width, height: r.height, visibleLabel: label.opacity !== '0' && label.maxHeight !== '0px', fullLabel: text.scrollWidth<=text.clientWidth, text:text.textContent, active: el.classList.contains('active'), color: style.color, background: style.backgroundColor };
      });
      const active = buttons.find(button => button.active), a = luminance(active.color), b = luminance(active.background);
      return { buttons, left: rect.left, right: rect.right, height: rect.height, contrast: (Math.max(a, b) + .05) / (Math.min(a, b) + .05) };
    });
    assert.equal(result.height, 64);
    assert.equal(result.buttons.length, 5);
    assert(result.contrast >= 4.5, 'selected tab contrast ' + result.contrast);
    assert.equal(result.buttons.filter(button => button.active).length, 1);
    assert(result.buttons[selectedIndex].active);
    for (const [i, button] of result.buttons.entries()) {
      assert(button.width >= 44 && button.height >= 44, 'touch target ' + JSON.stringify(button));
      assert(button.visibleLabel, 'labels stay visible on every tab');
      assert(button.fullLabel, 'navigation caption fits: '+button.text);
      assert(button.left >= result.left && button.right <= result.right, 'button inside navigation');
      if (i) assert(button.left >= result.buttons[i - 1].right && Math.abs(button.top - result.buttons[0].top) < 1, 'one aligned row');
    }
  };
  for (language of ['en', 'no', 'de', 'fr', 'es', 'hu']) {
    for (theme of ['light', 'dark']) {
      await page.goto(url);
      await page.waitForFunction(theme => document.documentElement.dataset.theme === theme && document.querySelector('.surface-view[data-user="QA"]'), theme);
      for (const width of [320, 390, 768, 844]) {
        await page.setViewportSize({ width, height: width > 768 ? 430 : 844 });
        for (const [index, view, selected] of [[0, 'home', 0], [1, 'recipes', 1], [2, 'inventory', 3]]) {
          await main.nth(index).click();
          await page.locator(`.surface-view[data-view="${view}"]`).waitFor();
          await verify(selected);
          if (process.env.QA_NAV_SCREENSHOTS && language === 'no' && theme === 'light' && width === 390) {
            await nav.screenshot({ path: path.join(process.env.QA_NAV_SCREENSHOTS, `navigation-${view}.png`) });
          }
        }
      }
      console.log('PASS navigation layouts', language, theme);
    }
  }
  await page.setViewportSize({ width: 390, height: 844 });
  for (const [index, view] of [[0, 'stats'], [1, 'help'], [2, 'settings']]) {
    await main.last().click();
    await page.locator('.app-menu-item').nth(index).click();
    await page.locator(`.surface-view[data-view="${view}"]`).waitFor();
    await verify(4);
  }
  await main.nth(1).click();
  const headerAdd=page.locator('.collection-toolbar-heading .collection-primary-action');
  await headerAdd.waitFor();
  assert(await headerAdd.evaluate(el=>el.getBoundingClientRect().width>=44 && el.getBoundingClientRect().height>=44));
  await headerAdd.click();
  await page.locator('.surface-view[data-uploads="1"]').waitFor();
  await page.evaluate(()=>window.scrollTo(0,document.body.scrollHeight));
  const compactAdd=page.locator('.collection-compact-search.visible .collection-primary-action');
  await compactAdd.waitFor();
  await page.waitForFunction(()=>{
    const bar=document.querySelector('.collection-compact-search.visible');
    const r=bar?.getBoundingClientRect();
    return r && r.top>=0 && r.bottom<=innerHeight && getComputedStyle(bar).opacity==='1';
  });
  await compactAdd.click();
  await page.locator('.surface-view[data-uploads="2"]').waitFor();
  assert(await page.locator('.collection-compact-search-inner').evaluate(el=>el.scrollWidth<=el.clientWidth),'compact search and Add fit together');
  await page.evaluate(()=>window.scrollTo(0,0));
  for (const [index, action] of [[0, 'import'], [1, 'yarn'], [2, 'tool']]) {
    await main.last().click();
    await page.locator('.app-menu-create').click();
    await page.locator('.add-menu-item').nth(index).click();
    await page.locator(`.surface-view[data-action="${action}"]`).waitFor();
    await page.locator('.add-menu').waitFor({ state: 'detached' });
  }
  await nav.locator('.mobile-nav-main-split-btn--tools').click();
  await nav.waitFor({ state: 'detached' });
  await page.locator('.surface-tools-close').click();
  await nav.waitFor();
  await nav.locator('.mobile-nav-collapse').click();
  await page.locator('.mobile-nav-peek').click();
  await verify(1);
  assert.deepEqual(errors, []);
  console.log('PASS contextual Add recipe in header and compact search, five consistent navigation actions, six locales, light/dark themes, global Add menu, Tools and collapse');
})().catch(error => { console.error(error); process.exitCode = 1; }).finally(async () => {
  await browser?.close(); server.kill();
});
