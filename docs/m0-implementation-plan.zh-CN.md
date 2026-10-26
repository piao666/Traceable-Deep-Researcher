# M0 契约与离线基线：实施清单

> 按 `superpowers:subagent-driven-development` 分工实施并复核。执行顺序为先测试、确认缺失行为、实现、回归；实施期间未自动提交或推送。用户于 2026-10-26 授权更新任务清单并提交推送本阶段成果。

实施日期：2026-10-24 至 2026-10-25；当前分支 `codex/work`。规格与代码质量复核均已完成，实际验证记录见第 8 节。

## 1. 阶段范围

本清单落实 [总方案](optimization-plan.zh-CN.md) 的 M0（第 2 节及 D1/D2/D3 的离线基础），不是 M1 的持久任务服务。交付请求/状态/事件/结果契约、任务/节点样本契约、确定性回放器、数据集校验、运行清单和错误不被跳过的结果汇总。

M0 使用 8 个自编任务和 8 个节点样本，覆盖中英文本、基本事实、比较、版本冲突、缺证据、重复引用、空结果、工具失败。全部为开发集，不声称已完成 80 题标注集、人工双标或真实模型评测。运行结果属于工程回放，不代表研究质量。线上 provider、任务队列、证据持久库和生产 API 接线在后续阶段实施。

沿用用户指定的 `codex/work` 工作分支。原工作区的 Graphify 本地产物和忽略规则已经存在，本轮不删除或覆盖。代码文件与评测输出严格分开。

## 2. 已阅读的源码与发现

| 文件 | 现状 | M0 决策 |
|---|---|---|
| `traceable_deep_researcher/__init__.py` | 导入包时立即导入 agent 与检索/模型依赖 | 公共类改为延迟导出，保持 `from ... import TraceableDeepResearcher`；契约可独立导入 |
| `traceable_deep_researcher/agent.py::__init__` | 使用 kwargs 传递扩展配置 | 显式可选 run_context，避免其落入模型 kwargs；不改变旧方法返回值 |
| `backend/server/app.py::ResearchRequest` | 当前 HTTP 模型与未来任务模型不同 | 新增 tasks/models，M0 不替换旧路由模型 |
| `backend/server/websocket_manager.py::run_agent` | 返回值因分支不同 | 定义 ResearchResult，实际分支迁移留在 M1/A2 |
| `evals/quality_eval/base.py`、`suite.py` | 分数/跳过；异常也转成跳过 | 新框架区分 error/skipped/N/A；旧结构加可选状态兼容适配 |
| `evals/quality_eval/metrics.py` | 域名引用一致性等纯指标 | 回放复用其确定性函数；明确 domain alignment，不称语义支持 |
| `evals/quality_eval/benchmark.py` | 修改环境和全局类收集结果 | 新 runner 实例隔离；本阶段不替换旧在线 benchmark |
| `evals/context_filter/replay.py` | 回放仍调用真实模型/embedding | 新 runner 内部阻断网络，fixture miss 报错，无在线回退 |
| `tests/conftest.py` | pytest 可选阻断 socket，允许 loopback | 新 CLI 独立实现可恢复的网络 guard，不依赖 pytest 环境 |
| `frontend/nextjs/types/data.ts` | UI 旧 block，无 task/seq | 增加可选关联字段与独立契约类型，旧页面不改行为 |

当前解释器具备 Python 3.12、pytest、Pydantic v2，缺少完整业务模型依赖。先跑可用的既有质量指标测试，再对新增轻量模块验证；业务级回归需要完整依赖时明确记录环境限制，不能冒充通过。

## 3. 任务 01：运行与前后端契约

新增：

