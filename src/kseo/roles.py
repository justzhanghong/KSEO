"""角色协议。LLM 提供诊断/提案，冻结 Validator 决定结果。"""
from copy import deepcopy

from .util import KSEOError, digest


ROLES = {
    'analyst': {
        'name': '瓶颈分析员',
        'inputs': ['当前 Profile', '源码/参数/负载身份', '已尝试路径', '冻结合同'],
        'outputs': ['绑定输入摘要的 diagnosis.json', '最大瓶颈点、证据、单个可检验假设及优化路径'],
        'may_write': ['本次诊断目录'],
        'must_not_change': ['候选源码', 'Profile 原始证据', '任务合同', 'Validator'],
        'authority': '建议；System 只接受当前 Profile 中可操作的路径。估计收益不是实测收益。',
    },
    'developer': {
        'name': '开发人员',
        'inputs': ['已选瓶颈及证据', '只读候选源码', '参数空间', '经验与证据边界', '冻结合同'],
        'outputs': ['proposal.json', '可选 patch.diff', '数学等价说明与验证建议'],
        'may_write': ['本次提案目录'],
        'must_not_change': ['输入源码副本', '任务合同', '参考实现/oracle', '数据集', 'Validator', '验收原始结果'],
        'authority': '提案；不能自行批准候选，也不能以质量分数代替数学等价性。',
    },
    'validator': {
        'name': '验收人员',
        'inputs': ['冻结合同与参考实现', '候选身份', '固定本地数据', '可信 adapter 产生的原始结果'],
        'outputs': ['独立重算的指标与逐项门禁', '局部/E2E 结论及失败证据'],
        'may_write': ['验收目录和审计结果'],
        'must_not_change': ['候选源码', '任务目标', '冻结容差', '数据分母', '参考实现/oracle'],
        'authority': '程序化 Validator 判定。可附加独立 Agent 审阅；审阅不能覆盖失败的硬门禁。',
    },
    'system': {
        'name': 'System 调度器',
        'inputs': ['角色产物', '阶段目标', '剩余预算', '历史 trial'],
        'outputs': ['路由', '候选集成/拒绝', '最佳有效候选', '最终验收与交付状态'],
        'may_write': ['状态、事件、独立源码副本和交付目录'],
        'must_not_change': ['已冻结合同', '原始证据', 'Validator'],
        'authority': '组织闭环；目标未达或最终验收未通过不能标为 COMPLETED。',
    },
}


def catalog():
    return {'schema_version': 1, 'roles': deepcopy(ROLES),
            'isolation': '协议检查和源码/工具摘要校验不等于 OS sandbox；生产应使用独立会话、容器及最小文件权限。',
            'implementation': 'analyst 为可选外部命令，未配置时使用 Profile/Amdahl 规则路由；developer 为外部命令；validator 为冻结的程序。'}


def contract(role):
    return {'role': role, **deepcopy(ROLES[role])}


def diagnosis_request(profile, identity, parameters, validation, seen, *, evidence=None):
    inputs = {'profile': profile, 'identity': identity, 'parameters': parameters,
              'validation': validation, 'seen': sorted(seen), 'evidence': deepcopy(evidence or {})}
    return {'schema_version': 1, 'role_contract': contract('analyst'), 'inputs': inputs,
            'input_sha256': digest(inputs),
            'instructions': '只写 diagnosis.json。ranked_hypotheses 每项包含 hotspot_id、lane、evidence、hypothesis。'
                            '只能引用本 Profile 的热点；按最大瓶颈点与可验证收益排序，不修改证据、源码或规则。'}


def validate_diagnosis(output, request):
    if not isinstance(output, dict) or output.get('schema_version') != 1 or output.get('input_sha256') != request['input_sha256']:
        raise KSEOError('瓶颈诊断未绑定本次冻结输入')
    rows = output.get('ranked_hypotheses')
    if not isinstance(rows, list):
        raise KSEOError('瓶颈诊断需要 ranked_hypotheses 列表')
    hotspots = {row['id']: row for row in request['inputs']['profile']['hotspots']}
    seen = set()
    for row in rows:
        if not isinstance(row, dict):raise KSEOError('诊断项必须是对象')
        identifier = row.get('hotspot_id')
        if identifier not in hotspots or identifier in seen:
            raise KSEOError('诊断引用未知或重复热点')
        seen.add(identifier)
        lane = 'kernel' if hotspots[identifier]['kind'] == 'kernel' else 'scheduling'
        if row.get('lane') != lane:
            raise KSEOError('诊断路径与实际 Profile 热点类型不符')
        if not isinstance(row.get('hypothesis'), str) or not row['hypothesis'].strip():
            raise KSEOError('诊断缺少可检验假设')
        if not isinstance(row.get('evidence'), list) or not row['evidence'] or any(not isinstance(x,str) or not x.strip() for x in row['evidence']):
            raise KSEOError('诊断缺少证据引用')
    return rows
