"""Actual browser smoke of the public package; no mocks, hardware or private apps.

Install .[browser], then `python -m playwright install chromium` (or use
--browser-channel msedge for an installed Edge). Starts/stops its own local API/UI.
"""
from __future__ import annotations
import argparse,json,os,shutil,subprocess,sys,time,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]

def ready(url,process,seconds=45):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if process.poll() is not None: raise RuntimeError('Test server exited; inspect .cache/browser logs')
        try:
            with urllib.request.urlopen(url,timeout=1) as response:
                if response.status==200:return
        except Exception:pass
        time.sleep(.2)
    raise RuntimeError('Server readiness timeout: '+url)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--browser-channel');p.add_argument('--api-port',type=int,default=8875);p.add_argument('--ui-port',type=int,default=5118);args=p.parse_args()
    output=ROOT/'.cache/browser';output.mkdir(parents=True,exist_ok=True)
    node=shutil.which('node');assert node,'Node.js is required'
    env=dict(os.environ,XPP_API_URL=f'http://127.0.0.1:{args.api_port}',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
    flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
    processes=[];logs=[];report=[]
    try:
        for name,cmd,cwd in [('api',[sys.executable,'-m','xp_plus','api','--port',str(args.api_port)],ROOT),('ui',[node,str(ROOT/'web/node_modules/vite/bin/vite.js'),'--host','127.0.0.1','--port',str(args.ui_port)],ROOT/'web')]:
            log=(output/(name+'.log')).open('w',encoding='utf-8');logs.append(log)
            processes.append(subprocess.Popen(cmd,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=flags))
        ready(f'http://127.0.0.1:{args.api_port}/xpp/api/health',processes[0])
        base=f'http://127.0.0.1:{args.ui_port}';ready(base,processes[1])
        with sync_playwright() as pw:
            options={'headless':True}
            if args.browser_channel:options['channel']=args.browser_channel
            browser=pw.chromium.launch(**options)
            try:
                for width in (1440,1280):
                    page=browser.new_page(viewport={'width':width,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.goto(base+'/reproduce');page.get_by_role('link',name='XP Plus · Public MVP',exact=True).wait_for()
                    page.get_by_text('RTD tracer, tau = 9 min',exact=True).wait_for()
                    page.goto(base+'/reproduce/dfe_rtd_9');page.get_by_role('button',name='Check the paper as written',exact=True).wait_for()
                    with page.expect_response(lambda r:r.url.endswith('/dfe_rtd_9/gate') and r.request.method=='POST') as response:
                        page.get_by_role('button',name='Check the paper as written',exact=True).click()
                    gate=response.value.json();assert not gate['passed']
                    assert sum(g['blocking'] and g['status']=='open' for g in gate['gaps'])>=4
                    page.get_by_role('button',name='Rig',exact=True).click();page.locator('.react-flow__node[data-id="reactor"]').wait_for();page.locator('.react-flow__node[data-id="reactor"]').click()
                    page.get_by_text('Paper stated',exact=True).first.wait_for()
                    page.get_by_text('Volume (\u00b5L)',exact=True).wait_for()
                    page.screenshot(path=str(output/f'rig-{width}.png'))
                    with page.expect_response(lambda r:r.url.endswith('/dfe_rtd_9/run') and r.request.method=='POST',timeout=120000) as response:
                        page.get_by_role('button',name='Run XP Plus',exact=True).click()
                    standard=response.value.json();assert standard['verdict']=='insufficient_data' and standard['twin'] is not None and standard['physical'] is None,standard
                    page.get_by_text('Insufficient data',exact=True).first.wait_for()
                    page.get_by_role('button',name='Standard',exact=True).click()
                    with page.expect_download() as download:
                        page.get_by_role('link',name='Download Standard (JSON)',exact=True).click()
                    destination=output/f'standard-{width}.json';download.value.save_as(str(destination));exported=json.loads(destination.read_text())
                    assert exported['standard_id']==standard['standard_id'] and exported['features']['paper']['doi']=='10.1038/s44286-025-00249-z'
                    assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth'), 'Page overflows horizontally'
                    page.screenshot(path=str(output/f'standard-{width}.png'));assert not errors,errors
                    report.append({'width':width,'gate_blocked_as_expected':True,'rig_provenance_inspected':True,'actual_twin_executed':True,'standard_downloaded':True,'verdict':standard['verdict'],'browser_errors':errors})
                    page.close()
            finally:browser.close()
        (output/'results.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
        for log in logs:log.close()

if __name__=='__main__':main()
