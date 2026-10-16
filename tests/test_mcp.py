import json
import os
import subprocess
import sys
import unittest

class MCPTests(unittest.TestCase):
    def test_stdio_protocol(self):
        p=subprocess.Popen([sys.executable,'-m','poker_spot.mcp_server'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,env={**os.environ,'OPENBLAS_NUM_THREADS':'1'})
        def call(req):
            p.stdin.write(json.dumps(req)+'\n');p.stdin.flush()
            return json.loads(p.stdout.readline())
        try:
            r=call({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18'}})
            self.assertEqual(r['result']['serverInfo']['name'],'poker-spot-local')
            r=call({'jsonrpc':'2.0','id':2,'method':'tools/list'})
            self.assertEqual(r['result']['tools'][0]['name'],'solve_river')
            r=call({'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'solve_river','arguments':{
                'board':'2c,3d,4h,8s,9c','oop_range':'AsAd','ip_range':'KhQd',
                'pot':100,'stack':100,'bet_sizes':[1.0],'iterations':100,'oop_hand':'AsAd'}}})
            self.assertFalse(r['result']['isError'])
            self.assertIn('oop',r['result']['structuredContent']['hands'])
            r=call({'jsonrpc':'2.0','id':4,'method':'tools/call','params':{'name':'solve_river','arguments':{'board':'bad'}}})
            self.assertTrue(r['result']['isError'])
        finally:
            p.terminate();p.communicate(timeout=3)

if __name__=='__main__':unittest.main()