- `traceable_deep_researcher/runtime/__init__.py`、`contracts.py`：标准库 dataclass 与 Protocol，RunContext、ResearchResult、EventSink、CheckpointStore、ReviewInbox。
- `backend/server/tasks/__init__.py`、`models.py`：ResearchTaskRequest、Budget、SourcePolicy、TaskEvent、SubscribeCommand 以及任务/审核/导出枚举。
- `frontend/nextjs/types/research.ts`：对应 TypeScript 类型；`tests/fixtures/research-contract.v1.json`：有效契约样本。
- `scripts/check_research_contract_types.mjs`：将该样本作为虚拟 TypeScript 文件编译，无需写入应用源码。
- `tests/runtime/test_contracts.py`、`tests/backend/test_task_contracts.py`：序列化、非法值、默认集合隔离、协议注入和轻量导入。

修改：`traceable_deep_researcher/__init__.py` 延迟导入公共类；`agent.py` 显式注入 run_context；`frontend/nextjs/types/data.ts` 为旧 UI block 增加可选 research_id/attempt_id/seq。

- [x] 测试先验证缺少契约、非法事件版本/序号/时区、空任务和错误枚举、共享默认集合。
- [x] 定义 RunContext 的 research_id/attempt_id/span_id/parent_span_id 与可选协议引用；child 创建新 span 并保留 task/attempt 与依赖。
- [x] 请求只接受已支持 report_type/source/tone；预算正数；额外字段拒绝。保存 MCP 配置引用，不接受嵌套的真实密钥配置。
- [x] 事件固定 version=1，时间必须带时区，状态分开；订阅 seq 可为 0。
- [x] 运行契约只用标准库，任务验证只需 Pydantic；不从新模块导入 FastAPI/数据库/provider。
- [x] 现有公共类的导出名称保持一致；用 AST/隔离依赖测试确认 run_context 不进入 kwargs。

验收：新模块可在无模型依赖环境导入，既有调用者构造方式不变；不声称运行方法已使用持久化协议。

## 4. 任务 02：评测契约、清单和结果状态

新增 `evals/framework/__init__.py`、`models.py`、`manifest.py`、`results.py`、`gates.py`；新增 `tests/evals/test_eval_contracts.py`、`test_manifest.py`、`test_result_aggregation.py`。

- [x] TaskCase：版本、split、query、日期、source_bundle、requirements、gold facts/evidence、预算、故障和标签；AgentCase：节点、输入、允许工具、预期约束、gold 引用。
- [x] 被测系统输入通过显式白名单投影，不包含 gold、评分标准内部标签或其他样本信息。
- [x] EvalResult 的 passed/failed 必须有有效 score，error/skipped/N/A 不允许分数，原因必填；非有限值拒绝。
- [x] 汇总保留所有状态计数与实际评分分母；failed 的 0 分参与平均，error 不变成 0 分或成功。
- [x] 必需指标缺失/error/skipped/N/A 阻止门禁；语义 N/A 不可被误读为完美结果。
- [x] manifest 包含 commit、源码脏状态摘要、Python/依赖、dataset/config/prompt/source hash、seed 和 fixture 模型说明；不保存环境变量或凭据。
- [x] 扩展旧 EvalSample 的可选 task/trace/evidence 引用；旧 MetricResult.skipped 保留兼容，异常显式标 error，旧字典适配保留原返回键。

验收：已有 `tests/test_quality_metrics.py` 保持通过；新错误状态能从旧指标适配出来，并在新门禁中拒绝通过。

## 5. 任务 03：冻结数据集、验证器与小型基线

新增 `evals/datasets/task_cases.v1.jsonl`、`agent_cases.v1.jsonl`、`dataset_manifest.json`、`source_bundles/`、`replays/`、`README.md`；新增 `evals/framework/datasets.py`、`scripts/validate_eval_dataset.py` 与 `tests/evals/test_dataset_validation.py`。

- [x] 每个样本带 split、group_id 和版本，所有内容为自编合成事实；同组不能跨 split。
- [x] manifest 列出每个文件的 SHA-256；加载时先验证路径位于数据集根目录内，再验证 hash 和 schema。
- [x] source bundle 的 evidence 用 Unicode code point 坐标；验证 quote/hash 和半开区间。
- [x] replay 单独保存工具调用/固定响应、最终报告、已知故障；被测输入不包含 gold。
- [x] 校验 ID 唯一、文件存在、case/replay/source 引用有效、split 不泄漏、证据范围有效；被修改的 fixture 不能继续跑成绿色。
- [x] 8 任务和 8 节点作为 smoke 数据，不混成实际模型成绩；已知问题另列说明，不用 fixed response 证明已修复生产流程。

