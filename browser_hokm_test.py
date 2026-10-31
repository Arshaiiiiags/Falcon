"""Four-player Hokm browser QA, with an isolated seeded initial Hakem draw.

python browser_hokm_test.py --browser /usr/bin/chromium --axe /tmp/axe.min.js --screenshots /tmp/hokm-qa
Uses two Gunicorn workers and a disposable database; never touches the live account DB.
"""
import argparse
import json
import os
from pathlib import Path
import random
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import build_opener,ProxyHandler
from urllib.error import URLError
import uuid
from playwright.sync_api import sync_playwright,expect
import hokm_engine as hk


def run_flow(base,browser_path,axe,screenshots):
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path=browser_path,headless=True,args=['--no-sandbox'])
  context=browser.new_context(viewport={'width':1440,'height':1050})
  context.add_init_script("localStorage.setItem('pgc_lang','en')")
  page=context.new_page();errors=[];failed=[]
  page.on('pageerror',lambda e:errors.append(str(e)))
  page.on('response',lambda r:failed.append((r.status,r.url)) if r.status>=400 and '/api/' not in r.url else None)
  def idle():expect(page.locator('#main')).to_have_attribute('aria-busy','false')
  def capture(name):
   page.wait_for_function("[...document.images].every(i=>i.complete&&i.naturalWidth>0)")
   page.screenshot(path=str(screenshots/name),full_page=True)
  def audit(label):
   if not axe:return
   page.add_script_tag(path=axe)
   report=page.evaluate("async()=>{let r=await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa']}});return r.violations.map(v=>({id:v.id,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))}))}")
   assert not report,(label,report)
  def action(selector,suffix):
   with page.expect_response(lambda r:f'/hokm/{suffix}' in r.url and r.request.method=='POST') as response:
    page.locator(selector).click()
   out=response.value.json();assert response.value.status==200,out
   idle();return out
  def responsive():
   for lang in ['en','fa']:
    if page.locator('html').get_attribute('lang')!=lang:
     page.locator('[data-action=language]').click();idle()
    for width in [320,390,768,1440]:
     page.set_viewport_size({'width':width,'height':900})
     assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'),(lang,width)
     expect(page.locator('.hokm-seat')).to_have_count(4)
     for seat in range(4):expect(page.locator(f'.hokm-seat-{seat}')).to_be_visible()
   page.set_viewport_size({'width':1440,'height':1050})
   if page.locator('html').get_attribute('lang')!='en':page.locator('[data-action=language]').click();idle()
  page.goto(base,wait_until='networkidle')
  expect(page.locator('.game-grid .game-card')).to_have_count(3)
  page.locator('[data-action=signup]').first.click()
  page.locator('#auth-username').fill('hokm_'+uuid.uuid4().hex[:8]);page.locator('#auth-password').fill('password123');page.locator('#auth-confirm').fill('password123')
  page.locator('button[type=submit]').click();expect(page.locator('#modal')).not_to_be_visible();idle()
  page.locator('[data-action=setup][data-game=hokm]').first.click()
  page.locator('input[value=medium]').check()
  with page.expect_response(lambda r:'/hokm/start' in r.url and r.request.method=='POST') as response:
   page.locator('.setup-form button[type=submit]').click()
  out=response.value.json();assert response.value.status==201,out;idle()
  expect(page.locator('.hokm-choose')).to_be_visible()
  expect(page.locator('.hokm-first-five .playing-card')).to_have_count(5)
  expect(page.locator('[data-action=hokm-trump]')).to_have_count(4)
  expect(page.locator('.balance')).to_have_text('95')
  responsive();audit('trump selection');capture('hokm-choose-desktop.png')
  page.set_viewport_size({'width':390,'height':844});capture('hokm-choose-mobile.png')
  page.set_viewport_size({'width':1440,'height':1050})
  out=action('[data-action=hokm-trump][data-suit=S]','trump')
  expect(page.locator('.hokm-hand-cards .playing-card')).to_have_count(13)
  print('PASS human Hakem, first-five choice, deal to 13, four seats, en/fa responsive layouts',flush=True)
  steps=0;checked_full_trick=False;checked_resume=False;checked_hand_end=False
  while out['match_status']=='active':
   assert steps<700
   st=out['state']
   if st['can_choose_trump']:
    out=action('[data-action=hokm-trump][data-suit=H]','trump')
   elif st['can_continue']:
    expect(page.locator('.hokm-play')).to_have_count(4)
    if not checked_full_trick:
     responsive()
     for _ in range(5):
      audit('Hokm full trick, '+page.locator('html').get_attribute('data-theme'))
      page.locator('[data-action=theme-cycle]').click();idle()
     capture('hokm-play-desktop.png')
     page.locator('[data-action=language]').click();idle()
     page.set_viewport_size({'width':390,'height':844});audit('Persian mobile Hokm');capture('hokm-play-mobile.png')
     page.set_viewport_size({'width':1440,'height':1050});page.locator('[data-action=language]').click();idle()
     checked_full_trick=True
    if st['phase']=='hand_end' and not checked_hand_end:
     audit('Hokm hand end');capture('hokm-hand-result.png');checked_hand_end=True
    if not checked_resume:
     old=out
     page.reload(wait_until='networkidle')
     page.locator('[data-action=resume]').first.click();idle()
     expect(page.locator('.hokm-table')).to_be_visible()
     expect(page.locator('.hokm-play')).to_have_count(4)
     assert page.request.get(base+f"/api/matches/{out['match_id']}/hokm").json()==old
     checked_resume=True
    out=action('[data-action=hokm-continue]','continue')
   else:
    legal=st['legal_cards'];assert legal
    actual=page.locator('[data-action=hokm-card]:enabled').evaluate_all('(els)=>els.map(e=>e.dataset.card)')
    assert sorted(actual)==sorted(legal),(actual,legal)
    page.locator(f'[data-action=hokm-card][data-card="{legal[0]}"]').click()
    expect(page.locator(f'[data-action=hokm-card][data-card="{legal[0]}"]')).to_have_attribute('aria-pressed','true')
    out=action('[data-action=hokm-play]','move')
   steps+=1
  expect(page.locator('.terminal-panel')).to_be_visible()
  assert out['state']['finished'] and max(out['state']['scores'])>=7
  audit('Hokm match complete');capture('hokm-completed.png')
  print('PASS complete match to 7, legal-card controls, trick/hand results, resume, all themes and accessibility',flush=True)
  page.locator('[data-action=navigate][data-view=history]').first.click();idle()
  page.locator('[data-filter=historyGame]').select_option('hokm');idle()
  expect(page.locator('tbody tr')).to_have_count(1)
  page.locator('[data-action=navigate][data-view=rankings]').first.click();idle()
  page.locator('[data-filter=rankGame]').select_option('hokm');idle()
  expect(page.locator('tbody tr')).to_have_count(1)
  page.locator('[data-action=navigate][data-view=rules]').first.click();idle()
  expect(page.locator('[data-action=setup][data-game=hokm]')).to_be_visible();audit('rules')
  page.locator('[data-action=setup][data-game=hokm]').click()
  with page.expect_response(lambda r:'/hokm/start' in r.url and r.request.method=='POST'):
   page.locator('.setup-form button[type=submit]').click()
  idle();page.locator('[data-action=resign]').click();page.locator('[data-action=confirm-resign]').click();idle()
  expect(page.locator('.terminal-panel')).to_be_visible()
  expect(page.locator('.balance')).to_have_text('90')
  assert not errors,errors
  assert not failed,failed
  print('PASS Hokm history, leaderboard, rules, resignation, one fee per match; no JS or asset errors',flush=True)
  browser.close()


