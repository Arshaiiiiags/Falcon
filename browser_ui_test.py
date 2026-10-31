"""Hub design checks: EN/FA, five themes, responsive layouts and axe.

Uses browser_test's isolated database/two-worker server harness.
python browser_ui_test.py --browser /usr/bin/chromium --axe /tmp/axe.min.js
"""
import json
from playwright.sync_api import sync_playwright, expect
import browser_test

def run_flow(base,browser_path,screenshots,axe_path):
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path=browser_path,headless=True,args=['--no-sandbox'])
  context=browser.new_context(viewport={'width':1440,'height':1000})
  context.add_init_script("localStorage.setItem('pgc_lang','en')")
  page=context.new_page();errors=[];failed=[]
  page.on('pageerror',lambda e:errors.append(str(e)))
  page.on('response',lambda r:failed.append((r.status,r.url)) if r.status>=400 and '/api/' not in r.url else None)
  page.goto(base,wait_until='networkidle')
  def audit(label):
   if axe_path:
    page.add_script_tag(path=axe_path)
    result=page.evaluate("async()=>{const r=await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa']}});return r.violations.map(v=>({id:v.id,nodes:v.nodes.map(n=>n.target)}))}")
    assert not result,(label,result)
  def nav(view):
   if page.viewport_size['width']<=700:
    page.locator('[data-action=menu]').click()
   page.locator(f'.nav-item[data-view={view}]').click()
   expect(page.locator('#main')).to_have_attribute('aria-busy','false')
  for locale in ['en','fa']:
   if page.locator('html').get_attribute('lang')!=locale:
    page.locator('[data-action=language]').click()
    expect(page.locator('html')).to_have_attribute('lang',locale)
   for theme in ['royal-gold','midnight-purple','persian-turquoise','dark-minimal','light-ivory']:
    page.set_viewport_size({'width':1440,'height':1000})
    nav('settings');page.locator(f'[data-action=theme][data-theme={theme}]').click()
    expect(page.locator('html')).to_have_attribute('data-theme',theme)
    audit(f'{locale} {theme} settings')
    nav('lounge')
    expect(page.locator('.game-card')).to_have_count(3)
    assert page.locator('.hero').count()==0
    assert page.locator('.game-card .button').last.bounding_box()['y']<900
    for width in [320,390,768,1024,1440]:
     page.set_viewport_size({'width':width,'height':1000})
     assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'),(locale,theme,width)
     assert page.locator('.game-card img').evaluate_all('(imgs)=>imgs.every(i=>i.complete&&i.naturalWidth>0)')
     if width in [390,1440]:
      audit(f'{locale} {theme} hub {width}')
      if theme in ['royal-gold','dark-minimal']:
       page.screenshot(path=str(screenshots/f'hub-{locale}-{theme}-{width}.png'),full_page=True)
    print(f'PASS {locale} {theme}: settings, hub, assets and five widths'+(' + axe' if axe_path else ''),flush=True)
  page.set_viewport_size({'width':390,'height':844})
  page.locator('.game-card [data-action=setup]').first.click()
  expect(page.locator('#modal')).to_be_visible();audit('registration modal')
  page.screenshot(path=str(screenshots/'register-fa-mobile.png'),full_page=True)
  page.keyboard.press('Escape');expect(page.locator('#modal')).not_to_be_visible()
  page.locator('[data-action=menu]').click();expect(page.locator('.sidebar')).to_be_visible()
  page.keyboard.press('Escape');expect(page.locator('.sidebar')).not_to_be_visible()
  assert not errors,errors
  assert not failed,failed
  print('PASS registration, keyboard dismissal, no JS errors or missing assets',flush=True)
  browser.close()

if __name__=='__main__':
 browser_test.run_flow=run_flow
 browser_test.main()
