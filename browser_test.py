"""Browser QA with isolated storage and two local Gunicorn workers.

Install requirements-dev.txt, then run:
  python browser_test.py --browser /usr/bin/chromium
Optional: --axe /path/to/axe.min.js --screenshots /tmp/club-screenshots
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from urllib.request import urlopen
from urllib.error import URLError
from playwright.sync_api import sync_playwright, expect

def run_flow(BASE,browser_path,screenshots,axe_path):
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path=browser_path,headless=True,args=['--no-sandbox'])
  context=browser.new_context(viewport={'width':1440,'height':1000})
  context.add_init_script("localStorage.setItem('pgc_lang','en')")
  page=context.new_page();errors=[];failed=[]
  page.on('pageerror',lambda e:errors.append(str(e)))
  page.on('response',lambda r: failed.append((r.status,r.url)) if r.status>=400 and '/api/' not in r.url else None)
  page.goto(BASE,wait_until='networkidle')
  page.locator('[data-action=signup]').first.click()
  page.locator('#auth-username').fill('visual_'+uuid.uuid4().hex[:8])
  page.locator('#auth-password').fill('password123')
  page.locator('#auth-confirm').fill('password123')
  page.locator('button[type=submit]').click()
  expect(page.locator('#modal')).not_to_be_visible()
  expect(page.locator('.balance')).to_have_text('100')
  print('PASS signup and initial balance',flush=True)
  page.locator('[data-action=setup][data-game=backgammon]').first.click()
  page.locator('input[value=easy]').check();page.locator('input[name=cube]').check()
  page.locator('.setup-form button[type=submit]').click()
  expect(page.locator('.backgammon-board')).to_be_visible()
  print('PASS start backgammon',flush=True)
  for i in range(12):
   if page.locator('[data-action=bg-roll]').count():
    page.locator('[data-action=bg-roll]').click()
   elif page.locator('[data-action=cube-accept]').count():
    page.locator('[data-action=cube-accept]').click()
   else:
    point=page.locator('.point.movable').first if page.locator('.point.movable').count() else page.locator('[data-action=bg-point][data-point=bar]')
    point.click()
    expect(point).to_be_focused()
    (page.locator('.destination').first if page.locator('.destination').count() else page.locator('[data-action=bg-point][data-point=off]')).click()
   expect(page.locator('#main')).to_have_attribute('aria-busy','false')
  if axe_path:
   page.add_script_tag(path=axe_path)
   violations=page.evaluate("async()=>{const r=await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa']}});return r.violations.map(v=>({id:v.id,nodes:v.nodes.map(n=>n.target)}))}")
   assert not violations,violations
  page.screenshot(path=str(screenshots/'pgc-backgammon-desktop.png'),full_page=True)
  for locale in ['en','fa']:
   if page.locator('html').get_attribute('lang')!=locale:
    page.locator('[data-action=language]').click()
    expect(page.locator('html')).to_have_attribute('lang',locale)
   for width in [320,390,768,1440]:
    page.set_viewport_size({'width':width,'height':844})
    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'),f'bg overflow {locale} {width}'
  if page.locator('html').get_attribute('lang')!='en':
   page.locator('[data-action=language]').click()
   expect(page.locator('html')).to_have_attribute('lang','en')
  page.set_viewport_size({'width':390,'height':844})
  page.wait_for_timeout(250)
  page.screenshot(path=str(screenshots/'pgc-backgammon-mobile.png'),full_page=True)
  page.reload(wait_until='networkidle')
  expect(page.locator('h1')).to_contain_text('Welcome back')
  page.locator('[data-action=resume]').first.click()
  expect(page.locator('.backgammon-board')).to_be_visible()
  page.locator('[data-action=resign]').click();page.locator('[data-action=confirm-resign]').click()
  expect(page.locator('.terminal-panel')).to_be_visible()
  print('PASS moves, mobile board, resume, resignation',flush=True)
  page.set_viewport_size({'width':1440,'height':1000})
  page.locator('[data-action=navigate][data-view=lounge]').first.click()
  page.locator('[data-action=setup][data-game=pasur]').first.click()
  page.locator('input[value=easy]').check();page.locator('.setup-form button[type=submit]').click()
  expect(page.locator('.pasur-board')).to_be_visible()
  for i in range(12):
   page.locator('[data-action=hand-card]').first.click()
   page.locator('[data-action=pasur-suggest]').click()
   page.locator('[data-action=pasur-play]').click()
   expect(page.locator('#main')).to_have_attribute('aria-busy','false')
  if axe_path:
   page.add_script_tag(path=axe_path)
   violations=page.evaluate("async()=>{const r=await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa']}});return r.violations.map(v=>({id:v.id,nodes:v.nodes.map(n=>n.target)}))}")
   assert not violations,violations
  page.screenshot(path=str(screenshots/'pgc-pasur-desktop.png'),full_page=True)
  for locale in ['en','fa']:
   if page.locator('html').get_attribute('lang')!=locale:
    page.locator('[data-action=language]').click()
    expect(page.locator('html')).to_have_attribute('lang',locale)
   for width in [320,390,768,1440]:
    page.set_viewport_size({'width':width,'height':844})
    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'),f'pasur overflow {locale} {width}'
  if page.locator('html').get_attribute('lang')!='en':
   page.locator('[data-action=language]').click()
   expect(page.locator('html')).to_have_attribute('lang','en')
  page.set_viewport_size({'width':390,'height':844})
  page.wait_for_timeout(250)
  page.screenshot(path=str(screenshots/'pgc-pasur-mobile.png'),full_page=True)
  page.locator('[data-action=resign]').click();page.locator('[data-action=confirm-resign]').click()
  expect(page.locator('.terminal-panel')).to_be_visible()
  page.set_viewport_size({'width':1440,'height':1000})
  print('PASS Pasur selection, moves, and responsive table',flush=True)
  page.locator('[data-action=navigate][data-view=settings]').click()
  for theme in ['midnight-purple','persian-turquoise','dark-minimal','light-ivory','royal-gold']:
   page.locator(f'[data-theme="{theme}"]').click()
   expect(page.locator('html')).to_have_attribute('data-theme',theme)
   expect(page.locator('#main')).to_have_attribute('aria-busy','false')
   if axe_path:
    page.add_script_tag(path=axe_path)
    violations=page.evaluate("async()=>{const r=await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa']}});return r.violations.map(v=>({id:v.id,nodes:v.nodes.map(n=>n.target)}))}")
    assert not violations,(theme,violations)
  page.locator('#language-setting').select_option('fa')
  expect(page.locator('html')).to_have_attribute('dir','rtl')
  page.reload(wait_until='networkidle')
  expect(page.locator('html')).to_have_attribute('dir','rtl')
  page.locator('[data-action=language]').click()
  expect(page.locator('html')).to_have_attribute('dir','ltr')
  page.locator('[data-action=navigate][data-view=history]').first.click()
  expect(page.locator('tbody tr')).to_have_count(2)
  page.locator('[data-action=navigate][data-view=rankings]').click()
  expect(page.locator('h1')).to_have_text('Rankings')
  page.locator('select[data-filter=rankGame]').select_option('pasur')
  page.locator('select[data-filter=rankLevel]').select_option('easy')
  expect(page.locator('#main')).to_have_attribute('aria-busy','false')
  page.locator('[data-action=navigate][data-view=rules]').click()
  expect(page.locator('h1')).to_have_text('A little know-how. A better game.')
  print('PASS history, rankings, themes, locale persistence, rules',flush=True)
  if axe_path:
   for view in ['rules','lounge','history','rankings','settings']:
    page.locator(f'[data-action=navigate][data-view={view}]').first.click()
    expect(page.locator('#main')).to_have_attribute('aria-busy','false')
    page.add_script_tag(path=axe_path)
    report=page.evaluate("async()=>{const r=await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa']}});return r.violations.map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.map(n=>n.target)}))}")
    assert not report, (view,report)
   print('PASS: axe WCAG A/AA checks on five signed-in screens',flush=True)
  else:
   print('SKIP: axe checks (pass --axe /path/to/axe.min.js to enable)',flush=True)
  page.locator('[data-action=navigate][data-view=lounge]').first.click()
  page.evaluate("async()=>{await navigator.serviceWorker.ready; if(!navigator.serviceWorker.controller) await new Promise(resolve=>navigator.serviceWorker.addEventListener('controllerchange',resolve,{once:true}));}")
  cached=page.evaluate("async()=>{const keys=await caches.keys();const urls=[];for(const key of keys){const cache=await caches.open(key);urls.push(...(await cache.keys()).map(r=>new URL(r.url).pathname));}return urls;}")
  assert '/' in cached and '/club-art.png' in cached
  assert not any(path.startswith('/api/') for path in cached),cached
  context.set_offline(True)
  page.reload(wait_until='domcontentloaded')
  expect(page.locator('.offline-banner')).to_be_visible()
  expect(page.locator('#collection')).to_be_visible()
  expect(page.locator('#collection .game-card')).to_have_count(3)
  context.set_offline(False)
  page.reload(wait_until='networkidle')
  expect(page.locator('h1')).to_contain_text('Welcome back')
  print('PASS: offline public shell, no private API cache, online recovery',flush=True)
  page.set_viewport_size({'width':390,'height':844})
  page.locator('[data-action=menu]').click()
  expect(page.locator('.sidebar')).to_be_visible()
  page.keyboard.press('Escape')
  expect(page.locator('.sidebar')).not_to_be_visible()
  page.screenshot(path=str(screenshots/'navigation-mobile.png'),full_page=True)
  assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'),page.evaluate("[...document.querySelectorAll('body *')].map(e=>({tag:e.tagName,cls:e.className,r:e.getBoundingClientRect().right,l:e.getBoundingClientRect().left,v:getComputedStyle(e).visibility})).filter(x=>x.v!=='hidden'&&(x.r>innerWidth+1||x.l < -1)).slice(0,20)")
  print('PASS: mobile navigation and Escape key',flush=True)
  page.set_viewport_size({'width':1440,'height':1000})
  assert not errors,errors
  assert not failed,failed
  print('PASS: no JavaScript exceptions or failed asset requests',flush=True)
  page.screenshot(path=str(screenshots/'pgc-signed-in.png'),full_page=True)
  browser.close()

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--browser',default=shutil.which('chromium') or shutil.which('google-chrome'))
 parser.add_argument('--axe',help='Path to a locally installed axe-core axe.min.js')
 parser.add_argument('--screenshots',type=Path,help='Directory for QA screenshots; otherwise temporary')
 args=parser.parse_args()
 with tempfile.TemporaryDirectory(prefix='pgc-browser-') as directory:
  screenshots=args.screenshots or Path(directory)/'screenshots'
  screenshots.mkdir(parents=True,exist_ok=True)
  with socket.socket() as listener:
   listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
  BASE=f'http://127.0.0.1:{port}'
  env=dict(os.environ,APP_ENV='development',SECRET_KEY=secrets.token_hex(32),TRUST_PROXY='0',DATABASE_PATH=str(Path(directory)/'browser.db'))
  with open(Path(directory)/'server.log','w+') as log:
   process=subprocess.Popen([sys.executable,'-m','gunicorn','app:app','--workers','2','--bind',f'127.0.0.1:{port}'],cwd=Path(__file__).parent,env=env,stdout=log,stderr=log)
   try:
    for _ in range(100):
     if process.poll() is not None:
      log.seek(0);raise RuntimeError(log.read())
     try:
      with urlopen(BASE+'/api/health',timeout=1) as response:
       assert response.status==200
      break
     except (URLError,TimeoutError):time.sleep(.05)
    else:raise RuntimeError('Preview server did not start')
    run_flow(BASE,args.browser,screenshots,args.axe)
   finally:
    process.terminate()
    try:process.wait(timeout=10)
    except subprocess.TimeoutExpired:process.kill();process.wait()
 if args.screenshots:print('Screenshots:',args.screenshots.resolve())

if __name__=='__main__':main()
