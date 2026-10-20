"""阶段目标不修改最终合同；搜索保留正确且更优的中间候选。"""
from .util import KSEOError, finite, get_path


def enabled(config):
    return bool(config['validation'].get('milestones'))


def validate(policy):
    stages = policy.get('milestones')
    if stages is None:
        return
    if not isinstance(stages, list) or not stages:
        raise KSEOError('milestones 必须为非空有序列表')
    names = set()
    for stage in stages:
        if not stage.get('name') or stage['name'] in names or not stage.get('gates'):
            raise KSEOError('阶段目标需要唯一名称及完整 gates')
        names.add(stage['name'])
        for gate in stage['gates']:
            if not gate.get('field', '').startswith('benchmark.') or gate.get('op') not in ('<', '<=', '>', '>='):
                raise KSEOError('阶段目标仅声明性能数值门禁，不替换正确性或最终验收')
            finite(gate.get('value'), 'milestone.value')
    for previous, current in zip(stages, stages[1:]):
        before = {g['field']:g for g in previous['gates']}
        after = {g['field']:g for g in current['gates']}
        if set(before) != set(after):raise KSEOError('各阶段必须覆盖同一套性能字段')
        for field,g in after.items():
            old = before[field]
            if g['op'] != old['op'] or (g['value'] > old['value'] if g['op'] in ('<','<=') else g['value'] < old['value']):
                raise KSEOError('阶段目标只能逐步收紧，不能回退或改变比较符')
    # 最后一阶段必须与正式 benchmark 门禁一致，不能以更宽目标结束。
    hard = {(g['field'], g['op'], finite(g['value'],'gate.value')) for g in policy['gates'] if g['stage'] == 'benchmark' and not g.get('always_required', False)}
    final = {(g['field'], g['op'], finite(g['value'],'gate.value')) for g in stages[-1]['gates']}
    if hard != final:
        raise KSEOError('最后一个 milestone 必须完整对应正式性能门禁')


def report(results, policy):
    from .validation import COMPARE
    rows = []
    for stage in policy.get('milestones', []):
        decisions = []
        for gate in stage['gates']:
            try:
                actual = finite(get_path(results, gate['field']), gate['field'])
                passed = bool(COMPARE[gate['op']](actual, gate['value']))
            except KSEOError:
                passed = False
            decisions.append(passed)
        rows.append({'name': stage['name'], 'passed': all(decisions)})
    return rows
