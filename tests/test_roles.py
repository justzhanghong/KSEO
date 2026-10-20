import copy
import tempfile
import unittest
import kseo
from pathlib import Path
from kseo import roles, optimizer
from kseo.demo import task
from kseo.profiling import normalize, route
from kseo.runner import Runner
from kseo.util import KSEOError, write_json


class RolesTests(unittest.TestCase):
    def request(self):
        profile=normalize({'scope':'critical_path','hotspots':[
            {'id':'kernel','kind':'kernel','share':.5,'achievable_speedup':2,'editable':True},
            {'id':'wait','kind':'host','share':.5,'achievable_speedup':1.5}]})
        return roles.diagnosis_request(profile,{'source_revision':'a'}, {}, {'gates':[]}, set())

    def output(self, request):
        return {'schema_version':1,'input_sha256':request['input_sha256'],'ranked_hypotheses':[
            {'hotspot_id':'wait','lane':'scheduling','evidence':['trace:wait'],'hypothesis':'reduce host waiting'}]}

    def test_diagnosis_is_bound_and_cannot_invent_hotspots_or_lanes(self):
        req=self.request();out=self.output(req)
        self.assertEqual(len(roles.validate_diagnosis(out,req)),1)
        for change in ({'hotspot_id':'imaginary'},{'lane':'kernel'},{'evidence':[]}):
            bad=copy.deepcopy(out);bad['ranked_hypotheses'][0].update(change)
            with self.assertRaises(KSEOError):roles.validate_diagnosis(bad,req)
        out['input_sha256']='0'*64
        with self.assertRaises(KSEOError):roles.validate_diagnosis(out,req)

    def test_system_still_enforces_eligibility_after_analyst_ranking(self):
        profile=self.request()['inputs']['profile']
        self.assertIsNone(route(profile,{'kernel'},set(),'r',priority=['wait']))
        self.assertIsNone(route(profile,{'kernel'},set(),'r',priority=['kernel'],min_gain=.3))

    def test_pipeline_executes_bound_analyst_as_separate_workflow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);config=task(pipeline=True)
            config['optimizer']['analyst']={'command':['{python}',str(Path(__file__).parent/'fixtures/analyst_worker.py')],
                                             'env':{'PYTHONPATH':str(Path(kseo.__file__).resolve().parent.parent)}}
            config['optimizer']['max_cycles']=24
            path=root/'task.json';write_json(path,config)
            state=Runner(root/'run').run(path)
            self.assertEqual(state['status'],'COMPLETED',state.get('error'))
            self.assertTrue(any(a['lane']=='analysis' and a['status']=='DIAGNOSED' for a in state['pipeline']['attempts']))
            self.assertEqual(state['trials'][0]['acceptance_role']['role'],'validator')
            for a in state['pipeline']['attempts']:
                if a.get('hotspot'):
                    self.assertIn('analyst_diagnosis',a['hotspot'])

    def test_roles_do_not_claim_os_sandbox_or_llm_validator(self):
        value=roles.catalog()
        self.assertIn('OS sandbox',value['isolation'])
        self.assertEqual(set(value['roles']),{'analyst','developer','validator','system'})

    def test_developer_requires_equivalence_and_cannot_rewrite_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'source').mkdir();wrapper=root/'worker.py'
            config=task(agent=True);config['optimizer']['command']=['{python}',str(wrapper)]
            config['optimizer']['require_equivalence_rationale']=True
            preamble="import json,os\nfrom pathlib import Path\nr=Path(os.environ['KSEO_AGENT_REQUEST'])\np=Path(os.environ['KSEO_AGENT_PROPOSAL'])\n"
            proposal="p.write_text(json.dumps({'parameters':{'chunk_tokens':512},'hypothesis':'unchanged semantics'}))\n"
            wrapper.write_text(preamble+proposal)
            variables={'run_dir':str(root),'source_dir':str(root/'source'),'python':__import__('sys').executable}
            with self.assertRaises(KSEOError):optimizer.agent(config,{'trials':[]},root/'proposal',variables,{},20)
            wrapper.write_text(preamble+"r.write_text('{}')\np.write_text('{\"stop\":true}')\n")
            with self.assertRaises(KSEOError):optimizer.agent(config,{'trials':[]},root/'proposal',variables,{},20)
