import copy
import tempfile
import unittest
from pathlib import Path
from kseo import brief
from kseo.util import KSEOError, read_json, write_json


def sample(root, second=False):
    return {'schema_version':1,'model_path':str(root/('another-model' if second else 'model')),
            'source':'https://github.com/example/backend/tree/another-branch' if second else str(root/'source'),
            'workdir':str(root/'work'),'base_image':'example/backend:baseline','platform':{'kind':'docker'},
            'targets':{'speed':{'input_tokens':12000 if second else 4000,'output_tokens':512 if second else 128,
                               'concurrencies':[2,8] if second else [1,2], 'ttft_ms':4000 if second else 2000,'tpot_ms':20 if second else 12},
                       'thinking':'low' if second else 'high',
                       'accuracy':{'gsm8k':.8 if second else .9,'rtlbench':.2,'longbench_v2':.3,'livecodebench_v1':.4}}}


class BriefTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)

    def test_two_tasks_inherit_semantics_but_no_model_or_numeric_goals(self):
        for second in (False,True):
            raw=sample(self.root,second);norm=brief.normalize(raw);task=brief.draft_task(norm)
            case=task['validation']['cases'][0];target=raw['targets']['speed']
            self.assertEqual(case['input_tokens'],target['input_tokens'])
            self.assertEqual(case['output_tokens'],target['output_tokens'])
            self.assertEqual(case['concurrency'],target['concurrencies'][0])
            self.assertEqual(norm['policy']['accuracy']['generation']['thinking'],raw['targets']['thinking'])
            self.assertEqual(norm['policy']['speed']['output_token_basis'],'reasoning_plus_final')
            self.assertNotIn('gpu_arch',task['context']);self.assertEqual(task['resources']['gpu_count'],0)
            self.assertTrue(task['draft']);self.assertEqual(task['parameters'],{})
        self.assertEqual(brief.normalize(sample(self.root,True))['source']['ref'],'another-branch')
        d=brief.defaults();self.assertNotIn('input_tokens',d['speed']);self.assertNotIn('min_scores',d['accuracy'])

    def test_missing_targets_are_not_filled_with_previous_model_numbers(self):
        for section,key in (('speed','input_tokens'),('accuracy','gsm8k')):
            raw=sample(self.root);del raw['targets'][section][key]
            with self.assertRaises(KSEOError):brief.normalize(raw)

    def test_milestones_follow_task_and_reject_relaxation(self):
        raw=sample(self.root);raw['targets']['milestones']=[[4000,20],[2000,12]]
        self.assertEqual(len(brief.draft_task(brief.normalize(raw))['validation']['milestones']),2)
        raw['targets']['milestones']=[[1000,20],[2000,12]]
        with self.assertRaises(KSEOError):brief.normalize(raw)

    def test_prepare_is_readonly_discovery_not_gpu_acceptance(self):
        raw=sample(self.root);Path(raw['model_path']).mkdir();Path(raw['source']).mkdir()
        write_json(Path(raw['model_path'])/'config.json',{'model_type':'unseen','max_position_embeddings':65536})
        out=self.root/'prepared';report=brief.prepare(raw,out)
        self.assertEqual(report['status'],'READY_TO_BOOTSTRAP');self.assertFalse(report['real_model_or_platform_checks_run'])
        self.assertTrue(read_json(out/'task.draft.json')['draft'])
        raw.pop('base_image');self.assertEqual(brief.inspect_inputs(brief.normalize(raw))['status'],'NEEDS_INPUT_OR_ACCESS')
        with self.assertRaises(KSEOError):brief.prepare(raw,out)

    def test_bind_check_forbids_omission_and_budget_expansion(self):
        norm=brief.normalize(sample(self.root));task=brief.draft_task(norm)
        task['resources']['gpu_count']=4;task['budget']['max_gpu_hours']=96
        self.assertTrue(brief.bind_check(task,norm))
        for section,key,value in (('validation','docker_artifacts',False),('budget','max_gpu_hours',97)):
            bad=copy.deepcopy(task);bad[section][key]=value
            with self.assertRaises(KSEOError):brief.bind_check(bad,norm)
        task['validation']['final_accuracy']['suites'].pop()
        with self.assertRaises(KSEOError):brief.bind_check(task,norm)

    def test_multiturn_and_docker_defaults_are_explicit_and_overridable(self):
        raw=sample(self.root);raw['targets']['multi_turn']={}
        norm=brief.normalize(raw);task=brief.draft_task(norm)
        self.assertEqual(task['parameters'],{'kv_offloading':True})
        self.assertEqual(task['validation']['multi_turn']['minimum_reduction'],.3)
        self.assertEqual(task['validation']['multi_turn']['comparison_op'],'>=')
        self.assertTrue(norm['policy']['docker']['allow_update'])

    def test_credentials_in_urls_rejected(self):
        raw=sample(self.root);raw['source']='https://user:secret@example.com/repo'
        with self.assertRaises(KSEOError):brief.normalize(raw)
