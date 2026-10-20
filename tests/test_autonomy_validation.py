import copy
import json
import tempfile
import unittest
from pathlib import Path
from kseo import artifacts, milestones
from kseo.demo import task
from kseo.generation import output_budget, validate_generation
from kseo.runner import Runner
from kseo.util import KSEOError, digest, file_digest, write_json
from kseo.validation import gates, quality


class GenerationTests(unittest.TestCase):
    def test_context_remaining_has_no_manual_cap_or_retry(self):
        gen={'output_limit':'context_remaining','context_limit':131072,'thinking':'high','retry_policy':'none'}
        validate_generation(gen);self.assertEqual(output_budget(gen,72000),59072)
        for extra in ({'first_max_output_tokens':256},{'retry_policy':'empty_length_once'}):
            with self.assertRaises(KSEOError):validate_generation({**gen,**extra})
        with self.assertRaises(KSEOError):output_budget(gen,131072)

    def test_gsm_generation_budget_is_checked_against_frozen_native_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);gen={'output_limit':'context_remaining','context_limit':100,'thinking':'low','retry_policy':'none'}
            manifest=[{'sample_id':'1','prompt_sha256':'a'*64,'prompt_tokens':20}]
            policy={'quality_samples':1,'quality_manifest':manifest,'quality_generation':gen}
            row={**manifest[0],'max_output_tokens':80,'thinking':'low','generation_policy_sha256':digest(gen),'correct':True,'failed':False,'unparseable':False}
            def run():
                p=root/'quality.jsonl';p.write_text(json.dumps(row)+'\n')
                return quality({'samples_file':p.name,'samples_file_sha256':file_digest(p)},root,policy)
            self.assertEqual(run()['accuracy'],1)
            row['max_output_tokens']=16
            with self.assertRaises(KSEOError):run()


class ArtifactTests(unittest.TestCase):
    def test_candidate_image_changes_allowed_but_identity_and_fresh_instance_required(self):
        identity={'image':'base@sha256:'+'a'*64,'source_revision':'abc','parameters_sha256':'b'*64}
        image={'image':'candidate@sha256:'+'c'*64,'base_image':identity['image'],'source_revision':'abc','parameters_sha256':'b'*64}
        result={'build':{'runtime':{'artifact':image}},'deploy':{'runtime':{'artifact':image,'deployment_id':'new','fresh_deployment':True}},
                'benchmark':{'runtime':{'artifact':image,'deployment_id':'new'}}}
        self.assertEqual(artifacts.validate(result,identity,{'docker_artifacts':True},phase='final'),image)
        with self.assertRaises(KSEOError):artifacts.validate(result,identity,{'docker_artifacts':True},phase='final',previous_deployments=['new'])
        bad=copy.deepcopy(result);bad['benchmark']['runtime']['artifact']['source_revision']='other'
        with self.assertRaises(KSEOError):artifacts.validate(bad,identity,{'docker_artifacts':True})


class MilestoneTests(unittest.TestCase):
    def specification(self):
        config=task();policy=config['validation']
        performance=[g for g in policy['gates'] if g['stage']=='benchmark' and g['field']!='benchmark.failed_requests']
        for g in policy['gates']:
            if g['field']=='benchmark.failed_requests':g['always_required']=True
        policy['milestones']=[{'name':'first','gates':[{**g,'value':g['value']*2} for g in performance]},
                              {'name':'final','gates':copy.deepcopy(performance)}]
        return config

    def test_search_does_not_relax_correctness_or_final_gate(self):
        config=self.specification();policy=config['validation'];milestones.validate(policy)
        results={'benchmark':{'failed_requests':0}}
        self.assertTrue(all(g['pass'] for g in gates(results,policy,'benchmark',phase='candidate')))
        self.assertFalse(all(g['pass'] for g in gates(results,policy,'benchmark',phase='final')))
        results['benchmark']['failed_requests']=1
        self.assertFalse(all(g['pass'] for g in gates(results,policy,'benchmark',phase='candidate')))

    def test_correct_intermediate_candidates_preserved_but_unmet_target_cannot_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);config=self.specification();policy=config['validation']
            for gate in policy['gates']:
                if gate['stage']=='benchmark' and not gate.get('always_required'):gate['value']=.00001
            policy['milestones'][-1]['gates']=[copy.deepcopy(g) for g in policy['gates'] if g['stage']=='benchmark' and not g.get('always_required')]
            path=root/'task.json';write_json(path,config);state=Runner(root/'run').run(path)
            self.assertEqual(state['status'],'TARGETS_NOT_MET',state.get('error'))
            self.assertIsNotNone(state['best']);self.assertFalse(state['best']['final_performance_passed'])
            self.assertTrue(any(t['status']=='ACCEPTED' and t['phase']=='candidate' for t in state['trials']))
            self.assertFalse(any(t['phase']=='final' for t in state['trials']))
