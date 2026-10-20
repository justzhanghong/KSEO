import copy
import json
import tempfile
import unittest
from pathlib import Path
from kseo.multi_turn import evaluate, validate_policy
from kseo.util import KSEOError, digest, file_digest


class MultiTurnTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.manifest=[{'request_id':str(i),'session_id':'s','turn':i,'input_tokens':100+i,'output_tokens':8,
                        'concurrency':1,'prompt_sha256':digest('prompt'+str(i))} for i in range(2)]
        self.policy={'include_first_turn':True,'minimum_reduction':.3,'comparison_op':'>=','manifest':self.manifest}
        self.identity={'parameters_sha256':digest({'kv_offloading':True,'tp':2})}
        self.rows={name:[{**r,'status':'completed','ttft_ms':ttft,'cache_read_tokens':0 if i==0 else 50,
                          'offload_read_bytes':100 if name=='on' and i else 0,'offload_write_bytes':100 if name=='on' else 0}
                         for i,(r,ttft) in enumerate(zip(self.manifest,values))]
                   for name,values in [('off',[100,900]),('on',[100,600])]}

    def run_eval(self):
        arms={}
        for name,rows in self.rows.items():
            path=self.root/(name+'.jsonl');path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
            arms[name]={'artifact_identity':copy.deepcopy(self.identity),'parameters':{'kv_offloading':name=='on','tp':2},
                        'requests_file':path.name,'requests_file_sha256':file_digest(path)}
        return evaluate({'multi_turn_runs':arms},self.root,self.policy,self.identity)

    def test_exact_thirty_percent_uses_pooled_mean_including_first_turn(self):
        validate_policy(self.policy);result=self.run_eval()
        self.assertTrue(result['passed']);self.assertEqual(result['reduction'],.3)
        self.assertEqual(result['off_mean_ttft_ms'],500)
        # 各请求降幅的均值只有 1/6；验收不能偷换该口径。
        self.policy['comparison_op']='>';self.assertFalse(self.run_eval()['passed'])

    def test_failed_request_cannot_be_discarded_from_mean(self):
        self.rows['on'][1]['status']='failed';result=self.run_eval()
        self.assertFalse(result['passed']);self.assertIsNone(result['on_mean_ttft_ms'])

    def test_missing_or_changed_prompt_rejected(self):
        self.rows['on'][1]['prompt_sha256']='a'*64
        with self.assertRaises(KSEOError):self.run_eval()
        self.rows['on'].pop()
        with self.assertRaises(KSEOError):self.run_eval()

    def test_offload_flag_alone_is_not_evidence(self):
        for row in self.rows['on']:row['offload_read_bytes']=row['offload_write_bytes']=0
        self.assertFalse(self.run_eval()['passed'])

    def test_first_turn_and_contiguous_manifest_required(self):
        self.policy['include_first_turn']=False
        with self.assertRaises(KSEOError):validate_policy(self.policy)
        self.policy['include_first_turn']=True;self.manifest[1]['turn']=3
        with self.assertRaises(KSEOError):validate_policy(self.policy)
