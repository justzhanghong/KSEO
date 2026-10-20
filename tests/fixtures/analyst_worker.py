"""确定性 CPU 诊断 fixture；不调用 LLM，不接受 measured。"""
import os
from pathlib import Path
from kseo.util import read_json, write_json

if os.environ.get('KSEO_MODE') != 'synthetic':
    raise SystemExit('fixture only accepts synthetic')
request = read_json(Path(os.environ['KSEO_ANALYST_REQUEST']))
assert Path(request['inputs']['evidence']['trial_dir']).is_dir()
assert request['inputs']['evidence']['context']['backend']=='synthetic'
assert request['inputs']['evidence']['remaining_seconds'] > 0
rows = [{'hotspot_id':r['id'], 'lane':'kernel' if r['kind']=='kernel' else 'scheduling',
         'evidence':['inputs.profile.hotspots.'+r['id']], 'hypothesis':'CPU fixture routing check'}
        for r in request['inputs']['profile']['hotspots']]
write_json(Path(os.environ['KSEO_ANALYST_OUTPUT']), {'schema_version':1,'input_sha256':request['input_sha256'],'ranked_hypotheses':rows})
