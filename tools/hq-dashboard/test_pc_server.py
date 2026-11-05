"""Synthetic integration checks; no real workbook or AI calls."""
import hashlib
import http.client
import importlib.util
import json
from pathlib import Path
import secrets
import ssl
import subprocess
import tempfile
import threading
import time
import sys
import shutil
import unittest
import uuid
from urllib.parse import urlencode

import openpyxl

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('hq_pc', HERE / 'server.py')
hq = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hq)


class Integration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hq-pc-test-')
        self.state = Path(self.tmp.name)
        self.password = secrets.token_urlsafe(24)
        salt = secrets.token_hex(16)
        (self.state / 'password.json').write_text(json.dumps({'salt': salt, 'hash': hq.password_hash(self.password, salt)}))
        self.book = self.state / 'fictional.xlsx'
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Fictional jobs'
        ws.append(['#', 'Company', 'Role', 'My status', 'Date applied', 'Notes', 'Link'])
        ws.append([1, 'Example Company', 'Example Engineer', 'Suggested (not applied)', '', 'Example only', 'https://example.com/job'])
        wb.save(self.book)
        wb.close()
        self.app = hq.App(self.state, self.book, 'http://127.0.0.1')
        self.app.scan_log_dir = self.state
        self.app.cv_work = self.state
        self.server = hq.ThreadingHTTPServer(('127.0.0.1', 0), hq.handler(self.app))
        self.port = self.server.server_port
        self.app.origin = f'http://127.0.0.1:{self.port}'
        self.app.host = f'127.0.0.1:{self.port}'
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.cookie = ''

    def tearDown(self):
        self.app.queue.stop()
        self.app.ai.stop()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def request(self, method, path, data=None, origin=True, host=None):
        headers = {'Host': host or self.app.host, 'Cookie': self.cookie}
        if origin:
            headers['Origin'] = origin if isinstance(origin,str) else self.app.origin
        if path == '/api/login':
            body = urlencode({'password': data or ''})
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
        else:
            body = json.dumps(data) if data is not None else None
            headers['Content-Type'] = 'application/json'
        c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        c.request(method, path, body, headers)
        r = c.getresponse()
        result = r.status, dict(r.getheaders()), r.read()
        c.close()
        return result

    def login(self):
        status, headers, _ = self.request('POST', '/api/login', self.password)
        self.assertEqual(status, 303)
        self.cookie = headers['Set-Cookie'].split(';')[0]
        return headers

    def data(self):
        status, _, body = self.request('GET', '/api/data')
        self.assertEqual(status, 200)
        return json.loads(body)

    def edit(self, **extra):
        d = self.data()
        p = dict(sheet='Fictional jobs', row=2, version=d['version'], expect={'Company': 'Example Company', 'Role': 'Example Engineer'}, note='Saved fictional note',requestId=str(uuid.uuid4()))
        p.update(extra)
        return self.request('POST', '/api/update', p)

    def dismiss_latest(self):
        item = self.app.queue.recent()[0]
        self.assertEqual(self.request('POST','/api/writes/dismiss',{'id':item['id']})[0],200)

    def test_queue_survives_restart_and_retries_once(self):
        self.login()
        lock = self.book.with_name('~$' + self.book.name)
        lock.touch()
        request_id = str(uuid.uuid4())
        self.assertEqual(self.edit(note='Wait for Excel',requestId=request_id)[0],202)
        self.assertEqual(self.edit(note='Second edit blocked')[0],400)
        app2 = hq.App(self.state,self.book,self.app.origin)
        self.assertEqual(app2.queue.get(request_id)['status'],'waiting')
        lock.unlink()
        app2.queue.process_one()
        self.assertEqual(app2.queue.get(request_id)['status'],'saved')
        self.assertEqual(self.data()['jobs'][0]['Notes'],'Wait for Excel')
        version = self.app.tracker.version()
        app2.queue.process_one()
        self.assertEqual(self.app.tracker.version(),version)

    def test_queue_changed_workbook_requires_confirmation(self):
        self.login()
        lock = self.book.with_name('~$' + self.book.name)
        lock.touch()
        self.assertEqual(self.edit(note='Pending note')[0],202)
        lock.unlink()
        wb = openpyxl.load_workbook(self.book)
        wb.active.cell(2,6).value='Edited on PC'
        wb.save(self.book)
        wb.close()
        self.app.queue.process_one()
        self.assertEqual(self.app.queue.recent()[0]['status'],'conflict')
        self.assertEqual(self.data()['jobs'][0]['Notes'],'Edited on PC')
        self.dismiss_latest()

    def test_idempotent_add_and_interrupted_write(self):
        self.login()
        p={'sheet':'Fictional jobs','Company':'Another Example','Role':'Test','version':self.data()['version'],'requestId':str(uuid.uuid4())}
        self.assertEqual(self.request('POST','/api/add',p)[0],200)
        self.assertEqual(self.request('POST','/api/add',p)[0],200)
        self.assertEqual(len(self.data()['jobs']),2)
        p['Company']='Different payload'
        self.assertEqual(self.request('POST','/api/add',p)[0],400)
        with self.app.queue.connect() as db, db:
            db.execute("UPDATE edits SET status='applying' WHERE id=?",(p['requestId'],))
        app2=hq.App(self.state,self.book,self.app.origin)
        self.assertEqual(app2.queue.recent()[0]['status'],'needs_check')
        app2.queue.process_one()
        self.assertEqual(len(self.data()['jobs']),2)

    def test_authentication_and_logout(self):
        self.assertEqual(self.request('GET', '/')[0], 303)
        self.assertEqual(self.request('GET', '/api/data')[0], 401)
        headers = self.login()
        for flag in ('Secure', 'HttpOnly', 'SameSite=Strict'):
            self.assertIn(flag, headers['Set-Cookie'])
        self.assertEqual(len(self.data()['jobs']), 1)
        self.assertEqual(self.request('GET', '/')[0], 200)
        self.assertEqual(self.request('POST', '/api/logout', {})[0], 200)
        self.assertEqual(self.request('GET', '/api/data')[0], 401)

    def test_host_origin_and_route_boundaries(self):
        self.login()
        self.assertEqual(self.request('GET', '/api/data', host='evil.example')[0], 404)
        self.assertEqual(self.request('POST', '/api/update', {}, origin=False)[0], 403)
        self.assertEqual(self.request('POST', '/api/update', {}, origin='null')[0],403)
        self.assertEqual(self.request('POST', '/api/update', {}, origin='https://evil.example')[0],403)
        self.assertEqual(self.request('GET','/login')[1]['Referrer-Policy'],'same-origin')
        for path in ('/server.py', '/../../work/applications-tracker.xlsx', '/.env', '/api/exec'):
            self.assertEqual(self.request('GET', path)[0], 404)

    def test_edits_stale_rows_and_excel_lock(self):
        self.login()
        self.assertEqual(self.edit()[0], 200)
        self.assertEqual(self.data()['jobs'][0]['Notes'], 'Saved fictional note')
        self.assertEqual(self.edit(version='stale')[0], 409)
        self.dismiss_latest()
        self.assertEqual(self.edit(expect={'Company': 'Wrong company', 'Role': 'Example Engineer'})[0], 409)
        self.dismiss_latest()
        lock = self.book.with_name('~$' + self.book.name)
        lock.touch()
        self.assertEqual(self.edit(note='Do not save')[0], 202)
        lock.unlink()
        self.assertEqual(self.data()['jobs'][0]['Notes'], 'Saved fictional note')

    def test_formula_and_long_text_rejected(self):
        self.login()
        self.assertEqual(self.edit(note='=1+1')[0], 400)
        self.assertEqual(self.edit(note='x' * 32768)[0], 400)
        self.assertEqual(self.edit(note='😀' * 17000)[0], 400)

    def test_add_and_read_external_save(self):
        self.login()
        p = {'sheet': 'Fictional jobs', 'Company': 'Second Example', 'Role': 'Test role', 'version': self.data()['version'],'requestId':str(uuid.uuid4())}
        self.assertEqual(self.request('POST', '/api/add', p)[0], 200)
        self.assertEqual(len(self.data()['jobs']), 2)
        wb = openpyxl.load_workbook(self.book)
        wb.active.cell(2, 6).value = 'Fictional scan result'
        wb.save(self.book)
        wb.close()
        self.assertEqual(self.data()['jobs'][0]['Notes'], 'Fictional scan result')

    def test_lockout_survives_restart(self):
        for _ in range(5):
            self.assertEqual(self.request('POST', '/api/login', 'wrong')[0], 401)
        self.assertEqual(self.request('POST', '/api/login', self.password)[0], 429)
        app2 = hq.App(self.state, self.book, self.app.origin)
        self.assertEqual(app2.login(self.password)[1], 429)

    def test_local_unlock_clears_lockout_without_restart(self):
        for _ in range(5):
            self.assertEqual(self.request('POST', '/api/login', 'wrong')[0], 401)
        self.assertEqual(self.app.login(self.password)[1], 429)
        hq.unlock(self.state)
        self.assertEqual(self.app.login(self.password)[1], 200)

    def test_health_requires_completion_marker(self):
        self.assertEqual(self.app.health()['scan']['state'],'unknown')
        log=self.state/'scan-2026-11-04.log'
        log.write_text('=== example start ===\n')
        self.assertEqual(self.app.health()['scan']['state'],'unconfirmed')
        log.write_text('=== 2026-11-04T11:38:14+00:00 end (exit 0) ===\n')
        self.assertEqual(self.app.health()['scan']['state'],'finished')
        log.write_text('=== 2026-11-04T11:38:14+00:00 end (exit 1) ===\n')
        self.assertEqual(self.app.health()['scan']['state'],'failed')

    def test_other_process_writer_lock_queues_edit(self):
        self.login()
        ready=self.state/'lock-ready'
        code='''import importlib.util,sys
from pathlib import Path
s=importlib.util.spec_from_file_location('fixture_lock',sys.argv[1])
m=importlib.util.module_from_spec(s)
s.loader.exec_module(m)
with m.workbook_lock(sys.argv[2]):
    Path(sys.argv[3]).touch()
    sys.stdin.readline()
'''
        child=subprocess.Popen([sys.executable,'-I','-c',code,str(HERE.parent/'tracker'/'workbook_lock.py'),str(self.book),str(ready)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            deadline=time.monotonic()+5
            while not ready.exists() and time.monotonic()<deadline and child.poll() is None:
                time.sleep(.05)
            self.assertTrue(ready.exists(),'Lock fixture failed to start')
            self.assertEqual(self.edit(note='After scan lock')[0],202)
            child.communicate('\n',timeout=5)
            self.assertEqual(child.returncode,0)
            self.app.queue.process_one()
            self.assertEqual(self.data()['jobs'][0]['Notes'],'After scan lock')
        finally:
            if child.poll() is None:
                child.kill()
                child.communicate(timeout=5)


    def test_phone_browser(self):
        from playwright.sync_api import sync_playwright, expect
        # Real local HTTPS and cookie transport; no public service or real data.
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        cert, key = self.state / 'test-cert.pem', self.state / 'test-key.pem'
        openssl = Path('C:/Program Files/Git/usr/bin/openssl.exe')
        subprocess.run([str(openssl),'req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(cert),'-days','1','-subj','/CN=localhost'],
                       check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        self.server = hq.ThreadingHTTPServer(('127.0.0.1',0),hq.handler(self.app))
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(cert,key)
        self.server.socket = tls.wrap_socket(self.server.socket,server_side=True)
        self.port = self.server.server_port
        self.app.origin = f'https://127.0.0.1:{self.port}'
        self.app.host = f'127.0.0.1:{self.port}'
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        with sync_playwright() as p:
            browser = p.webkit.launch()
            # Exercise native browser Origin handling; never inject a passing header.
            context = browser.new_context(**p.devices['iPhone 15'],ignore_https_errors=True)
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto(self.app.origin)
            page.fill('#password', self.password)
            page.click('button')
            try:
                page.wait_for_selector('#sync', timeout=5000)
            except Exception:
                self.fail('Browser sign-in did not finish: '+page.url+' '+page.locator('body').inner_text()[:300])
            self.assertEqual(errors, [])
            expect(page.locator('#sync')).to_contain_text('1 jobs', timeout=10000)
            for view in ('board', 'list', 'contacts', 'search', 'review', 'overview'):
                page.click(f'.seg [data-v="{view}"]')
            self.assertEqual(errors, [])
            self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), 394)
            lock = self.book.with_name('~$' + self.book.name)
            lock.touch()
            # Exercise the PC adapter and pending banner over the real HTTPS connection.
            page.evaluate("() => post('/api/update',{id:D.jobs[0]._id,sheet:D.jobs[0]._sheet,note:'Phone queued note'})")
            expect(page.locator('#pc-saves')).to_contain_text('Waiting for Excel')
            self.assertEqual(self.app.queue.recent()[0]['status'],'waiting')
            lock.unlink()
            self.app.queue.process_one()
            page.evaluate('() => pcWrites()')
            expect(page.locator('#pc-saves')).to_contain_text('Saved to your spreadsheet')
            wb = openpyxl.load_workbook(self.book)
            self.assertEqual(wb.active.cell(2,6).value,'Phone queued note')
            wb.close()
            # Entire UI path uses a fake provider and fictional evidence, never a live call.
            self.app.ai.bank_loader=lambda:{'rules':'Fictional only','entries':{'E-999':{'level':'stated','text':'Fictional skill'}}}
            def fake_runner(prompt,kind,folder,images):
                if kind=='analyze':return {'is_job_posting':True,'readable':True,'company':'Example Company','role':'Example Role','link':'','posting_text':'',
                                          'score':3.5,'verdict':'CONSIDER','summary':'Fictional result only','location_ok':'unclear','matches':[],'gaps':[],'flags':[]}
                return {'cv_markdown':'# Fictional CV\nFictional skill.','sources':['E-999'],'flags':[],
                        'claims':[{'text':'Fictional skill.','evidence':['E-999']}]}
            self.app.ai.runner=fake_runner
            page.click('.seg [data-v="review"]')
            page.fill('#r-text','Fictional job posting with example requirements. '*8)
            page.click('#r-go')
            expect(page.locator('#r-op')).to_contain_text('Waiting for Codex')
            self.app.ai.process_one()
            expect(page.locator('#result')).to_contain_text('Fictional result only',timeout=10000)
            page.get_by_role('button',name='Create CV',exact=True).click()
            expect(page.locator('#result')).to_contain_text('Waiting for Codex')
            self.app.ai.process_one()
            expect(page.locator('#result')).to_contain_text('Fictional CV',timeout=10000)
            expect(page.locator('#result')).to_contain_text('awaiting separate truth review')
            page.get_by_role('button',name='Create cover letter',exact=True).click()
            expect(page.locator('#r-sent')).to_be_visible()
            self.assertEqual(len(self.app.ai.list_tasks()),2,'Opening sentiment must not create a letter')
            page.get_by_role('button', name='Sign out', exact=True).click()
            page.wait_for_selector('#password')
            browser.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
