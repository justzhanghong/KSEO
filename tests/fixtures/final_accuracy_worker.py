"""仅用于 CPU synthetic 控制流检查，不是三个真实 benchmark 的执行器。"""
import json
import os
from pathlib import Path
from kseo.util import digest, file_digest, write_json
from kseo.final_accuracy import hash_text, SUITES


def policy():
    suites=[]
    for suite in SUITES:
        manifest=[]
        for i in range(2):
            row={'sample_id':f'{suite}-{i}','prompt_sha256':hash_text(f'prompt-{suite}-{i}')}
            row.update({'gold':'AB'[i]} if suite=='longbench_v2' else {'test_payload_sha256':hash_text(f'tests-{suite}-{i}')})
            manifest.append(row)
        suites.append({'id':suite,'dataset_id':'synthetic-'+suite,'dataset_sha256':hash_text('synthetic dataset '+suite),'evaluator_sha256':hash_text('synthetic evaluator'),'extractor_sha256':hash_text('synthetic extractor'),'expected_samples':2,'min_score':1.0,'max_failed_requests':0,'manifest':manifest,'generation':{'thinking':'synthetic','first_max_output_tokens':16,'context_limit':64,'retry_policy':'empty_length_once'},**({'choice_regex':'^([A-D])$'} if suite=='longbench_v2' else {})})
    return {'suites':suites}


def write_outputs(directory, contract=None):
    contract=contract or policy();directory.mkdir(parents=True,exist_ok=True);outputs=[]
    for suite in contract['suites']:
        attempts=[];samples=[]
        for row in suite['manifest']:
            content=row.get('gold','synthetic code');aid=row['sample_id']+'-attempt1'
            attempts.append({'sample_id':row['sample_id'],'attempt_id':aid,'prompt_sha256':row['prompt_sha256'],'final_content':content,'thinking':'synthetic','max_output_tokens':16,'prompt_tokens':8,'finish_reason':'stop'})
            score={'sample_id':row['sample_id'],'attempt_id':aid,'final_content_sha256':hash_text(content),'status':'completed'}
            if suite['id']=='longbench_v2':score['predicted_choice']=content
            else:
                score.update(test_payload_sha256=row['test_payload_sha256'],test_results=[True])
                if suite['id']=='rtlbench':score.update(compile_exit_code=0,simulation_exit_code=0,success_marker=True,failure_marker=False)
            samples.append(score)
        output={'id':suite['id'],**{k:suite[k] for k in ('dataset_sha256','evaluator_sha256','extractor_sha256')},'generation_policy_sha256':digest(suite['generation'])}
        for kind,rows in [('samples',samples),('attempts',attempts)]:
            p=directory/(suite['id']+'-'+kind+'.jsonl');p.write_text(''.join(json.dumps(r)+'\n' for r in rows));output[kind+'_file']=p.name;output[kind+'_file_sha256']=file_digest(p)
        p=directory/(suite['id']+'-review.json');write_json(p,{'status':'PASS','manifest_sha256':digest(suite['manifest']),'unresolved_sample_ids':[],'scope':'synthetic control-flow fixture'})
        output.update(validity_review_file=p.name,validity_review_file_sha256=file_digest(p));outputs.append(output)
    return {'benchmarks':outputs}


if __name__=='__main__':
    if os.environ.get('KSEO_MODE')!='synthetic':raise SystemExit('CPU fixture refuses real benchmark mode')
    from kseo.adapter import emit
    root=Path(os.environ['KSEO_RUN_DIR']);config=json.loads((root/'task.json').read_text())
    result=write_outputs(Path(os.environ['KSEO_STAGE_DIR']),config['validation']['final_accuracy'])
    emit(benchmarks=result['benchmarks'])
