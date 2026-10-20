"""允许更新 Docker，同时绑定实际候选镜像与源码，最终部署必须是新实例。"""
import re
from .util import KSEOError


def validate(results, identity, policy, *, phase=None, previous_deployments=()):
    if not policy.get('docker_artifacts'):
        return
    if 'build' not in results:
        return
    artifact=results['build'].get('runtime',{}).get('artifact')
    if not isinstance(artifact,dict):raise KSEOError('build 必须输出实际候选镜像 artifact')
    if not re.fullmatch(r'.+@sha256:[a-f0-9]{64}',artifact.get('image','')):
        raise KSEOError('候选镜像需要实际完整 digest')
    for key,wanted in [('base_image',identity['image']),('source_revision',identity['source_revision']),('parameters_sha256',identity['parameters_sha256'])]:
        if artifact.get(key) != wanted:raise KSEOError('构建产物没有绑定相同的基础镜像/源码/参数')
    deployment=None
    for stage,result in results.items():
        if stage in ('preflight','build'):continue
        runtime=result.get('runtime',{})
        if runtime.get('artifact') != artifact:raise KSEOError(stage+' 使用的实际镜像/源码与 build 产物不符')
        identifier=runtime.get('deployment_id')
        if not isinstance(identifier,str) or not identifier:raise KSEOError('需要实际容器/Pod deployment_id')
        if stage=='deploy':
            deployment=identifier
            if phase=='final' and (runtime.get('fresh_deployment') is not True or identifier in previous_deployments):
                raise KSEOError('最终复验必须使用新创建的实际容器/Pod，不能复用搜索实例')
        elif deployment is None or identifier != deployment:
            raise KSEOError('测量没有绑定实际 deploy 实例')
    return artifact
