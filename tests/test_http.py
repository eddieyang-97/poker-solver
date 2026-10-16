import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from poker_spot.http_server import app

class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.patch = patch.dict(os.environ, {'POKER_MCP_TOKEN': 'test-secret','POKER_ALLOWED_ORIGINS':'https://chatgpt.com'})
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def send(self, message, token='test-secret', origin=None):
        headers={'Authorization':f'Bearer {token}', 'Content-Type':'application/json'}
        if origin:headers['Origin']=origin
        return self.client.post('/mcp',json=message,headers=headers)

    def test_health_requires_configuration(self):
        self.assertEqual(self.client.get('/health').status_code, 200)
        with patch.dict(os.environ, {'POKER_MCP_TOKEN':''}):
            self.assertEqual(self.client.get('/health').status_code, 503)

    def test_authentication(self):
        body={'jsonrpc':'2.0','id':1,'method':'tools/list'}
        self.assertEqual(self.send(body,token='wrong').status_code, 401)
        self.assertEqual(self.send(body,origin='https://not-allowed.example').status_code,403)
        self.assertEqual(self.send(body,origin='https://chatgpt.com').status_code,200)

    def test_protocol(self):
        r=self.send({'jsonrpc':'2.0','id':1,'method':'initialize',
                     'params':{'protocolVersion':'2025-06-18'}})
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.json()['result']['serverInfo']['name'],'poker-spot-local')
        r=self.send({'jsonrpc':'2.0','id':2,'method':'tools/list'})
        self.assertEqual(len(r.json()['result']['tools']),2)
        r=self.send({'jsonrpc':'2.0','method':'notifications/initialized'})
        self.assertEqual(r.status_code,202)

    def test_calculation(self):
        req={'jsonrpc':'2.0','id':3,'method':'tools/call','params':{
            'name':'evaluate_river_call','arguments':{
            'board':'Ks,9s,5h,Td,Ts','hero_hand':'KdQd',
            'villain_betting_range':'AsJh','pot':505,'bet':450}}}
        out=self.send(req).json()['result']['structuredContent']
        self.assertEqual(out['best_action_given_range'],'call')
        self.assertAlmostEqual(out['caller_pot_odds'],450/1405,places=5)

    def test_solve_cap(self):
        req={'jsonrpc':'2.0','id':4,'method':'tools/call','params':{
            'name':'solve_river','arguments':{'board':'2c,3d,4h,8s,9c',
            'oop_range':'AA','ip_range':'KK','pot':100,'stack':100,'iterations':10000}}}
        result=self.send(req).json()['result']
        self.assertTrue(result['isError'])
        self.assertIn('iterations',result['content'][0]['text'])

if __name__=='__main__':unittest.main()
