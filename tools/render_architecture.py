"""生成分层 Architecture 和独立流程图，不把依赖、顺序和反馈混画。"""

from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).resolve().parents[1] / "docs"
INK, MUTED, BLUE = "#10294a", "#56708b", "#2475dd"


class SVG:
    def __init__(self, width, height, title, subtitle):
        self.parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
                      f'<title id="title">{escape(title)}</title><desc id="desc">{escape(subtitle)}</desc>',
                      '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8Z" fill="#2475dd"/></marker></defs>',
                      f'<rect width="{width}" height="{height}" rx="20" fill="#f5f8fc"/>',
                      '<g font-family="Noto Sans CJK SC, Microsoft YaHei, sans-serif">']
        self.text(44, 55, title, 30, bold=True)
        self.text(44, 90, subtitle, 17, color=MUTED)

    def text(self, x, y, value, size=18, *, bold=False, color=INK):
        self.parts.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}"'+
                          (' font-weight="700"' if bold else '')+f'>{escape(value)}</text>')

    def rect(self, x, y, width, height, *, fill="white", stroke="#d5e1ef", radius=12):
        self.parts.append(f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')

    def card(self, x, y, width, height, title, lines=(), *, fill="white", size=20, body_size=16):
        self.rect(x, y, width, height, fill=fill)
        self.text(x + 18, y + 34, title, size, bold=True)
        for index, line in enumerate(lines):
            self.text(x + 18, y + 64 + index * 24, line, body_size, color=MUTED)

    def arrow(self, path, *, dashed=False):
        self.parts.append(f'<path d="{path}" fill="none" stroke="{BLUE}" stroke-width="2.2" marker-end="url(#arrow)"'+
                          (' stroke-dasharray="7 5"' if dashed else '')+'/>' )

    def save(self, name):
        (OUT / name).write_text("\n".join(self.parts + ["</g></svg>"]), encoding="utf-8")


def architecture():
    svg = SVG(1440, 1120, "KSEO Architecture", "分层架构只表达职责与依赖；执行顺序和反馈在独立流程图中展示")
    layers = [(130, 150, "L1 目标与上下文", "输入、能力与评测目标"),
              (330, 150, "L2 System 编排层", "端到端大流程与决策"),
              (530, 280, "L3 优化子流程", "局部分析、候选与证据"),
              (860, 200, "L4 共享运行基础", "执行、状态与可信验证")]
    for y, height, name, description in layers:
        svg.rect(44, y, 1352, height, fill="#edf3fb")
        svg.text(64, y + 45, name, 21, bold=True)
        svg.text(64, y + 77, description, 16, color=MUTED)
    for start, end in [(280, 330), (480, 530), (810, 860)]:
        svg.arrow(f"M860 {start+3} V{end-4}")
    for x, title, line in [(290, "模型与运行环境", "模型、源码、镜像、服务器"),
                            (650, "Workload 与能力", "请求分布、上下文、模型特性"),
                            (1010, "优化目标与预算", "TTFT / TPOT / 吞吐 / 质量")]:
        svg.card(x, 163, 330, 90, title, [line])
    for x, title, line in [(290, "System Workflow", "基线、迭代、最终复验与交付"),
                            (650, "Strategy Router", "配置优先：按最大瓶颈点与收益路由"),
                            (1010, "E2E Integrator", "集成、验收、最佳方案与回退")]:
        svg.card(x, 363, 330, 90, title, [line])
    cards = [(290, "Configuration", ["flags / env / backend", "有限搜索 → 参数候选", "返回配置与可检验假设"]),
             (650, "Scheduling", ["host / 通信 / 调度", "瓶颈分析 → 可回退候选", "返回参数或源码 patch"]),
             (1010, "Kernel", ["真实调用提取 → 冻结 oracle", "局部正确性与性能验证", "返回 patch 与独立证据"])]
    for x, title, lines in cards:
        svg.card(x, 565, 330, 195, title + " Workflow", lines, fill="#ffffff", size=21)
    svg.text(310, 790, "子流程不直接宣布端到端成功；候选统一交回 System 层验收。", 17, color=BLUE)
    services = [(290, 887, "Executor / Backend adapters"), (650, 887, "Source snapshot / Patch"),
                (1010, 887, "Validator / 原始证据"), (290, 968, "状态、预算与资源租约"),
                (650, 968, "Profile / 实验账本"), (1010, 968, "Knowledge / 经验记忆")]
    for x, y, title in services:
        svg.card(x, y, 330, 59, title, size=18)
    svg.text(44, 1095, "纵向箭头仅表示层间依赖。外部 Agent 与平台脚本通过子流程协议和 Backend adapters 接入。", 17, color=MUTED)
    svg.save("architecture.svg")


def system_flow():
    svg = SVG(1280, 490, "End-to-End Pipeline", "System 层大流程：候选生成、集成、评估和反馈分别归位")
    nodes = [("环境与基线", ["能力与环境检查", "正确性基线"]), ("采集 Profile", ["当前源码与负载", "定位瓶颈点"]),
             ("诊断与路由", ["配置优先", "最大瓶颈点与收益"]), ("调用子流程", ["Configuration", "Scheduling", "Kernel"]),
             ("集成候选", ["隔离源码", "可逆 patch"]), ("E2E 验收", ["通过全部门禁", "再选择 best"]),
             ("最终复验与交付", ["E2E + 三项精度", "证据与复现包"])]
    for index, (title, lines) in enumerate(nodes):
        x = 44 + index * 170
        svg.card(x, 150, 150, 140, title, lines, size=17, body_size=13)
        if index < len(nodes) - 1:
            svg.arrow(f"M{x+150} 212 H{x+166}")
    svg.text(1040, 139, "停止", 15, color=BLUE)
    svg.arrow("M969 290 V355 H289 V294", dashed=True)
    svg.text(375, 335, "继续：接受或回退 → 更新方案 → 重新采集 Profile", 17, color=BLUE)
    svg.rect(44, 400, 1170, 60, fill="#e7f0ff", stroke="#d0e1fa")
    svg.text(65, 437, "Kernel 局部通过只允许提交候选；是否保留仍由 System 层 E2E 验收决定。", 18)
    svg.save("system-workflow.svg")


def kernel_flow():
    svg = SVG(1280, 390, "Kernel Workflow", "Kernel 层内部小流程：独立 oracle、独立验证与可集成产物")
    nodes = [("提取真实调用", ["shape / dtype", "实际输入与边界"]), ("冻结 oracle", ["参考实现与 I/O", "文件清单与 SHA256"]),
             ("提出 Kernel 候选", ["独立源码与 patch", "限定 editable_files"]), ("独立正确性验证", ["完整 cases 与实际路径"]),
             ("局部性能验证", ["目标硬件", "相同测量条件"]), ("返回 patch 与证据", ["源码 tree", "patch / evidence hash"])]
    for index, (title, lines) in enumerate(nodes):
        x = 44 + index * 202
        svg.card(x, 140, 180, 110, title, lines, size=17, body_size=13)
        if index < len(nodes) - 1:
            svg.arrow(f"M{x+180} 195 H{x+198}")
    svg.rect(44, 290, 1190, 65, fill="#e7f0ff", stroke="#d0e1fa")
    svg.text(65, 329, "子流程在此返回。System 接手：可逆集成 → E2E 验收 → 保留或回退。", 19)
    svg.save("kernel-workflow.svg")


def other_flows():
    svg = SVG(1280, 600, "Configuration / Scheduling Workflows", "这两类子流程负责提出候选；部署、测量和最终选择由 System 层统一完成")
    for y, title, labels in [(140, "Configuration 子流程", ["读取当前参数", "有限搜索空间", "去重与预算检查", "返回参数候选"]),
                              (350, "Scheduling 子流程", ["读取最大瓶颈点", "形成可检验假设", "参数与 patch 约束检查", "返回可回退候选"])]:
        svg.text(44, y, title, 23, bold=True)
        for index, label in enumerate(labels):
            x = 44 + index * 300
            svg.card(x, y + 28, 270, 80, label, size=20)
            if index < len(labels) - 1:
                svg.arrow(f"M{x+270} {y+68} H{x+296}")
    svg.text(44, 550, "Scheduling 承接 host、通信与调度；按最大瓶颈点与收益路由，历史经验作为辅助。", 18, color=MUTED)
    svg.save("optimization-workflows.svg")


def role_flow():
    svg = SVG(1280, 650, 'KSEO · 角色协作', '外部大流程由 System 组织；三方分别交付诊断、候选和独立验收证据')
    svg.card(44, 125, 1190, 90, 'System 调度器', ['冻结目标与预算 · 先配置搜索 · 按最大瓶颈点路由 · 集成/回退 · 继续迭代或最终交付'], fill='#e7f0ff')
    for x,title,lines in [
        (44,'瓶颈分析员 Analyst',['读取：Profile / 请求 / 身份','输出：证据、瓶颈、可检验假设','权限：只写诊断目录']),
        (454,'开发人员 Developer',['读取：诊断 / 源码 / 经验边界','输出：参数、patch、等价说明','权限：只写提案目录']),
        (864,'验收人员 Validator',['读取：冻结合同 / oracle / raw','输出：重算指标、门禁及失败证据','权限：不修改目标与候选'])]:
        svg.card(x, 255, 370, 155, title, lines, size=21, body_size=16)
    svg.arrow('M414 330 H450'); svg.arrow('M824 330 H860')
    svg.arrow('M1049 410 V470 H229 V414', dashed=True)
    svg.text(370, 454, '继续：失败证据 / 实际收益 → System 更新方案与 Profile', 18, color=BLUE)
    svg.card(44, 520, 1190, 90, '共享基础：可信 Backend、独立源码副本、原始证据、冻结 Validator、状态与预算',
             ['角色可使用同一模型的独立会话；协议检查不等于 OS sandbox，生产须配置实际写权限隔离。'], size=20)
    svg.save('roles.svg')


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    architecture(); system_flow(); kernel_flow(); other_flows(); role_flow()
    print("已生成分层 Architecture、各级流程与角色协作图。")