验收：正常数据集校验成功；重复 ID、跨 split 同组、越界路径、坏 hash、缺失工具 fixture 都有独立失败测试。

## 6. 任务 04：无网络回放与统一 CLI

新增 `evals/framework/replay.py`、`network_guard.py`、`constraints.py`；新增 `evals/task_eval/__init__.py`、`evals/agent_eval/__init__.py`、`evals/run.py`、`evals/report.py`；新增 `tests/evals/test_tool_replay.py`、`test_offline_guard.py`、`test_cli.py`。

- [x] Replay key 为规范化 JSON（tool/context/fixture key/arguments）；每个实例有独立计数；匹配失败立即报错，无 live fallback。
- [x] guard 阻止 TCP/UDP、DNS 与 connect_ex；上下文退出恢复原函数，嵌套 guard 不扩大权限；默认不放行 loopback。
- [x] runner 默认 offline；M0 对 frozen-tools/live 明确返回配置错误，避免仅提供名称却真实联网。后续实现才启用。
- [x] 任务与节点 suite 各自只消费合法输入，重放固定产物并运行确定性约束/引用一致性检查；不存在语义裁判分数。
- [x] 输出 manifest/results/summary 到 `evals/results/<run_id>`，已有输出目录不覆盖；exit code 0/1/2 分别是通过/有效评测不达标/配置或执行错误。
- [x] report 命令只读取既有结果并输出 Markdown，不触发研究；汇总明确标注 engineering replay。
- [x] 新增忽略 `/evals/results/`，保留原有 Graphify 忽略改动；运行失败也保存可解释状态。

验收：没有供应商密钥也能跑完两套 suite；fixture miss 不访问网络；输出可重复（manifest 时间等运行字段除外），CLI 能区分失败与错误。

## 7. 技术风险小样与收尾

小样文件：新增 `evals/probes/recovery.py`、`evals/probes/structured_output.py`、`tests/runtime/test_m0_probes.py` 和隔离验证依赖清单 `evals/requirements-m0.txt`；仅使用临时数据，不接入应用启动流程。

- [x] SQLite 用临时数据库验证 event seq 唯一/事务回滚与重开持久性，不建立生产存储。
- [x] LangGraph 持久 interrupt/resume 以及结构化写作只做兼容性小样；真实图依赖未安装时先准备隔离测试环境，不用内存恢复冒充进程恢复。
- [x] 编写 `docs/evaluation.md` 的 M0 使用方式与边界，更新 `docs/architecture.md` 和总方案阶段状态。
- [x] 运行新增全部测试、已有质量指标测试、Python 编译检查；前端有类型改动时运行生产构建（缺依赖先准备环境）。
- [x] 规格复核后再做代码质量复核，修正问题并重跑受影响测试。
- [x] 在本清单末尾记录实际命令与结果；不提交生成报告、缓存或数据库。

## 8. 实际验证记录

以下为本轮实际执行记录，不沿用历史迁移记录。完整应用研究及真实供应商评测未执行。

### 8.1 最终验收（2026-10-25）

