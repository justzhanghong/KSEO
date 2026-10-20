"""冻结生成协议；无人工输出上限仍必须遵守实际上下文边界。"""
from .util import KSEOError, positive_int


def validate_generation(generation: dict) -> None:
    if not isinstance(generation, dict):
        raise KSEOError('generation 必须为对象')
    positive_int(generation.get('context_limit'), 'generation.context_limit')
    mode = generation.get('output_limit', 'fixed')
    if mode not in ('fixed', 'context_remaining'):
        raise KSEOError('output_limit 必须为 fixed 或 context_remaining')
    if mode == 'fixed':
        positive_int(generation.get('first_max_output_tokens'), 'first_max_output_tokens')
    elif generation.get('first_max_output_tokens') is not None:
        raise KSEOError('context_remaining 不得同时设置人为 first_max_output_tokens')
    if generation.get('retry_policy') not in ('none', 'empty_length_once'):
        raise KSEOError('retry_policy 必须显式冻结')
    if mode == 'context_remaining' and generation['retry_policy'] != 'none':
        raise KSEOError('已使用全部上下文余量时默认不重采样；不得把 length 当成可扩容预算')
    if not isinstance(generation.get('thinking'), str) or not generation['thinking']:
        raise KSEOError('必须冻结 thinking')


def output_budget(generation: dict, prompt_tokens: int, attempt: int = 0) -> int:
    positive_int(prompt_tokens, 'native prompt_tokens')
    context = positive_int(generation.get('context_limit'), '实际 context_limit')
    remaining = context - prompt_tokens
    if remaining <= 0:
        raise KSEOError('输入占满实际上下文，无法生成；不能静默裁剪输入')
    if generation.get('output_limit', 'fixed') == 'context_remaining' or attempt:
        return remaining
    return positive_int(generation.get('first_max_output_tokens'), 'first_max_output_tokens')
