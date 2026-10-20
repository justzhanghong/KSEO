import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from kseo.aihub import BASE, Client, read_token
from kseo.util import KSEOError, read_json


class AIHubTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.calls=[];self.remote={};self.fail_create=False
        outer=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def handle_request(self):
                body=self.rfile.read(int(self.headers.get('Content-Length','0')))
                value=json.loads(body) if body else None
                outer.calls.append((self.command,self.path,self.headers.get('Authorization'),value))
                if self.command=='POST' and self.path==BASE+'/trainings':
                    if outer.fail_create:
                        self.send_response(503);self.end_headers();return
                    outer.remote={**value,'id':42};data={'id':42}
                elif self.command=='GET' and self.path==BASE+'/trainings/42':data=outer.remote
                elif self.command=='POST' and self.path==BASE+'/trainings/42/stop':data={}
                elif self.path==BASE+'/storages':data=[]
                else:self.send_response(404);self.end_headers();return
                self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
                self.wfile.write(json.dumps({'code':0,'data':data}).encode())
            do_GET=handle_request
            do_POST=handle_request
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(thread.join,2);self.addCleanup(server.shutdown)
        self.client=Client('http://127.0.0.1:'+str(server.server_port),'synthetic-test-token')
        self.kw={'owner':'run/trial','ledger':self.root/'ledger.json','cluster_id':7,'max_gpus':8,'max_nodes':1,'gpus_per_sku':1}
        self.payload={'sku_cnt':4,'instances':1,'virtual_cluster_id':7,'image':'example:baseline','command':'example'}

    def test_real_http_protocol_idempotent_create_owned_stop(self):
        self.assertEqual(self.client.launch(self.payload,**self.kw),42)
        self.assertEqual(self.client.launch(self.payload,**self.kw),42)
        self.assertEqual(sum(c[0]=='POST' and c[1]==BASE+'/trainings' for c in self.calls),1)
        self.client.stop(self.kw['ledger'],'run/trial');self.client.stop(self.kw['ledger'],'run/trial')
        self.assertEqual(sum(c[1].endswith('/stop') for c in self.calls),1)
        self.assertTrue(all(c[2]=='Bearer synthetic-test-token' for c in self.calls))
        self.assertNotIn('token',self.kw['ledger'].read_text())

    def test_limits_checked_before_allocation(self):
        self.payload['sku_cnt']=16
        with self.assertRaises(KSEOError):self.client.launch(self.payload,**self.kw)
        self.assertEqual(self.calls,[])

    def test_unknown_create_not_retried_and_no_body_leak(self):
        self.fail_create=True
        with self.assertRaises(KSEOError):self.client.launch(self.payload,**self.kw)
        self.assertEqual(read_json(self.kw['ledger'])['state'],'UNKNOWN')
        with self.assertRaises(KSEOError):self.client.launch(self.payload,**self.kw)
        self.assertEqual(len(self.calls),1)

    def test_foreign_owner_cannot_be_stopped(self):
        self.client.launch(self.payload,**self.kw);self.remote['description']='another owner'
        with self.assertRaises(KSEOError):self.client.stop(self.kw['ledger'],'run/trial')
        self.assertFalse(any(c[1].endswith('/stop') for c in self.calls))

    def test_read_token_formats_and_invalid_url(self):
        path=self.root/'token.json';path.write_text(json.dumps({'token':'synthetic-test-token'}))
        self.assertEqual(read_token(path),'synthetic-test-token')
        with self.assertRaises(KSEOError):Client('https://u:p@example.com','token')