| 检查 | 实际结果 |
|---|---|
| `TDR_BLOCK_NETWORK=1 .venv/Scripts/python.exe -m pytest tests/runtime tests/backend/test_task_contracts.py tests/evals tests/test_quality_metrics.py -q --tb=short` | **154 passed**，无跳过；包含现有 39 项质量指标测试与新增契约/数据/回放/错误路径测试 |
| 新模块、受影响核心与测试的 `compileall` | 退出码 0 |
| `npm ci --legacy-peer-deps --ignore-scripts --no-audit --no-fund` | 按现有 Dockerfile 依赖规则安装成功；未修改 package-lock.json |
| `NEXT_TELEMETRY_DISABLED=1 npm run build` | Next.js 生产构建、lint 与 TypeScript 校验成功 |
| `node scripts/check_research_contract_types.mjs` | 共享 JSON 样本静态类型检查成功 |
| 类型检查负面对照 | 将事件 version 改为 2 后，TypeScript 检查退出 1；原样本仍通过 |
| 数据集验证 CLI | 8 task / 8 agent；所有 hash、引用、片段坐标和分组校验通过 |
| `evals.run` 两套 offline suite | 各 8 个工程回放案例通过；provider_calls=0；无真实模型分数 |
| SQLite / LangGraph 小样 | 事务回滚与重开通过；两个独立 Python 进程间恢复同一个审核检查点通过 |
| 规格与质量复核 | 先独立规格复核，再独立质量复核；发现的问题均修正并复核关闭 |

运行环境：Python 3.12.10、Pydantic 2.13.4、pytest 9.1.1、pytest-asyncio 1.4.0。风险小样验证版本为 langgraph 1.2.17、langgraph-checkpoint 4.3.0、langgraph-checkpoint-sqlite 3.1.2；独立清单在 `evals/requirements-m0.txt`。前端为 Node 24.21.0、npm 11.19.0、锁文件中的 Next.js 14.2.35。

本机 Windows 沙箱会阻止 asyncio 自唤醒连接，pytest 默认沙箱临时目录也存在权限限制。已用最小 asyncio 样例确认差异：沙箱内卡住，沙箱外立即完成。因此涉及异步和临时文件的验证在沙箱外执行，同时保留 `TDR_BLOCK_NETWORK=1`；回放 CLI 自身另外安装 socket/DNS 阻断，不依赖测试进程。

直接 `npm ci` 的第一次准备失败：锁文件按 legacy peer 规则生成。检查现有 Dockerfile 后使用其原有 `--legacy-peer-deps` 规则成功，没有重新生成锁文件或升级依赖。

### 8.2 红绿验证与复核修正

- 新契约、CLI、数据加载器在实现前都执行过缺失功能的失败检查，再实现与回归。
- Budget 的浮点字段拒绝 bool；保留正常数字秒数/费用。
- 数据配置校验不再要求候选提前满足标准答案：合法负面候选得到 failed/退出 1，无效配置得到退出 2。
- 代码指纹纳入新增源码和根依赖契约；记录限定范围 dirty diff 的 hash。
- 子主题/论断的提取和逐项裁判、来源权威性裁判异常都保留 error 与空分数；未配置权威性裁判时的原规则回退保留。
- 裁判错误的原始明细保留在 breakdown，调用失败不再伪装为未覆盖、无依据 0 分或默认权威分数。
- 节点 equals 约束改为 JSON 类型感知的递归比较，true 不等于 1，嵌套对象/数组同样适用。
- 比较案例补充重复正文引用和重复来源 URL，标签与数据 pin 同步更新。

### 8.3 基线产物与后续入口

2026-10-26 提交前复核：上述 154 项离线测试再次全部通过。暂存检查发现 Windows 换行转换会影响原始字节 hash，新增 `.gitattributes` 将数据集 JSON/JSONL 固定为 LF、同步更新 manifest pins，并确认暂存区中的全部数据文件 hash 与 manifest 一致。修正后 154 项测试再次通过（19.31 秒，无跳过）；共享契约 TypeScript 检查、8 task / 8 agent 数据集校验、`git diff --check` 均通过。此前生产构建记录仍见 8.1；此次未重跑构建。

完整输出留在忽略目录 `evals/results/`，包含每次 manifest、逐例结果与汇总，不提交生成报告。可按 `docs/evaluation.md` 的命令选择新目录复现。

M0 完成的是契约、工程回放和兼容性小样。M1 的第一个实施点仍是 A1：建立生产存储与旧 ReportStore 迁移，然后接任务服务/worker；本轮没有宣称生产研究已具备持久化、断线恢复或逐论断追溯。
