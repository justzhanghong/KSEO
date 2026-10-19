# KSEO 工程约定

- 用户说明、CLI 帮助、报告和经验卡优先使用中文；专业名词和代码标识保持英文。
- 禁止使用 brainstorming、planning-with-files、grilling 和 grill-me skill。
- Python 运行时仅依赖标准库，支持 Python 3.10 及以上。
- 任务合同和 Validator 独立于候选源码，不能由优化候选修改。
- synthetic、replay 与 measured 结果严格区分；禁止把示例或历史回放称为新实测收益。
- 源码、镜像、配置和负载身份必须进入实验记录。未知身份不能默认为验证通过。
- credentials 只通过环境或外部配置注入，不提交内部地址、账号、原始运维日志或模型权重。
- 提交前运行 `PYTHONPATH=src python3 -m unittest discover -s tests -v` 和 README 中的 CPU 示例。
- 不为测试启动真实模型或占用 GPU；真实运行需要明确提供 adapter 和任务合同。
