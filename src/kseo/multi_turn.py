"""相同最终产物的 KVOffloading OFF/ON 配对验收，全部冻结请求参与均值。"""
from fractions import Fraction
from .util import KSEOError, digest, finite, positive_int


def validate_policy(policy: dict) -> None:
    if policy.get('include_first_turn') is not True:
        raise KSEOError('整体平均 TTFT 必须包含冻结集合的第一轮，不能静默丢掉第一轮')
    minimum = finite(policy.get('minimum_reduction'), 'minimum_reduction')
    if not 0 <= minimum < 1 or policy.get('comparison_op', '>=') not in ('>=', '>'):
        raise KSEOError('多轮收益线必须在 [0,1)，比较符为 >= 或 >')
    if not isinstance(policy.get('parameter_key', 'kv_offloading'), str):
        raise KSEOError('必须冻结 KVOffloading 参数名')
    manifest = policy.get('manifest', [])
    if not manifest:
        raise KSEOError('多轮验收必须先冻结完整配对 manifest')
    ids, turns = set(), {}
    for row in manifest:
        rid, sid = row.get('request_id'), row.get('session_id')
        if not isinstance(rid, str) or not rid or rid in ids or not isinstance(sid, str) or not sid:
            raise KSEOError('多轮 request_id/session_id 缺失或重复')
        ids.add(rid)
        turn = positive_int(row.get('turn'), 'turn', zero=True)
        if turn in turns.setdefault(sid, set()):
            raise KSEOError('同一 session 的 turn 不能重复')
        turns[sid].add(turn)
        for key in ('input_tokens', 'output_tokens', 'concurrency'):
            positive_int(row.get(key), key)
        if row['output_tokens'] < 2:
            raise KSEOError('多轮输出至少两个 token')
        from .final_accuracy import _sha
        _sha(row.get('prompt_sha256'), 'multi_turn.prompt_sha256')
    for sequence in turns.values():
        if len(sequence) < 2 or sequence != set(range(len(sequence))):
            raise KSEOError('多轮 session 必须从第 0 轮开始，至少两轮，且连续完整')


def evaluate(payload: dict, directory, policy: dict, identity: dict) -> dict:
    from .validation import artifact, jsonl
    arms = payload.get('multi_turn_runs', {})
    if set(arms) != {'off', 'on'}:
        raise KSEOError('多轮验收必须同时包含 OFF/ON 原始运行')
    parameter_key = policy.get('parameter_key', 'kv_offloading')
    parameters, means, failed, evidence = {}, {}, {}, {}
    manifest = policy['manifest']
    for name in ('off', 'on'):
        arm = arms[name]
        if arm.get('artifact_identity') != identity:
            raise KSEOError('多轮两组必须使用同一最终源码、镜像、模型和合同身份')
        params = arm.get('parameters')
        if not isinstance(params, dict) or params.get(parameter_key) is not (name == 'on'):
            raise KSEOError('必须明确 OFF/ON 开关及全部实际参数')
        parameters[name] = {k: v for k, v in params.items() if k != parameter_key}
        if name == 'on' and digest(params) != identity['parameters_sha256']:
            raise KSEOError('ON 组必须对应最终候选的冻结参数')
        rows = jsonl(artifact(arm, 'requests_file', directory))
        if [r.get('request_id') for r in rows] != [r['request_id'] for r in manifest]:
            raise KSEOError('配对请求必须与冻结清单的全部 ID 和顺序一致')
        values = []; failures = 0; read = write = 0
        for actual, expected in zip(rows, manifest):
            positive_int(actual.get('turn'), 'actual.turn', zero=True)
            positive_int(actual.get('concurrency'), 'actual.concurrency')
            positive_int(actual.get('input_tokens'), 'actual.input_tokens')
            for key in ('session_id', 'turn', 'concurrency', 'prompt_sha256', 'input_tokens'):
                if actual.get(key) != expected[key]:
                    raise KSEOError('多轮实际请求与冻结 prompt/轮次/并发/输入长度不符')
            if actual.get('status') not in ('completed', 'failed'):
                raise KSEOError('多轮请求必须保存真实终态')
            if actual['status'] == 'failed':
                failures += 1
                continue
            if actual.get('output_tokens') != expected['output_tokens']:
                raise KSEOError('多轮生成总 token 数必须包含 reasoning 并符合合同')
            value = finite(actual.get('ttft_ms'), 'multi_turn.ttft_ms')
            if value <= 0:
                raise KSEOError('配对 TTFT 必须为正')
            values.append(Fraction(str(value)))
            positive_int(actual.get('cache_read_tokens'), 'cache_read_tokens', zero=True)
            for key in ('offload_read_bytes', 'offload_write_bytes'):
                positive_int(actual.get(key), key, zero=True)
            read += actual['offload_read_bytes']; write += actual['offload_write_bytes']
            if name == 'off' and (actual['offload_read_bytes'] or actual['offload_write_bytes']):
                raise KSEOError('OFF 组不能出现 offload 读写')
        failed[name] = failures
        # 有失败时不使用剩下的成功请求伪造完整集合均值。
        means[name] = sum(values, Fraction(0)) / len(rows) if not failures else None
        evidence[name] = {'read_bytes': read, 'write_bytes': write}
    if parameters['off'] != parameters['on']:
        raise KSEOError('OFF/ON 除冻结开关外不得改变 GPU/拓扑、配置或其他参数')
    valid = not any(failed.values()) and evidence['on']['read_bytes'] > 0 and evidence['on']['write_bytes'] > 0
    reduction = 1 - means['on'] / means['off'] if valid else None
    threshold = Fraction(str(policy['minimum_reduction']))
    passed = valid and (reduction >= threshold if policy.get('comparison_op', '>=') == '>=' else reduction > threshold)
    return {'samples_per_arm': len(manifest), 'off_mean_ttft_ms': float(means['off']) if means['off'] is not None else None,
            'on_mean_ttft_ms': float(means['on']) if means['on'] is not None else None,
            'reduction': float(reduction) if reduction is not None else None, 'failed_requests': failed,
            'offload_evidence': evidence, 'passed': bool(passed), 'statistic': 'pooled_request_mean_ttft_including_first_turn'}
