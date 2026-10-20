"""将外层 Agent 的简要输入规范化；自动发现、冻结合同和真实运行各有明确状态。"""
from __future__ import annotations
import copy
import json
import re
from importlib.resources import files
from pathlib import Path
from urllib.parse import urlsplit
from .util import KSEOError, digest, file_digest, read_json, write_json, positive_int, finite


def defaults():
    return json.loads(files('kseo').joinpath('data/defaults.json').read_text(encoding='utf-8'))


def merge(base, overrides):
    result = copy.deepcopy(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def normalize(brief):
    if not isinstance(brief, dict) or brief.get('schema_version') != 1:
        raise KSEOError('简要任务输入要求 schema_version=1')
    if not brief.get('model_path') or not brief.get('workdir') or not brief.get('source'):
        raise KSEOError('需要 model_path、source 和 workdir；其余使用统一默认策略')
    result = copy.deepcopy(brief)
    result['name'] = result.get('name') or re.sub(r'[^A-Za-z0-9_-]', '-', Path(result['model_path']).name).lower()
    if not re.fullmatch(r'[A-Za-z0-9_-]+', result['name']):
        raise KSEOError('name 必须由英文、数字、下划线或连字符组成')
    for key in ('model_path', 'workdir'):
        if not Path(result[key]).is_absolute():
            raise KSEOError(f'{key} 必须使用明确的绝对路径')
    source = result['source']
    if isinstance(source, str):
        if source.startswith(('https://', 'http://')):
            if '/tree/' in source:
                url, ref = source.split('/tree/', 1)
                source = {'url': url.rstrip('/') + '.git', 'ref': ref}
            else:
                source = {'url': source, 'ref': None}
        else:
            source = {'path': source}
    if not isinstance(source,dict):raise KSEOError('source 需要路径、Git URL 或对象')
    result['source'] = source
    for url in [source.get('url'), result.get('platform', {}).get('url')]:
        if url and (urlsplit(url).username or urlsplit(url).password):
            raise KSEOError('URL 不允许包含 credentials，请使用外部凭据引用')
    result['policy'] = merge(defaults(), result.get('policy', {}))
    policy = result['policy']
    targets = brief.get('targets', {})
    if not isinstance(targets.get('speed'), dict):
        raise KSEOError('targets.speed 需要当前任务的长度、输出、并发与速度目标；不沿用示例数值')
    policy['speed'] = merge(policy['speed'], targets['speed'])
    policy['accuracy']['min_scores'] = copy.deepcopy(targets.get('accuracy', {}))
    required_scores = ('gsm8k','rtlbench','longbench_v2','livecodebench_v1')
    for suite in required_scores:
        if suite not in policy['accuracy']['min_scores']:
            raise KSEOError('缺少当前任务精度线：' + suite + '；不得沿用其他模型分数')
        value = finite(policy['accuracy']['min_scores'][suite], suite)
        if not 0 <= value <= 1:raise KSEOError('精度线必须为 [0,1]')
    if targets.get('multi_turn') is not None:
        policy['multi_turn'] = merge(policy['multi_turn'], {'enabled':True, **targets['multi_turn']})
    speed = policy['speed']
    for key in ('input_tokens','output_tokens','concurrencies','ttft_ms','tpot_ms'):
        if key not in speed:raise KSEOError('缺少当前任务 speed.' + key)
    mode = targets.get('thinking', speed.get('thinking','model_default'))
    if not isinstance(mode,str) or not mode.strip():raise KSEOError('thinking 需要明确字符串或 model_default')
    speed['thinking'] = mode
    policy['accuracy']['generation']['thinking'] = mode

    for key in ('input_tokens', 'output_tokens', 'waves_per_concurrency'):
        positive_int(speed[key], 'speed.' + key)
    if speed['output_tokens'] < 2 or speed['output_token_basis'] != 'reasoning_plus_final':
        raise KSEOError('测速输出总量包含 reasoning，TPOT 至少需要两个 token')
    if not speed['concurrencies'] or len(set(speed['concurrencies'])) != len(speed['concurrencies']):
        raise KSEOError('并发列表不能为空或重复')
    for c in speed['concurrencies']:
        positive_int(c, 'concurrency')
    for key in ('ttft_ms','tpot_ms'):
        if finite(speed[key], key) <= 0:raise KSEOError('性能目标必须为正')
    explicit_stages = targets.get('milestones', targets['speed'].get('milestones'))
    target = [speed['ttft_ms'], speed['tpot_ms']]
    if explicit_stages is None:
        speed['milestones'] = [target]
    elif not explicit_stages or list(explicit_stages[-1]) != target:
        raise KSEOError('显式阶段列表的最后一项必须对应当前任务最终速度目标')
    else:
        speed['milestones'] = copy.deepcopy(explicit_stages)
    if speed['statistic'] not in ('mean', 'p95', 'max'):
        raise KSEOError('必须明确性能统计口径')
    for pair in speed['milestones']:
        if not isinstance(pair,(list,tuple)) or len(pair) != 2 or any(finite(x,'milestone') <= 0 for x in pair):
            raise KSEOError('阶段列表每项必须为正值 [TTFT_ms, TPOT_ms]')
    for before, after in zip(speed['milestones'],speed['milestones'][1:]):
        if after[0] > before[0] or after[1] > before[1]:raise KSEOError('阶段目标必须逐步收紧')
    for key in ('max_gpus', 'max_nodes'):
        if policy['resources'][key] is not None:positive_int(policy['resources'][key], key)
    if policy['multi_turn']['comparison_op'] not in ('>=', '>'):
        raise KSEOError('多轮下降线必须明确比较符')
    result['defaults_revision'] = defaults()['revision']
    result['defaults_sha256'] = digest(defaults())
    return result


def inspect_inputs(brief):
    """只读检查，不读取凭据内容、不启动 GPU、不把配置声明当运行验收。"""
    checks = []; discovered = {}
    def check(name, ok, detail):
        checks.append({'name': name, 'status': 'PASS' if ok else 'MISSING', 'detail': detail})
    model = Path(brief['model_path'])
    check('model_directory', model.is_dir(), '模型目录存在性')
    config = model / 'config.json'
    if config.is_file():
        value = read_json(config); text = value.get('text_config', value)
        discovered['model'] = {'config_sha256': file_digest(config), 'model_type': value.get('model_type'),
            'text_model_type': text.get('model_type'), 'architectures': value.get('architectures'),
            'quant_method': value.get('quantization_config', {}).get('quant_method'),
            'vision_declared': bool(value.get('vision_config')), 'declared_context_limit': text.get('max_position_embeddings'),
            'runtime_support': 'NOT_TESTED', 'weight_content_identity': 'NOT_FROZEN'}
        check('model_config', True, '仅读配置；实际上下文/Thinking/图文功能须由 baseline smoke 验证')
    else:
        check('model_config', False, '缺少可读的 config.json')
    src = brief['source']
    check('source_reference', bool(src.get('path') or (src.get('url') and src.get('ref'))), '本地源码或明确远端 ref；Agent 自动拉取并解析 commit')
    if src.get('path'):
        check('source_local_directory', Path(src['path']).is_dir(), '本地源码目录')
    check('base_image', bool(brief.get('base_image')), '用户提供基础镜像；Agent 再解析 digest，不猜测基础镜像')
    platform = brief.get('platform', {})
    check('platform', platform.get('kind') in ('aihub', 'commands', 'docker'), '需要实际平台类型')
    if platform.get('kind') == 'aihub':
        for key in ('url', 'cluster_id', 'docs_file', 'token_file'):
            present = bool(platform.get(key))
            if key.endswith('_file') and present:
                present = Path(platform[key]).is_file()
            check('aihub_' + key, present, '只验证引用存在；资源、权限及 API 由 Backend 探测')
    return {'status': 'READY_TO_BOOTSTRAP' if all(c['status'] == 'PASS' for c in checks) else 'NEEDS_INPUT_OR_ACCESS',
            'checks': checks, 'discovered': discovered, 'real_model_or_platform_checks_run': False}


def draft_task(brief):
    """具体命令、数据与原生 prompt 由 bootstrap 生成；草稿永远不可直接运行。"""
    from .datasets import load_dataset
    task = json.loads(files('kseo').joinpath('data/profile-a800.json').read_text())
    policy = brief['policy']; speed = policy['speed']
    task['name'] = brief['name']; task['draft'] = True
    task['inputs'].update(model=brief['model_path'], image='<Agent 解析用户基础镜像后的 digest>', base_image=brief.get('base_image'),
                          workload='workload.json', workload_sha256='<native tokenize 后冻结完整 workload>', model_revision='<权重内容清单 SHA256>')
    task['context'] = {'model_family': '<Agent 从架构和参考实现确定>', 'backend': 'vllm', 'capabilities': []}
    task['source'] = {'kind': 'git', 'path': str(Path(brief['workdir'])/'source'), 'revision': '<Agent 冻结 commit>'}
    task['parameters'] = {'kv_offloading': True} if policy['multi_turn']['enabled'] else {}
    task['optimizer'] = {'kind': 'pipeline', 'space': {}, 'max_config_trials': 8, 'allow_source_changes': True,
                         'final_reserve_seconds': policy['budget']['final_reserve_seconds'], 'min_relative_improvement': 0,
                         'require_equivalence_rationale': True}
    task['budget'] = {k:v for k,v in policy['budget'].items() if k not in ('final_reserve_seconds','gpu_hours_rule')}
    task['resources'] = {'gpu_count': policy['resources']['max_gpus'] or 0, 'keys': ['<Backend 解析实际资源租约>'],
                         'limits': policy['resources']}
    v = task['validation']; v['docker_artifacts'] = True; v['cases'] = []; performance = []
    for concurrency in speed['concurrencies']:
        cid = f'single_c{concurrency}'
        v['cases'].append({'id':cid,'requests':concurrency*speed['waves_per_concurrency'],'concurrency':concurrency,
                          'input_tokens':speed['input_tokens'],'output_tokens':speed['output_tokens'], 'cache_policy':'zero_read',
                          'output_token_basis':speed['output_token_basis'],'ttft_basis':speed['ttft_basis']})
        for metric in ('ttft_ms','tpot_ms'):
            performance.append({'name':f'{cid}_{metric}','stage':'benchmark', 'field':f'benchmark.cases.{cid}.{metric}.{speed["statistic"]}',
                                'op':'<','value':speed[metric]})
    v['gates'] = [g for g in v['gates'] if g['stage'] != 'benchmark' and g['field'] != 'preflight.runtime.gpu_arch'] + performance + [
        {'name':'测速请求不得失败','stage':'benchmark','field':'benchmark.failed_requests','op':'==','value':0,'always_required':True}]
    for gate in v['gates']:
        if gate['field'] == 'quality.accuracy':gate['value'] = policy['accuracy']['min_scores']['gsm8k']
    v['milestones'] = []
    for i, pair in enumerate(speed['milestones']):
        gates = [{**g, 'value':pair[0] if '.ttft_ms.' in g['field'] else pair[1]} for g in performance]
        v['milestones'].append({'name':f'stage_{i+1}', 'gates':gates})
    # 用户覆盖最终目标但没有相应覆盖阶段列表时仍保证最后阶段与最终目标一致。
    v['milestones'][-1]['gates'] = copy.deepcopy(performance)
    v['selection_metrics'] = [{'field':g['field'],'target':g['value']} for g in performance]
    v['objective'] = {'field':'benchmark.mean_goal_ratio','direction':'min'}
    v['quality_generation'] = {**policy['accuracy']['generation'],'context_limit':None}
    v['quality_manifest'] = []
    for suite in v['final_accuracy']['suites']:
        entry = load_dataset(suite['dataset_id'])
        suite.update(dataset_sha256=digest(entry), expected_samples=entry['expected_samples'],
                     min_score=policy['accuracy']['min_scores'][suite['id']], max_failed_requests=0,
                     generation={**policy['accuracy']['generation'],'context_limit':None},manifest=[])
    if policy['multi_turn']['enabled']:
        task['steps'].insert(-1, {'name':'multi_turn','command':['{python}','{config_dir}/adapters/project_multi_turn.py'], 'timeout_seconds':policy['budget']['max_wall_seconds']})
        v['multi_turn'] = {'include_first_turn':True, 'minimum_reduction':policy['multi_turn']['minimum_reduction'],
                           'comparison_op':policy['multi_turn']['comparison_op'],'parameter_key':'kv_offloading','manifest':[]}
        v['gates'].append({'name':'多轮整体平均TTFT收益','stage':'multi_turn','field':'multi_turn.passed','op':'==','value':True})
    task['defaults_policy'] = policy
    task['brief_binding'] = {'brief_sha256':digest(brief),'defaults_sha256':brief['defaults_sha256'], 'docker':policy['docker']}
    return task


def prepare(raw, output):
    if output.exists():
        raise KSEOError('prepare 输出目录已存在，拒绝覆盖')
    brief = normalize(raw); report = inspect_inputs(brief)
    output.mkdir(parents=True)
    write_json(output/'brief.json', brief)
    write_json(output/'readiness.json', report)
    write_json(output/'task.draft.json', draft_task(brief))
    request = {'schema_version':1, 'brief':brief, 'readiness':report, 'draft_task':'task.draft.json',
        'required_output':'task.json', 'instructions':[
            '你是当前外层 coding Agent。读取 KSEO 的 docs/agent-bootstrap.md，自动补齐可发现信息，除用户基础镜像/不可访问凭据外不重复提问。',
            '在搜索前完成 source intake、模型 bring-up、AIHub/Docker Backend 和真实验收器接入；从当前基础镜像构建，允许编辑更新 Docker。',
            '仅将真实探测身份与原始记录写入合同；模型配置的上限、能力声明不是实际验收。不要使用固定 checks=true、synthetic 数据或 NotImplemented 的 bridge 充当 measured。',
            '冻结 task.json 前补全所有有序 manifest、native prompt/token 身份、服务实际上下文和独立 evaluator；精度默认使用 context_remaining，不引入人为输出 cap。',
            '按 case 冻结缓存政策；多轮冻结全部历史消息做配对输入，不将两组各自产生的不同历史混为相同负载。',
            '仅在自身资源/预算限制内选择单机或 PD，实际 GPU 数写入 resources；不继承 A800 的硬件占位信息。',
            '执行 kseo doctor task.json --brief brief.json；READY_TO_PREFLIGHT 后执行真实 kseo run，不把静态 doctor 当作真实验收通过。',
            '全部文件、构建缓存、数据导出和日志写入 brief.workdir；凭据只保留外部引用，不进入 Git/镜像层/日志。',
            '最终产物须 fresh deploy，并完成同合同速度、多轮、精度、API、稳定性核验；镜像/源码/参数/数据各身份必须对应。'
        ]}
    write_json(output/'bootstrap-request.json', request)
    return report


def bind_check(task, brief):
    """防止 bootstrap 遗漏用户要求；最终仍由 measured preflight 验证实际身份。"""
    expected = draft_task(brief); v = task['validation']; ev = expected['validation']
    if task.get('brief_binding', {}).get('brief_sha256') != digest(brief):
        raise KSEOError('最终合同没有绑定相同的规范化 brief')
    if task['inputs']['model'] != brief['model_path'] or task['inputs'].get('base_image') != brief.get('base_image'):
        raise KSEOError('不得更换用户模型或基础镜像')
    for key in ('cases','milestones','selection_metrics','objective'):
        if v.get(key) != ev.get(key):
            raise KSEOError('任务遗漏或改变速度/阶段/计时要求：' + key)
    if v.get('docker_artifacts') is not True or task['optimizer'].get('require_equivalence_rationale') is not True:
        raise KSEOError('不得移除镜像身份核验或数学等价说明')
    actual = {(g['stage'],g['field'],g['op'],json.dumps(g['value'])) for g in v['gates']}
    for g in ev['gates']:
        if (g['stage'],g['field'],g['op'],json.dumps(g['value'])) not in actual:
            raise KSEOError('合同遗漏用户或默认硬门禁：' + g['name'])
    if len(v['final_accuracy']['suites']) != len(ev['final_accuracy']['suites']):
        raise KSEOError('不能遗漏最终精度数据集')
    for suite, wanted in zip(v['final_accuracy']['suites'], ev['final_accuracy']['suites']):
        for key in ('id','dataset_id','dataset_sha256','expected_samples','min_score','max_failed_requests'):
            if suite.get(key) != wanted[key]:raise KSEOError('最终精度改变本地数据/阈值：' + key)
        for key,value in brief['policy']['accuracy']['generation'].items():
            if suite['generation'].get(key) != value:raise KSEOError('精度生成策略改变：' + key)
    for key,value in brief['policy']['accuracy']['generation'].items():
        if v.get('quality_generation', {}).get(key) != value:
            raise KSEOError('GSM8K 生成策略改变：' + key)
    positive_int(task['resources']['gpu_count'], '实际 GPU 数')
    if brief['policy']['resources']['max_gpus'] is not None and task['resources']['gpu_count'] > brief['policy']['resources']['max_gpus']:
        raise KSEOError('实际 GPU 数超出上限')
    for key in ('max_wall_seconds','max_gpu_hours','max_trials'):
        limit = brief['policy']['budget'][key]
        if key == 'max_gpu_hours' and limit is None:limit = task['resources']['gpu_count'] * brief['policy']['budget']['max_wall_seconds'] / 3600
        if task['budget'][key] > limit:raise KSEOError('预算超出 brief：' + key)
    if brief['policy']['multi_turn']['enabled']:
        for key in ('minimum_reduction','comparison_op','include_first_turn','parameter_key'):
            if v.get('multi_turn',{}).get(key) != ev['multi_turn'][key]:raise KSEOError('多轮验收合同被改变')
    return True


def doctor(task_path, brief_path=None):
    from .config import load
    task = load(task_path)
    if brief_path:
        brief = read_json(brief_path)
        bind_check(task, brief)
    paths = []
    commands = []
    def collect(value):
        if isinstance(value,dict):
            if isinstance(value.get('command'),list):commands.append(value)
            for child in value.values():collect(child)
        elif isinstance(value,list):
            for child in value:collect(child)
    collect(task)
    for command in commands:
        for arg in command.get('command', []):
            if arg.endswith('.py') and '{source_dir}' not in arg:
                path = Path(arg.replace('{config_dir}',str(task_path.resolve().parent)).replace('{package_dir}',str(Path(__file__).parent)))
                if not path.is_absolute():path = task_path.resolve().parent/path
                if not path.is_file():raise KSEOError('缺少实际 adapter 文件：' + str(path))
                paths.append({'path':str(path),'sha256':file_digest(path)})
    return {'status':'READY_TO_PREFLIGHT','contract_sha256':digest(task),'direct_adapters':paths,
            'note':'静态合同与文件检查；实际平台权限、GPU、镜像、模型和服务仍须由 preflight/smoke 测量，不表示已通过优化验收。'}