def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--browser',default=shutil.which('chromium'))
 parser.add_argument('--axe');parser.add_argument('--screenshots',type=Path)
 args=parser.parse_args()
 root=Path(__file__).parent
 seed=next(n for n in range(100) if hk.new_game(rng=random.Random(n))['hakem']==0)
 with tempfile.TemporaryDirectory(prefix='hokm-browser-') as directory:
  tmp=Path(directory);screenshots=args.screenshots or tmp/'screenshots';screenshots.mkdir(parents=True,exist_ok=True)
  config=tmp/'seed.py'
  config.write_text(f"def post_fork(server, worker):\n import hokm_engine as hk, random\n original=hk.new_game\n hk.new_game=lambda level='medium': original(level,random.Random({seed}))\n")
  with socket.socket() as listener:listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
  env=dict(os.environ,APP_ENV='development',SECRET_KEY=secrets.token_hex(32),TRUST_PROXY='0',DATABASE_PATH=str(tmp/'qa.db'))
  base=f'http://127.0.0.1:{port}'
  opener=build_opener(ProxyHandler({}))
  with (tmp/'server.log').open('w+') as log:
   process=subprocess.Popen([sys.executable,'-m','gunicorn','app:app','--workers','2','--config',str(config),'--bind',f'127.0.0.1:{port}'],cwd=root,env=env,stdout=log,stderr=log)
   try:
    for _ in range(100):
     if process.poll() is not None:log.seek(0);raise RuntimeError(log.read())
     try:
      with opener.open(base+'/api/health',timeout=1) as response:assert response.status==200
      break
     except (URLError,TimeoutError):time.sleep(.05)
    else:raise RuntimeError('Server did not start')
    run_flow(base,args.browser,args.axe,screenshots)
   except BaseException:
    log.seek(0);print(log.read(),file=sys.stderr);raise
   finally:
    process.terminate()
    try:process.wait(timeout=10)
    except subprocess.TimeoutExpired:process.kill();process.wait()
 if args.screenshots:print('Screenshots:',args.screenshots.resolve())


if __name__=='__main__':main()
