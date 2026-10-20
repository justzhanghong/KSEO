import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
import kseo

from kseo.cli import audit
from kseo.config import validate
from kseo.demo import task
from kseo.final_accuracy import evaluate, validate_policy, hash_text
from kseo.runner import Runner
from kseo.util import KSEOError, file_digest, read_json, write_json

HELPER=Path(__file__).parent/'fixtures/final_accuracy_worker.py'
spec=importlib.util.spec_from_file_location('final_accuracy_test_fixture',HELPER)
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)


class FinalAccuracyTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);self.policy=fixture.policy();self.payload=fixture.write_outputs(self.root,self.policy)

    def rows(self,index,key):
        out=self.payload['benchmarks'][index]
        return [json.loads(l) for l in (self.root/out[key+'_file']).read_text().splitlines()]

    def replace(self,index,key,rows):
        out=self.payload['benchmarks'][index];p=self.root/out[key+'_file']
        p.write_text(''.join(json.dumps(r)+'\n' for r in rows));out[key+'_file_sha256']=file_digest(p)

    def test_complete_three_suites_recomputed(self):
        validate_policy(self.policy,'synthetic')
        result=evaluate(self.payload,self.root,self.policy)
        self.assertTrue(result['passed']);self.assertEqual(len(result['benchmarks']),3)
        self.assertTrue(all(v['samples']==2 and v['score']==1 for v in result['benchmarks'].values()))

    def test_context_remaining_requires_full_native_budget_on_every_sample(self):
        for suite in self.policy['suites']:
            suite['generation'].pop('first_max_output_tokens')
            suite['generation'].update(output_limit='context_remaining',retry_policy='none')
            for row in suite['manifest']:row['prompt_tokens']=8
        validate_policy(self.policy,'synthetic')
        self.payload=fixture.write_outputs(self.root,self.policy)
        self.assertTrue(evaluate(self.payload,self.root,self.policy)['passed'])
        rows=self.rows(0,'attempts');rows[0]['max_output_tokens']=16;self.replace(0,'attempts',rows)
        with self.assertRaises(KSEOError):evaluate(self.payload,self.root,self.policy)

    def test_minus_one_minus_two_are_errors_not_true(self):
        rows=self.rows(2,'samples');rows[0]['test_results']=[-1,-2];self.replace(2,'samples',rows)
        result=evaluate(self.payload,self.root,self.policy)
        self.assertFalse(result['passed']);self.assertEqual(result['benchmarks']['livecodebench_v1']['score'],0.5)

    def test_integer_one_is_not_a_valid_boolean_pass(self):
        rows=self.rows(2,'samples');rows[0]['test_results']=[1];self.replace(2,'samples',rows)
        with self.assertRaises(KSEOError):evaluate(self.payload,self.root,self.policy)

    def test_rtl_zero_exit_without_success_marker_is_not_pass(self):
        rows=self.rows(0,'samples');rows[0]['success_marker']=False;self.replace(0,'samples',rows)
        self.assertFalse(evaluate(self.payload,self.root,self.policy)['passed'])

    def test_missing_samples_and_raw_hash_rejected(self):
        rows=self.rows(1,'samples');self.replace(1,'samples',rows[:1])
        with self.assertRaises(KSEOError):evaluate(self.payload,self.root,self.policy)
        self.payload=fixture.write_outputs(self.root,self.policy)
        p=self.root/self.payload['benchmarks'][0]['attempts_file'];p.write_text(p.read_text()+'\n')
        with self.assertRaises(KSEOError):evaluate(self.payload,self.root,self.policy)

    def test_evaluator_and_test_payload_identity_cannot_change(self):
        self.payload['benchmarks'][0]['evaluator_sha256']='a'*64
        with self.assertRaises(KSEOError):evaluate(self.payload,self.root,self.policy)
        self.payload=fixture.write_outputs(self.root,self.policy)
        rows=self.rows(2,'samples');rows[0]['test_payload_sha256']='b'*64;self.replace(2,'samples',rows)
        with self.assertRaises(KSEOError):evaluate(self.payload,self.root,self.policy)

    def test_nonempty_response_cannot_be_resampled(self):
        rows=self.rows(1,'attempts');extra=copy.deepcopy(rows[0]);extra['attempt_id']+='-retry';rows.insert(1,extra);self.replace(1,'attempts',rows)
        with self.assertRaises(KSEOError):evaluate(self.payload,self.root,self.policy)

    def test_empty_length_once_uses_exact_remaining_context(self):
        rows=self.rows(1,'attempts');extra=copy.deepcopy(rows[0]);extra['attempt_id']+='-retry';extra['max_output_tokens']=56
        rows[0]['final_content']='';rows[0]['finish_reason']='length';rows.insert(1,extra);self.replace(1,'attempts',rows)
        scores=self.rows(1,'samples');scores[0]['attempt_id']=extra['attempt_id'];self.replace(1,'samples',scores)
        self.assertTrue(evaluate(self.payload,self.root,self.policy)['passed'])
        rows[1]['max_output_tokens']=57;self.replace(1,'attempts',rows)
        with self.assertRaises(KSEOError):evaluate(self.payload,self.root,self.policy)

    def test_invalid_nonempty_choice_counts_wrong_without_retry(self):
        rows=self.rows(1,'attempts');rows[0]['final_content']='None of the above';self.replace(1,'attempts',rows)
        scores=self.rows(1,'samples');scores[0]['predicted_choice']=None;scores[0]['final_content_sha256']=hash_text(rows[0]['final_content']);self.replace(1,'samples',scores)
        result=evaluate(self.payload,self.root,self.policy)
        self.assertEqual(result['benchmarks']['longbench_v2']['score'],0.5)
        self.assertEqual(result['benchmarks']['longbench_v2']['failed_requests'],0)

    def test_choice_must_come_from_final_text(self):
        rows=self.rows(1,'samples');rows[0]['predicted_choice']='D';self.replace(1,'samples',rows)
        with self.assertRaises(KSEOError):evaluate(self.payload,self.root,self.policy)

    def test_unresolved_validity_does_not_pass_even_with_perfect_score(self):
        out=self.payload['benchmarks'][0];p=self.root/out['validity_review_file'];d=read_json(p);d['unresolved_sample_ids']=['rtlbench-0'];write_json(p,d);out['validity_review_file_sha256']=file_digest(p)
        result=evaluate(self.payload,self.root,self.policy)
        self.assertEqual(result['benchmarks']['rtlbench']['score'],1)
        self.assertFalse(result['passed'])

    def test_policy_requires_three_suites_and_explicit_thresholds(self):
        p=copy.deepcopy(self.policy);p['suites'].pop()
        with self.assertRaises(KSEOError):validate_policy(p,'synthetic')
        p=copy.deepcopy(self.policy);p['suites'][0]['min_score']=None
        with self.assertRaises(KSEOError):validate_policy(p,'synthetic')
        with self.assertRaises(KSEOError):validate_policy(self.policy,'measured')

    def test_measured_policy_uses_local_525_without_deduplication(self):
        from kseo.datasets import load_dataset
        from kseo.util import digest
        policy = copy.deepcopy(self.policy)
        for suite, name in zip(policy['suites'], ('rtlbench-160', 'longbench-v2', 'livecodebench-v1')):
            entry = load_dataset(name)
            suite.update(dataset_id=name, dataset_sha256=digest(entry), expected_samples=entry['expected_samples'])
            suite['manifest'] = []
            for sample_id in entry['ordered_sample_ids']:
                row = {'sample_id': sample_id, 'prompt_sha256': 'a' * 64}
                if suite['id'] == 'longbench_v2':
                    row['gold'] = entry['gold_answers'][sample_id]
                else:
                    row['test_payload_sha256'] = 'b' * 64
                suite['manifest'].append(row)
        validate_policy(policy, 'measured')
        self.assertEqual(policy['suites'][1]['expected_samples'], 525)
        replaced = copy.deepcopy(policy)
        replaced['suites'][1]['expected_samples'] = 503
        replaced['suites'][1]['manifest'] = replaced['suites'][1]['manifest'][:503]
        with self.assertRaises(KSEOError):
            validate_policy(replaced, 'measured')
        changed_gold = copy.deepcopy(policy)
        row = changed_gold['suites'][1]['manifest'][0]
        row['gold'] = 'D' if row['gold'] != 'D' else 'A'
        with self.assertRaises(KSEOError):
            validate_policy(changed_gold, 'measured')

    def test_stage_runs_only_after_optimization_and_final_failure_blocks_completion(self):
        for reject in (False,True):
            config=task();config['budget']['max_trials']=1
            if reject:config_policy=copy.deepcopy(self.policy);config_policy['suites'][0]['min_score']=1
            else:config_policy=copy.deepcopy(self.policy)
            if reject:config_policy['suites'][0]['manifest'][0]['prompt_sha256']='c'*64
            # Make a deterministic wrong answer by changing the frozen gold while the worker emits A/B.
            if reject:
                script=self.root/'reject.py'
                script.write_text(HELPER.read_text().replace("content=row.get('gold','synthetic code')", "content='synthetic code' if suite['id']!='longbench_v2' else 'D'"))
            else:script=HELPER
            config['steps'].append({'name':'final_accuracy','command':['{python}',str(script)],'timeout_seconds':20,
                                    'env':{'PYTHONPATH':str(Path(kseo.__file__).resolve().parents[1])}})
            config['validation']['final_accuracy']=config_policy
            config['validation']['gates'].append({'name':'三项最终精度','stage':'final_accuracy','field':'final_accuracy.passed','op':'==','value':True})
            path=self.root/('task-reject.json' if reject else 'task-ok.json');write_json(path,config)
            directory=self.root/('reject' if reject else 'ok');state=Runner(directory).run(path)
            self.assertEqual(state['status'],'FINAL_VALIDATION_FAILED' if reject else 'COMPLETED')
            self.assertNotIn('final_accuracy',state['trials'][0]['results'])
            self.assertIn('final_accuracy',state['trials'][-1]['results'])
            trial_dir = directory/state['trials'][-1]['directory']
            self.assertEqual(audit(path,trial_dir)['pass'],not reject)
            # The audit must not trust a changed phase to skip the final-only gate.
            identity = read_json(trial_dir/'identity.json')
            identity['phase'] = 'candidate'
            write_json(trial_dir/'identity.json', identity)
            with self.assertRaises(KSEOError):
                audit(path, trial_dir)
