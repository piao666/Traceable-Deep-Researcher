# Traceable Deep Researcher 四项优化实施方案

> 执行说明：按工作包逐项实施和验证；复选框记录已验收步骤，阶段进度见第 8.1 节。提交与推送遵循用户授权。

**目标**：形成可靠交付、交互闭环、关键结论可追溯和两层评测的自托管研究应用。

**架构**：以持久任务服务统一入口和执行，以版本化报告及证据模型承接结果，以同一轨迹契约支持任务/智能体评测。核心包通过协议注入存储、事件和审核依赖，保持现有公共类兼容。

**技术栈**：现有 Python/FastAPI、SQLAlchemy、LangGraph、Next.js/TypeScript、pytest；建议新增 SQLite 任务存储及前端测试工具，依赖版本在实施时锁定。

创建日期：2026-10-23；补全日期：2026-10-24；清单更新：2026-10-30。状态：M0 已验收；M1/A1–A7 的代码、离线、Linux 容器、浏览器验收及本地部署切换已完成；M2–M4 待实施。当前恢复粒度及部署记录见下文。

阶段更新（2026-10-30）：已依次完成 [批次 03 / A2–A3](m1-a2-a3-implementation-plan.zh-CN.md)、[批次 04 / A4–A5](m1-a4-a5-implementation-plan.zh-CN.md)、[批次 05 / A6–A7](m1-a6-a7-implementation-plan.zh-CN.md)：持久任务、单机 worker/租约、阶段检查点、有序事件与刷新恢复、独立导出、服务端历史。230 项离线回归、42 项 Linux 阶段/连接测试、8 项任务容器检查、前端生产构建和桌面/手机浏览器核验通过。旧历史现状为 JSON 不存在、报告/聊天各 0；没有虚构数据导入。多代理图节点与人工审核恢复仍属 B3，外部 LangGraph 不纳入本地恢复。完整验收与本地切换结果见 [validation](validation.md)。

阶段更新（2026-10-29）：批次 02 / A1 已按[详细实施清单](m1-a1-implementation-plan.zh-CN.md)接入 SQLite 报告存储、显式 schema 检查和旧历史迁移工具，并补齐 13 项隔离 Linux 容器检查。Docker/WSL2 环境已可用；真实数据未迁移，任务队列、worker 和研究恢复仍未实现。

阶段更新（2026-10-25）：M0 的运行/评测契约、小型离线工程回放和技术风险小样已实施；详细范围、验收记录见 [M0 实施清单](m0-implementation-plan.zh-CN.md) 和 [评测使用说明](evaluation.md)。M1–M4 及下面各完整工作包的完成标准仍按原计划推进，不能将 M0 的固定产物检查当作模型研究质量。

源码基线：`642a06c46ae4f05bc53d6114255a684d08a2d0ec`，本地工作分支 `codex/work`。依据为当前源码、[现有架构说明](architecture.md)以及本地 Graphify 图谱和链路梳理；图谱用于定位，实际行为以源码和后续测试为准。

阅读导航：[A 任务可靠性](#work-a) · [B 功能闭环](#work-b) · [C 证据追溯](#work-c) · [D 两层评测](#work-d) · [实施顺序](#delivery-order) · [验证与验收](#verification)

## 1. 目标、范围和交付标准

本轮包含四个工作包：

1. **任务可靠交付**：任务持久化、断线恢复、阶段恢复、正文与导出解耦。
2. **功能闭环**：移动端统一研究入口、人工反馈贯通、审核状态修正。
3. **最小证据追溯**：关键结论 → 证据片段 → 来源快照，版本与发布校验。
4. **项目评测**：任务级评测判断整体交付，智能体级评测定位规划、检索、写作、审核等环节的问题。

实施保留 `traceable_deep_researcher` 模块、`TraceableDeepResearcher` 公共类和自托管 Docker 定位；不将本轮扩展为包/插件发布。Traceable Research Agent 只作为只读设计参考，不直接修改或复制其运行引擎。保留 LICENSE、UPSTREAM.md 和第三方评测归属。

本文表格中的“修改”指已存在文件，“新增”指建议创建的文件。代码路径均相对仓库根目录；定位以函数/类名为主，避免实施过程中行号漂移。示意接口、配置和命令是拟定设计，不是当前已可用功能。

| 工作包 | 用户可感知的交付 | 完成条件 |
|---|---|---|
| A 任务可靠性 | 刷新页面后继续看研究，研究完成后立即读正文，单独重试导出 | 任务与连接解耦；服务重启后状态可解释；可恢复阶段有检查点；不重复提交成果 |
| B 功能闭环 | 桌面与移动端执行同一种研究；能确认/修改计划；看到真实审核状态 | 同请求契约；人工反馈只消费一次；超限不会变为通过 |
| C 证据追溯 | 点击关键结论看到当时使用的原文证据 | 片段坐标校验通过；所有“已验证”结论绑定有效证据；报告修订使旧审核失效 |
| D 项目评测 | 对比版本、定位退化环节、查看质量/成本/可靠性 | 离线回放可重复；任务与节点指标分开；失败和跳过不被统计为成功 |

### 1.1 实施前确认的现状

| 事实 | 源码定位 | 设计影响 |
|---|---|---|
| WS 主循环持有 `running_task`，断开时取消任务 | `backend/server/server_utils.py::handle_websocket_communication` | 连接必须改成订阅者，执行归 TaskService 管理 |
| HTTP 后台请求使用 `BackgroundTasks` | `backend/server/app.py::generate_report` | 替换为持久任务提交，不把 BackgroundTasks 当队列 |
| 正文导出后才发送 `path`，前端据此结束 loading | `backend/server/server_utils.py::generate_report_files`、`frontend/nextjs/hooks/useWebSocket.ts` | 正文完成和每一种导出独立建模 |
| 历史通常由 Next.js 完成 effect 保存 | `frontend/nextjs/app/page.tsx`、`frontend/nextjs/hooks/useResearchHistory.ts` | 服务端成为任务报告的权威写入方 |
| ReportStore 整体 JSON 读写，进程内锁，读取异常返回空字典 | `backend/server/report_store.py::ReportStore` | 迁移数据库，损坏不得被解释成空库再覆盖 |
| `run_agent` 普通分支可返回元组，多代理分支仍返回字符串；HTTP 先访问 `[0]` | `backend/server/websocket_manager.py::run_agent`、`backend/server/app.py::write_report` | 增加统一内部结果类型，避免多代理字符串被当元组使用 |
| 移动入口走聊天并产生与保存结果不一致的 ID | `frontend/nextjs/app/page.tsx::handleMobileDisplayResult` | 改用共享任务 API，ID 由服务端返回 |
| HumanAgent 也直接 `receive_text`，与 WS 主循环争用接收；异常可能留下空反馈 | `multi_agents/agents/human.py::review_plan` | 只保留一个网络接收者；审核输入来自持久 review inbox |
| 主编路由在修订超限后返回 `accept` | `multi_agents/agents/orchestrator.py::_route_human_feedback/_route_fact_check` | 增加 needs_review/blocked 分支，不再强制接受 |
| 已有多套评测，但不是统一任务/节点框架 | `evals/quality_eval`、`simple_evals`、`hallucination_eval`、`context_filter`、`deep_agents/*benchmark.py` | 复用指标与适配器，避免另建一套重复指标 |

## 2. 四项共用的设计基础

### 2.1 统一标识和依赖方向

全链路使用 `research_id`；每次执行使用 `attempt_id`；代理/工具步骤使用 `span_id` 和 `parent_span_id`；报告使用 `report_id + version`；证据使用 `snapshot_id/evidence_id/claim_id`；人工审核使用 `review_id`。

核心包只依赖轻量协议，不依赖 FastAPI 或数据库。后端实现持久化协议；评测使用内存实现或冻结数据实现。各入口映射到相同服务：

```text
桌面 / 移动 / 静态 UI / HTTP / 旧 WS 适配器
                    ↓
          ResearchRequest → TaskService
                    ↓
        数据库任务与事件 → Worker/Runner
                    ↓
          普通 / 详细 / deep / multi_agents
                    ↓
         研究结果 + 来源/步骤轨迹 + 报告版本
                ↙               ↘
         证据/审核校验         独立 ExportService
                    ↓
         UI 查询 / 事件回放 / 离线评测适配器
```

独立 `deep_agents` 首先接入评测与追踪适配器，不在本轮默认注册为网页研究类型；它与现有 `report_type=deep` 是不同执行方式。Next.js 直连 LangGraph 的分支须显式标记为外部执行模式；完成统一适配前，不能宣称该分支具备本地任务恢复能力。

### 2.2 新增与修改的公共契约

| 文件 | 方式与内容 |
|---|---|
| `traceable_deep_researcher/runtime/contracts.py` | **新增** `RunContext`、`ResearchResult`、`EventSink`、`CheckpointStore`、`ReviewInbox` 协议；所有新增核心参数可选 |
| `traceable_deep_researcher/runtime/tracing.py` | **新增** span 上下文、工具调用与产物引用记录；记录可观察输入/输出和错误，不要求记录模型隐藏推理 |
| `backend/server/tasks/models.py` | **新增** Pydantic 请求/状态/事件模型；统一约束枚举、预算、审核选项、来源与 MCP 配置引用 |
| `backend/server/settings.py` | **新增** 本轮服务端设置；新设置均为 `TDR_` 前缀，不将数据库配置塞进模型供应商配置 |
| `traceable_deep_researcher/agent.py` | **修改** 构造器增加可选 `run_context`；原公共 `conduct_research`/`write_report` 返回形式保持兼容 |
| `frontend/nextjs/types/research.ts` | **新增** 任务、事件、审核、报告版本和导出状态类型；用固定契约样本核对 Python/TS 字段 |
| `frontend/nextjs/types/data.ts` | **修改** UI block 关联任务/事件 ID；旧 block 通过转换器兼容 |

内部 `ResearchResult` 至少包含 `report_markdown`、`sources`、`context_refs`、`cost_summary`、`review_status`、`warnings`、`artifact_refs`；禁止返回活的数据库连接或研究器对象作为持久化结果。为了兼容已有调用，可暂留 `run_agent` 包装器，把新的 `run_research` 结果映射成旧形式，后端新路径直接使用新结果类型。

### 2.3 状态必须分开

任务执行状态：`queued → running → waiting_for_review → queued/running → succeeded/failed/cancelled`。运行恢复受阻时进入 `interrupted`，而不是一直显示 running。`cancel_requested` 是取消过程状态，只有 runner 确认停止后才变为 cancelled。

报告审核状态：`not_requested / pending / approved / needs_revision / needs_review / rejected`。执行 `succeeded` 仅指约定产物已生成，不代表事实审核通过。若策略要求审核通过才能完成，而达到上限，则停在 waiting_for_review；无人处理超时后按策略进入 interrupted 并保留草稿。

导出状态：每个 `(report_id, version, format)` 分别是 `queued/running/succeeded/failed`。生成正文成功后发出 `report.ready`；导出失败发出 `export.failed`，不把正文改成失败。需要用户拿到整套文件时，由 UI 展示“正文已完成，PDF 导出失败”。

### 2.4 数据库与事件一致性

第一版使用 SQLite 单机持久化，SQLAlchemy 已是项目依赖。采用短事务、外键、WAL、busy timeout；同步访问放到专用线程执行，避免阻塞事件循环。数据库写入逻辑统一在 repository 中，不能各模块自行拼接 SQL。

最低数据表：

| 表 | 关键字段/约束 |
|---|---|
| `research_tasks` | research_id PK、request_json（脱敏）、request_hash、idempotency_key、status、current_attempt、version、lease_owner、lease_until、fencing_token、cancel_requested、created_at/updated_at |
| `task_attempts` | attempt_id PK、research_id FK、开始/结束、错误、resume_from、模型/配置/代码版本摘要 |
| `task_events` | `(research_id, seq)` UNIQUE、attempt_id、event_type、payload、UTC 时间；seq 在事务内递增 |
| `task_checkpoints` | research_id、stage_key、schema_version、input_hash、artifact_refs、completed_at；逻辑步骤唯一 |
| `reports` / `report_versions` | 稳定 report_id、research_id、version、正文 hash、正文/产物引用、审核状态；版本不可覆盖 |
| `report_chats` | message_id、report_id、report_version、内容、来源引用、时间 |
| `export_jobs` | report_id、version、format、renderer_version、status、artifact_hash、错误与重试次数；组合唯一 |
| `review_requests` / `review_responses` | review_id、research_id、review_kind（plan/report/claim）、目标版本/hash、状态、deadline；每个 review 仅一个有效响应，计划批准不能替代报告批准 |

研究状态改变、报告版本写入和对应事件在同一数据库事务提交；通知只在提交后发送。通知失败时客户端通过事件表补读，不能依赖内存队列保证交付。文件先写临时位置并原子替换，再提交引用；失败遗留的无引用文件由独立清理流程处理，不能产生引用不存在文件的成功记录。

<a id="work-a"></a>

## 3. 工作包 A：任务持久化、恢复、导出解耦

### A1. 数据层与旧历史迁移

**涉及源码**：修改 `backend/server/report_store.py`、`backend/server/app.py` 的报告 CRUD；新增 `backend/server/storage/database.py`、`backend/server/storage/models.py`、`backend/server/storage/migrations/001_tasks.sql`、`backend/server/tasks/repository.py`、`scripts/migrate_report_store.py`。

**修改步骤**：

- [x] 把 ReportStore 的公开方法保留为兼容门面，内部交给数据库 repository；增加分页，避免每次读取所有报告。
- [x] 建立迁移版本表，启动时检测 schema；仅单个迁移进程执行结构升级，服务端不抢跑未完成迁移。
- [x] 迁移脚本先 dry-run 校验旧 JSON，输出记录数、异常 ID 和冲突；真正导入前备份旧文件并记录 SHA-256。
- [x] 旧报告保留 ID、聊天和时间；没有研究过程的历史标记 `legacy_import`、lineage unavailable，不伪造 task events 或证据。
- [x] 导入以源文件 hash 和旧 ID 幂等，事务失败整体回滚。损坏 JSON 停止迁移并报错，不能空库覆盖。
- [x] 提供维护停写、增量导入和切换操作说明；代码不双写 JSON/SQLite。部署检查与切换记录见 validation.md。

A1 范围说明：`001_tasks.sql` 建立报告/版本/聊天/schema 和导入凭据表；002–004 随后增加任务/事件/租约、检查点与导出。显式升级会先用 SQLite backup API 创建一致性备份。真实历史没有 JSON 可导入，不把这一现状记为旧数据迁移成功。

**验收**：新增 `tests/backend/test_report_store_migration.py`、`tests/backend/test_report_repository.py`，覆盖重复迁移、损坏文件、中文内容、相同 ID 冲突、并发更新和事务回滚；现有报告聊天路由测试继续通过。

### A2. 统一任务提交、状态查询和幂等

**涉及源码**：新增 `backend/server/tasks/service.py`、`backend/server/tasks/routes.py`；修改 `backend/server/app.py::generate_report/write_report`、`backend/server/websocket_manager.py::run_agent`、`backend/server/multi_agent_runner.py`。

**修改步骤**：

- [x] 定义 POST `/api/research`，验证请求后返回 HTTP 202 和服务端生成的 research_id；保存配置快照摘要和显式的 report_type/source。
- [x] 同一部署调用范围内，`Idempotency-Key + request_hash` 防重复：相同 key/内容返回原任务；相同 key/不同内容返回 409。若将来支持多用户，该唯一键必须带 owner scope。
- [x] GET `/api/research/{id}` 返回执行/审核/导出状态、最近 seq 和可用报告；GET 列表使用分页和状态过滤。
- [x] POST `/{id}/cancel` 发出取消请求；POST `/{id}/resume` 只允许 interrupted 或可重试失败，不允许重入正在运行的任务。
- [x] 普通、详细、deep、多代理均适配为 ResearchResult。修正 HTTP 对多代理返回值按字符串下标处理的问题。
- [x] 原 `/report/` 的后台模式委托 TaskService，前台模式等待同一任务的报告结果；等待超时返回任务引用，不能取消实际任务。旧返回字段通过适配器保留一个过渡版本。

**验收**：新增 `tests/backend/test_task_api.py`、`tests/backend/test_research_result_adapters.py`；覆盖重复提交、类型非法、取消与完成竞争、四种报告类型和旧 HTTP 返回兼容。

### A3. 将执行所有权从连接转移到 worker

**涉及源码**：新增 `backend/server/tasks/worker.py`、`backend/server/tasks/runner.py`；修改 `backend/server/app.py` 启停生命周期、`backend/server/server_utils.py::handle_start_command/handle_websocket_communication`、`backend/server/websocket_manager.py`。

**修改步骤**：

- [x] 第一版在单个 API 服务实例的 lifespan 内启动 worker，默认部署一个 API 进程；持久队列为数据库任务表。后续可复用 runner 分离 worker 进程，无需首版引入 Redis/Celery。
- [x] 使用事务 compare-and-set 领取 queued 任务；写入 lease、attempt_id 和递增 fencing_token。每次 checkpoint、状态和产物提交都校验 token，拒绝过期 worker 覆盖新尝试。
- [x] 运行中定期续租；进程退出前停止领取新任务，在有限宽限时间内保存检查点。租约过期只使任务具备重新领取条件，不能直接把它视为业务成功。
- [x] 进程丢失/租约过期置 interrupted，显式 resume 后复用兼容的已完成阶段；未完成阶段可能重跑。临时凭据丢失时拒绝恢复并要求新提交。
- [x] 断开 WS 只释放订阅队列和 sender，不取消研究。用户显式取消才传播 cancellation token 并关闭 MCP/抓取客户端。
- [x] 暂存凭据放在内存或部署端 secret resolver，数据库只保存脱敏配置与凭据引用；重启后无法恢复临时凭据的任务进入 interrupted/requires_credentials。

**验收**：新增 `tests/backend/test_task_worker.py`、`tests/backend/test_task_leases.py`；模拟进程丢失、租约竞争、旧 worker 延迟写入、取消传播。扩展 `tests/backend/test_websocket_disconnect_cleanup.py`，同时验证连接资源释放与后台任务继续；保留原清理断言。

### A4. 可恢复阶段与结果幂等

**涉及源码**：修改 `backend/report_type/basic_report/basic_report.py::run`、`backend/report_type/detailed_report/detailed_report.py::run`、`traceable_deep_researcher/agent.py`、`traceable_deep_researcher/skills/researcher.py`、`traceable_deep_researcher/skills/deep_research.py`；新增 `traceable_deep_researcher/runtime/checkpoints.py`。

**修改步骤**：

- [x] 第一批检查点为 `plan_ready`、`research_complete`、`report_written`。持久化查询计划、来源/上下文引用、visited_urls、成本和版本，不 pickle 整个研究器对象。
- [x] detailed 增加 section_id 检查点；deep 使用父子 query_id 与深度路径，恢复已完成子查询，避免仅以问题字符串作为唯一身份。
- [x] 检查点携带输入/配置/prompt hash、schema_version；版本不兼容时拒绝静默复用并说明重跑范围。
- [x] 流式正文绑定 attempt_id 和单调 seq。新尝试先发 `report.draft_reset`，避免前端把两次尝试拼接为一篇。
- [x] 以“至少执行一次、结果幂等提交”为语义；远程 LLM/工具调用在崩溃边界可能重复计费，不能承诺远程 exactly-once。保存 invocation_id 与 unknown outcome。
- [x] 多代理检查点分两步：先保证整次执行的持久状态；B3 接入审核恢复；再覆盖章节结果。未覆盖节点明确展示恢复粒度，不能把重新启动整条图称为节点恢复。

**验收**：实际使用 `tests/runtime/test_checkpoint_resume.py`、`tests/integration/test_research_stage_resume.py`、`tests/backend/test_task_leases.py` 和前端事件投影脚本；对各阶段注入故障，验证已完成阶段复用、输入/配置/checksum 不兼容、旧 token 拒绝和 attempt 草稿重置。未结束 invocation 的结果保持未知，不承诺不重复计费。

### A5. 持久事件回放与连接恢复

**涉及源码**：新增 `backend/server/tasks/events.py`；修改 `backend/server/server_utils.py`、`backend/server/websocket_manager.py`、`frontend/nextjs/hooks/useWebSocket.ts`；新增 `frontend/nextjs/hooks/useResearchTask.ts`。

**修改步骤**：

- [x] 新 WS 命令使用 JSON envelope：`{version:1,type:'subscribe',research_id,after_seq}`；保留单一 receive loop。旧 `start ...` 映射为创建任务再订阅。
- [x] 服务端事件包含 `version/research_id/attempt_id/seq/type/created_at/payload`；统一 `task.started`、`stage.completed/restored`、`report.delta`、`report.ready`、`task.failed`、`export.*`。审核事件在 B3 接入。
- [x] 订阅始终按数据库 seq 补读，没有依赖易失通知的丢事件窗口。浏览器用 HTTP 轮询，WS v1 也使用同一事件存储。
- [x] 客户端记录 last_seq，重连只订阅，不重新提交研究；按 `(research_id,seq)` 去重，忽略旧 attempt 的已作废正文。
- [x] 事件保留期结束返回 `resync_required` 和报告/状态快照；客户端先恢复快照再继续订阅。分页重放和有界发送队列防止慢连接拖垮 worker。
- [x] token delta 可批量持久化，阶段/终态必须可靠落库；最终全文与 hash 是正文权威结果。UI 从终态结束 loading，不再依赖 path。

**验收**：实际使用 `tests/backend/test_task_websocket.py`、`test_task_leases.py`、`tests/integration/test_persistent_websocket.py`、`frontend/nextjs/tests/task-events.cjs` 与隔离浏览器；覆盖断线、重复/乱序、新尝试、游标过期、失败终态与真实页面刷新。hook 组件套件尚未引入，不虚构通过记录。

### A6. 正文持久化与导出解耦

**涉及源码**：新增 `backend/server/exports/service.py`、`backend/server/exports/worker.py`；修改 `backend/server/server_utils.py::generate_report_files/send_file_paths`、`backend/server/app.py::write_report`、`multi_agents/agents/publisher.py`、`frontend/nextjs/components/ResearchBlocks/AccessReport.tsx`。

**修改步骤**：

- [x] 正文、版本和 `report.ready` 先提交；随后创建 PDF/DOCX/MD 导出任务，每种格式独立重试。
- [x] 幂等键使用报告版本、format 和 renderer_version，内容变化生成新版本；导出只读取冻结正文，不重新跑研究或修改正文。
- [x] PublisherAgent 产出最终 Markdown/layout 和元数据，服务端统一导出；独立 CLI 场景保留显式导出适配，避免两边重复生成文件。
- [x] 提供 GET 导出列表与 POST 单项重试接口，旧 path 事件保留为兼容通知；文件名使用服务端 ID，下载校验产物归属与版本。
- [x] 导出结果更新对应任务视图但不覆盖 task succeeded；M1 仅导出冻结终稿，执行成功不表示审核通过，不标为“已验证报告”。

**验收**：新增 `tests/backend/test_export_jobs.py`；模拟 PDF 原生库不可用、DOCX 成功、重复重试、修改正文后旧导出仍可定位。Linux 容器执行真实 PDF/DOCX 小文档导出，不调用研究模型。

### A7. 服务端历史写入与部署切换

**涉及源码**：修改 `frontend/nextjs/hooks/useResearchHistory.ts`、`frontend/nextjs/app/page.tsx` 完成 effect、Next reports 代理、`docker-compose.yml`、`.env.example`、`.gitignore`、`.dockerignore`、`docs/deployment.md`、`docs/migration.md`。

**修改步骤**：任务完成由服务端写报告；前端只刷新缓存，客户端手动保存作为单独导入路径。保留 localStorage 的旧历史导入入口，不让过期本地记录覆盖新服务端版本。Compose 挂载数据库、来源快照和导出目录；启动检查可写性与 schema；提供迁移 dry-run、备份、恢复说明。新库、运行轨迹、评测结果、报告与缓存全部忽略提交。

**验收**：浏览器在报告完成前关闭仍有历史；容器替换挂载同一数据后可见状态与报告；旧历史重复导入不会复制。对比既有 `docs/validation.md` 的检查范围，但不能沿用其历史通过结论。

<a id="work-b"></a>

## 4. 工作包 B：统一入口、人工反馈与审核语义

### B1. 前端统一创建任务

**涉及源码**：修改 `frontend/nextjs/app/page.tsx::handleDisplayResult/handleMobileDisplayResult`、`frontend/nextjs/components/layouts/MobileLayout.tsx`、`frontend/nextjs/components/mobile/MobileHomeScreen.tsx`、`frontend/nextjs/hooks/useResearchHistory.ts`；新增 `frontend/nextjs/lib/researchClient.ts`、`frontend/nextjs/app/api/research/route.ts`、`frontend/nextjs/app/api/research/[id]/route.ts` 及 cancel/resume/feedback 代理。

**修改方式**：抽出 `startResearch(request)`，桌面和移动均调用 POST `/api/research` 并订阅同一事件；用返回 ID 建立状态，删除移动端自造 ID 和“以空报告聊天代替研究”的路径。研究后的追问仍使用 chat。Next 服务端代理沿用已存在的内部 BACKEND_URL 解析规则；浏览器直连 WS 沿用公开地址规则，不能把容器内部地址传给浏览器。

**验收**：同一输入在桌面和移动生成相同请求字段，覆盖来源、tone、domain filters、MCP 和报告类型；刷新后不重复创建。新增 `frontend/nextjs/tests/e2e/research-entry.spec.ts`。

### B2. 静态 UI、嵌入 UI 和旧协议兼容

**涉及源码**：修改 `frontend/scripts.js`、`frontend/index.html`、`frontend/nextjs/src/TraceableDeepResearcher.tsx`、`frontend/nextjs/components/Langgraph/Langgraph.js`、`backend/server/server_utils.py`。

**修改方式**：静态 UI 共享任务协议；嵌入 UI 修正 `/chat` 与 `/api/chat` 差异，并支持 task ID 恢复。旧 start/chat 字符串由入口适配器转换，不散落在业务层。直连外部 LangGraph 的旧分支保持显式选择和能力提示，未来需通过专用 runner 才纳入本地任务管理。

**验收**：新增 `tests/backend/test_legacy_protocol_adapter.py`；三种 UI 的创建/失败/完成契约相同，旧协议仍能收到最终正文和兼容 path。不在本轮删除旧入口。

### B3. 人工审核改为持久等待和单次消费

**涉及源码**：修改 `multi_agents/agents/human.py::review_plan`、`multi_agents/agents/orchestrator.py::run_research_task`、`multi_agents/memory/research.py`、`backend/server/server_utils.py::handle_human_feedback`；新增 `backend/server/tasks/reviews.py`。

**修改步骤**：

- [ ] HumanAgent 通过 ReviewInbox 创建请求，包含 review_id、plan_version/hash、可选操作和截止时间；移除直接读取 websocket、打印后吞异常的逻辑。
- [ ] 持久化完整待审状态，保存 graph checkpoint 后让出执行槽位。使用 LangGraph checkpointer/interrupt-resume 的适配层，具体接口在实施时按锁定安装版本验证；不能只用内存 Future 假装可重启恢复。
- [ ] POST `/api/research/{id}/feedback` 接收 `review_id/action/comment/target_version/response_id`，action 为 approve/revise/reject；CAS 更新 pending→responded，并投递恢复任务。
- [ ] 重复 response_id 返回原结果；不同响应竞争返回 409；错误任务、旧计划版本或已过期 review 返回明确错误。
- [ ] 断线或超时不能隐式 approve。默认保留待审状态；到期进入 interrupted/review_timeout，可重新发起新 review。`include_human_feedback=false` 明确标记 not_requested。
- [ ] 旧 CLI 的输入方式作为单独实现保留，并显式把旧约定的 `no` 转成 approve；网络服务中不调用阻塞 input。

**验收**：新增 `tests/backend/test_review_inbox.py`、`tests/test_human_review_resume.py`；覆盖重启后审批、重复提交、两个标签页竞争、超时、旧版本审批、审批取消竞争，以及 WS 全程仅一个接收者。

### B4. 审核 UI 完整状态

**涉及源码**：修改 `frontend/nextjs/components/HumanFeedback.tsx`、`frontend/nextjs/app/page.tsx`、`frontend/nextjs/hooks/useWebSocket.ts`、`frontend/nextjs/types/data.ts`；新增 `frontend/nextjs/components/research/ReviewStatus.tsx`。

**修改方式**：展示计划版本、修改意见输入和 approve/revise/reject；提交中禁用按钮，服务端确认后更新状态，失败保留输入。刷新后从任务状态恢复审核卡片；移动端复用同一卡片。修正 human question 的布尔类型与实际文本不符问题。报告同时显示执行完成和审核结论，禁止一个绿色“完成”掩盖未通过审核。

**验收**：新增前端 `frontend/nextjs/tests/e2e/human-review.spec.ts`，覆盖移动端审批、刷新恢复、过期反馈和请求失败重试。

### B5. 修订上限不再转成通过

**涉及源码**：修改 `multi_agents/agents/orchestrator.py::_route_human_feedback/_route_fact_check`、`multi_agents/agents/editor.py::_route_draft_review`、`multi_agents/agents/plan_review.py`、`multi_agents/agents/fact_review.py`、`multi_agents/agents/draft_review.py`、`multi_agents/agents/fact_checker.py`、`multi_agents/agents/reviewer.py`、`multi_agents/memory/research.py`、`multi_agents/memory/draft.py`。

**修改步骤**：

- [ ] 路由结果改为显式的 accept/revise/needs_review/reject；超限转 needs_review，写明 revision_limit，不吞异常后 accept。
- [ ] 审核结果采用结构化 verdict、issue_id、严重性、目标 claim/section、依据和建议；解析失败为 unknown/needs_review，不能等同“没有问题”。
- [ ] 定义计数：initial draft 不算修订；每次完成一次重写计数加一；最多 N 次重写，第 N 次仍不通过就暂停，避免原有 `>` 边界语义模糊。
- [ ] Graph 增加暂停/结束分支；needs_review 不进入标记已审批的 publisher 分支。若配置允许草稿交付，明确输出 draft 与未解决问题。
- [ ] 记录人工 override 的人类决定和版本，保留原自动核查发现；override 不更改事实支持标签。

**验收**：更新现有 `tests/test_multi_agents_revision_caps.py`、`tests/test_multi_agents_plan_revisions.py`、`tests/test_multi_agents_fact_revisions.py`、`tests/test_multi_agents_draft_revisions.py`、`tests/test_multi_agents_route_bindings.py` 和 `tests/test_none_accept_sentinels.py`；新增跨节点测试证明超限时 publisher 的 verified 分支未被调用。

### B6. 入口闭环的统一回归

**涉及源码**：新增 `frontend/nextjs/playwright.config.ts`、`frontend/nextjs/tests/e2e/research-lifecycle.spec.ts`、`frontend/nextjs/tests/e2e/export-retry.spec.ts`；修改 `frontend/nextjs/package.json` 与 `frontend/nextjs/package-lock.json` 增加测试脚本/依赖。

**修改方式**：用离线 fake runner 驱动真实 API 与 UI，测试普通/详细/deep/多代理入口、断网重连、终态、历史、审核、导出重试。组件层可使用 Vitest/Testing Library，浏览器层 Playwright；这些是拟新增依赖，实施时再锁定版本。浏览器自动化使用临时数据库和固定端口，不访问真实供应商。

**验收**：桌面与约 390px 移动视口均完成同一条任务；`npm run build` 和新增测试脚本通过，旧静态页面离线 smoke 通过。

<a id="work-c"></a>

## 5. 工作包 C：关键结论到原文证据的最小追溯链路

### 5.1 首版边界与数据设计

首版优先打通普通报告的 web/local 来源，随后将 detailed、deep、multi_agents、MCP 接入相同契约。凡未覆盖的来源/执行模式，明确标记 `lineage_unavailable`，不能以“没有发现无效引用”推导整篇报告可追溯。只有全部约定路径完成接入，才将 C 工作包记为完成。

“可定位到原文”“原文支持结论”“来源本身可靠”是三个不同维度。哈希与坐标仅证明内容一致性，不证明事实真实性；语义核查标签还需记录核查器、人类审核与版本。

新增数据表由 `backend/server/storage/migrations/002_lineage.sql` 管理：

| 对象 | 字段与约束 | 设计目的 |
|---|---|---|
| `source_snapshots` | snapshot_id、research_id、source_kind、原始/最终 URL 或本地文档 ID、fetched_at、media_type、raw_blob_hash（可空）、canonical_text_hash、extractor_version、可用状态 | 同一个 URL 不同时刻的内容成为不同快照；没有原始响应时不能声称保留了原始网页 |
| `evidence_spans` | evidence_id、snapshot_id、start_char、end_char、quote、quote_hash、page_number（可空） | quote 必须等于冻结 canonical_text 的指定切片；同一快照可有多个片段 |
| `claims` | claim_id、report_id、report_version、section_id、text、text_hash、importance、kind | 原子论断关联具体报告版本；kind 区分 fact/inference/opinion |
| `claim_evidence` | claim_id、evidence_id、relation、support_status、verifier_version、reason、checked_at | relation 为 supports/contradicts/background；support_status 为 supported/partial/unsupported/unknown |
| `citations` | report_id、version、citation_id、claim_id、evidence_id、render_anchor | Markdown/HTML 引用从结构化关系生成 |
| `lineage_checks` | report_id、version、report_hash、manifest_hash、coverage、structural_valid、审核引用、错误列表 | 发布与导出前核验；不能继承另一版本的通过记录 |

canonical_text 的规则固定为 UTF-8 解码后标准化换行、保留剩余字符；用版本化规范记录任何 Unicode/空白处理。字符坐标统一为 Unicode code point 的半开区间 `[start,end)`。前端不要直接用 JavaScript UTF-16 下标切片，API 返回已经校验的 quote 和前后文；中文、emoji、CRLF 必须有回归样例。PDF 坐标是抽取文本坐标，页码是额外定位，首版不假称具备 PDF 版面框坐标。

### C1. 定义证据模型与内容寻址存储

**涉及源码**：新增 `traceable_deep_researcher/evidence/models.py`、`traceable_deep_researcher/evidence/protocols.py`、`traceable_deep_researcher/evidence/normalization.py`；新增 `backend/server/evidence/repository.py`、`backend/server/evidence/blob_store.py` 和上述 migration；修改 `traceable_deep_researcher/runtime/contracts.py` 的 RunContext 增加可选 EvidenceSink。

**修改步骤**：

- [ ] 定义 Snapshot、EvidenceSpan、Claim、Citation、LineageCheck，所有序列化带 schema_version；规范化算法也带独立版本。
- [ ] blob 路径使用服务端计算的 hash，临时写入后原子替换；相同内容复用 blob，但保留各次来源观测记录。
- [ ] repository 在写 evidence 时验证快照存在、坐标合法和 quote 相等；错误返回结构化 failure，不写入“已验证”标记。
- [ ] 严格证据模式下存储失败中断当前证据阶段并保留任务；宽松模式可交付未验证草稿，但必须携带 provenance warning。
- [ ] 增加 `tests/evidence/test_snapshot_store.py`、`tests/evidence/test_evidence_spans.py`：覆盖同 URL 内容变化、同内容不同 URL、中文/emoji、损坏 blob、无效坐标和重复片段。

**验收**：已持久化片段的 hash/坐标校验率必须为 100%；此项只表示结构正确，不计入语义正确率。

### C2. 在筛选前保存所有进入研究的来源

**涉及源码**：修改 `traceable_deep_researcher/skills/browser.py::browse_urls`、`traceable_deep_researcher/skills/researcher.py::_get_context_from_initial_results/_process_sub_query/_execute_mcp_research_for_queries/_combine_mcp_and_web_context`、`traceable_deep_researcher/agent.py::add_research_sources/quick_search`、`traceable_deep_researcher/actions/web_scraping.py`、`traceable_deep_researcher/mcp/research.py::_process_tool_result`、`traceable_deep_researcher/document/document.py`、`traceable_deep_researcher/document/langchain_document.py`、`traceable_deep_researcher/document/online_document.py`、`traceable_deep_researcher/document/azure_document_loader.py`；新增 `traceable_deep_researcher/evidence/ingestion.py`。

**修改步骤**：

- [ ] 新增统一 `ingest_sources(pages, run_context)` 入口，返回携带 snapshot_id 的页面记录；放在筛选/摘要前，浏览器路径和不需抓取的检索器路径均调用。
- [ ] 对初次规划结果、用户 source_urls、本地文档、向量库返回、MCP 内容分别检查接入点；同一段内容重复进入时复用快照，不丢掉 query/span 关系。
- [ ] 对 Tavily 等直接提供 raw_content 的来源，记录 `provider_text`；只有取得完整页面才标记为 page snapshot。搜索摘要标记 snippet，不能当成原网页全文。
- [ ] local/PDF 记录文件内容 hash 与解析器版本；不持久化无必要的本地绝对路径。LangChain Document metadata 保留文档 ID、页码和 snapshot_id。
- [ ] MCP 无稳定 URL 的内容使用服务器/工具/调用 ID 作为来源定位，保留工具结果快照，不生成虚构 HTTP 链接；仅保存允许的结果与脱敏参数。
- [ ] 抓取失败单独记录失败观测，空文本不生成有效证据。来源输出是数据，不允许其中的指令改变任务或审核规则。

**验收**：新增 `tests/evidence/test_source_ingestion.py`；扩展现有 `tests/test_retriever_requires_scraping.py`、`tests/test_planning_sources.py`、`tests/test_document_loader_metadata_source.py`。web/local/MCP/检索器直出均证明“先快照，后筛选”，失败记录能解释证据缺口。

### C3. 让上下文筛选保留片段身份

**涉及源码**：修改 `traceable_deep_researcher/context/select.py::select_context`、`traceable_deep_researcher/context/retriever.py`、`traceable_deep_researcher/context/lexical.py::_chunks/select`、`traceable_deep_researcher/context/jev_filter.py::_chunks/rank`、`traceable_deep_researcher/context/compression.py`、`traceable_deep_researcher/skills/context_manager.py`；新增 `traceable_deep_researcher/context/bundle.py`、`traceable_deep_researcher/evidence/chunking.py`。

**修改步骤**：

- [ ] 定义 ContextBundle，包含 selected spans、展示文本、filter_version、fallback_reason、token/字符统计；为 select_context 增加内部结构化入口 `select_context_bundle`。
- [ ] 原 select_context 保留返回字符串，调用 bundle 的 renderer，保证报告聊天和现有核心调用兼容。
- [ ] 分块时从冻结文本生成起止坐标，保留 metadata；keyword/Jev/embeddings 返回片段对象后再格式化。none 和短文本直通也必须生成片段身份。
- [ ] embeddings/Jev 失败回退 keyword 时沿用同一快照集合并记录策略变化。不能先丢失坐标，再用模糊匹配伪造精确证据。
- [ ] 摘要/改写内容标为 derived context，关联原始片段集合；若无法映射到准确原文，就不能作为原文 quote。向量库文档缺少来源文本时标记 unavailable。
- [ ] 写作 prompt 输入包含稳定 evidence_id；context token 裁剪在片段边界执行，或生成新的合法子片段，不从中间截断却沿用原范围。

**验收**：新增 `tests/evidence/test_context_lineage.py`；扩展 `tests/test_lexical_context_filter.py`、`tests/test_jev_context_filter.py`、`tests/test_context_compressor_source_url.py`、`tests/chat/test_chat_agent_rag_path.py`。每个支持的过滤策略均保留可验证坐标；旧字符串接口行为不变。

### C4. 写作时绑定关键结论，而非事后猜测引用

**涉及源码**：修改 `traceable_deep_researcher/skills/writer.py::write_report`、`traceable_deep_researcher/actions/report_generation.py::generate_report`、`traceable_deep_researcher/prompts.py`、`traceable_deep_researcher/agent.py::write_report/add_references`；新增 `traceable_deep_researcher/evidence/claims.py`、`traceable_deep_researcher/evidence/rendering.py`。

**修改步骤**：

- [ ] 为启用 lineage 的任务增加版本化写作 schema：section/block、原子 claim、evidence_ids、kind；普通未启用任务保持旧输出路径。
- [ ] 首版将数字、日期、比较结果、因果判断和主要结论列为必须绑定的关键论断；定义规则及遗漏审计，不只让模型自己选择容易支持的句子。
- [ ] 对模型返回的 evidence_id 使用白名单校验，未知 ID 进入未支持列表；禁止根据生成的 URL 反推“已存在证据”。
- [ ] 将写作产物分为流式草稿与结构化最终版本。最终通过 schema 校验后由 renderer 生成 Markdown、引用编号与锚点，再发送 report.ready。
- [ ] 结构解析失败允许一次有预算的修复；仍失败则保留未验证草稿和错误，不把纯文本当成成功的结构化证据报告。
- [ ] detailed 合并章节、deep 汇总、multi_agents writer/reviser 每次改写都生成新的 claim/version 映射；保留原 evidence_id，重新验证新论断，不能沿用旧 approval。

**验收**：新增 `tests/evidence/test_claim_generation.py`、`tests/evidence/test_citation_rendering.py`；固定模型输出覆盖虚构 ID、同一结论多证据、一个证据多结论、重排章节、报告修订、解析失败。流式草稿不能出现最终“已验证”徽标。

### C5. 分离结构校验、语义核查和发布门槛

**涉及源码**：新增 `traceable_deep_researcher/evidence/validation.py`、`traceable_deep_researcher/evidence/verification.py`、`traceable_deep_researcher/evidence/publication.py`；修改 `multi_agents/agents/fact_checker.py`、`multi_agents/agents/writer.py`、`multi_agents/agents/reviser.py`、`multi_agents/agents/publisher.py`，以及 A6 的 ExportService。

**修改步骤**：

- [ ] 结构校验检查 snapshot/blob hash、字符范围、claim/evidence 外键、报告 hash、引用和当前版本一致性；结构无效必须阻止 verified 发布。
- [ ] 语义核查每次只比较一个原子 claim 与明确的证据集合，返回 supported/partial/unsupported/unknown，并记录核查模型/规则/prompt 版本。
- [ ] 对多证据共同支持、冲突证据、日期版本冲突分别记录；“引用网址存在”不能替代支持性判断。
- [ ] 将现有 FactCheckerAgent 接到结构化核查结果；未实施 lineage 的旧报告保留独立 legacy review 状态，不能假装有逐论断核查。
- [ ] 发布策略分 draft 与 verified：草稿允许未解决问题并展示状态；verified 要求约定关键论断覆盖、结构有效、没有未处理的高严重性问题，以及对应版本审核通过。
- [ ] 正文或引用任一变更都产生新版本，使既有 publication check 失效；导出任务读取同一冻结 report hash 与 manifest hash。

**验收**：新增 `tests/evidence/test_lineage_validation.py`、`tests/evidence/test_publication_gate.py`；篡改正文/快照/证据关联均不能发布为 verified。离线假核查器验证流程，真实语义正确率由 D 工作包评测，不能用 mock 测试证明。

### C6. API 与前端原文证据查看

**涉及源码**：新增 `backend/server/evidence/routes.py`、`frontend/nextjs/components/research/EvidenceDrawer.tsx`、`frontend/nextjs/components/research/ClaimBadge.tsx`、`frontend/nextjs/app/api/reports/[id]/versions/[version]/claims/route.ts`、`frontend/nextjs/app/api/reports/[id]/versions/[version]/evidence/[evidence_id]/route.ts`；修改 `frontend/nextjs/components/ResearchBlocks/Report.tsx`、`frontend/nextjs/components/Task/Report.tsx`、`frontend/nextjs/components/ResearchBlocks/Sources.tsx`、`backend/server/app.py` 注册路由。

**修改方式**：GET `/api/reports/{id}/versions/{version}/claims` 返回论断索引；GET 同版本的 `/evidence/{evidence_id}` 返回经过校验的 quote、前后文、来源标题、URL、抓取时间和支持关系；代理添加对应 claims 和 evidence/[evidence_id] 路由。UI 点击 claim 打开抽屉，显示“原文一致性”和“语义支持”两个状态，不把 model score 呈现成人类确认。API 校验请求的报告确实引用该 evidence，不提供按任意文件路径读取原文的端点。

**验收**：新增 `tests/backend/test_evidence_routes.py`、`frontend/nextjs/tests/e2e/evidence-drawer.spec.ts`；覆盖中文长段、emoji、高亮、多来源、旧版本、无证据历史报告及移动端抽屉。原网页更新后仍显示任务当时的快照文本。

### C7. 各研究模式接入与证据生命周期

**涉及源码**：修改 `backend/report_type/detailed_report/detailed_report.py`、`traceable_deep_researcher/skills/deep_research.py`、`multi_agents/agents/researcher.py`、`multi_agents/agents/editor.py`、`multi_agents/agents/writer.py`、`deep_agents/tools.py`、`backend/server/report_store.py`；新增 `backend/server/evidence/retention.py`。

**修改方式**：子研究继承 research_id、EvidenceSink 和 parent_span，但每个子节点独立 span/section ID；合并前校验引用归属。deep_agents 只在显式传入运行上下文时提供同样追踪，保持独立脚本入口。删除报告采用 tombstone 和引用计数，保留期内可恢复；只有没有存活报告引用的 blob 才清理。过期删除快照后把 lineage 标为 unavailable，不能保留 verified 外观。

**验收**：新增 `tests/evidence/test_nested_research_lineage.py`、`tests/evidence/test_evidence_retention.py`；覆盖并发章节、同来源复用、报告版本引用、删除与导出竞争。任务级评测按模式列出覆盖率，不以普通报告通过代替其他模式通过。

<a id="work-d"></a>

## 6. 工作包 D：任务评测与智能体评测

### 6.1 两层评测各自回答什么

**任务评测**：给定问题、来源条件、预算与输出要求，整次研究是否可靠交付、是否回答完整、关键论断是否有依据、成本与耗时是否可接受。对象是一次完整任务及其报告/轨迹。

**智能体评测**：固定某个节点的输入、工具环境和预算，判断该节点是否完成职责，并通过替换节点对照其对最终任务的影响。对象包括 ResearchConductor 等单代理内部技能，也包括 planner/researcher/writer/reviewer 等多代理节点；不只按 Python 类名统计调用次数。

测试与评测分工：单元/集成测试检验确定性工程约束；评测检验模型行为和研究效果。离线 fake LLM 的全链路通过率只能证明工程流程，不能称为真实研究成功率。

### 6.2 复用现有评测与需要修正的语义

| 当前源码 | 已有能力 | 本轮修改 |
|---|---|---|
| `evals/quality_eval/base.py`、`evals/quality_eval/suite.py` | EvalSample、MetricResult、可组合指标 | 扩展轨迹/证据引用与结果状态，保持旧构造兼容；异常和主动跳过分开 |
| `evals/quality_eval/metrics.py::citation_faithfulness` | 正文与参考文献的域名集合一致性 | 保留为 legacy 结构性指标，命名/元数据注明 domain-reference alignment；新增精确 claim-evidence 支持指标，不能叫真实引用精确率 |
| 同文件 source_authority/diversity | 域名启发式、域名多样性 | 作为描述性来源特征；不奖励堆砌域名，不将权威域名等同事实正确 |
| `evals/quality_eval/run_eval.py` | 生成报告后评分 | 拆分 generate/evaluate；当前关闭部分 LLM 指标仍会生成研究，不能称整个命令零成本 |
| `evals/quality_eval/benchmark.py` | 多配置比较，临时 monkeypatch 收集子研究 | 用 RunContext 轨迹替代全局 monkeypatch 和进程环境修改，防止并发配置互相污染 |
| `evals/simple_evals/run_eval.py`、`evals/simple_evals/simpleqa_eval.py` | 有标准答案的短事实评测 | 经 adapter 接入任务 suite；保留数据许可/归属；不代表长报告能力 |
| `evals/hallucination_eval/evaluate.py` | 可选模型裁判 | 作为可选 scorer，固定输入快照与裁判版本，异常单列 |
| `evals/context_filter/collect.py/replay.py/judge.py` | 固定页面后比较筛选策略 | 复用 frozen inputs；注意 replay 写报告、Jev/embedding 和 judge 仍可能联网，不能因“回放”二字就认定离线 |
| `deep_agents/benchmark.py/report_benchmark.py/recency_benchmark.py/hybrid_benchmark.py/breadth_benchmark.py` | 独立编排的工具/报告/时效/混合来源实验 | 输出统一 manifest，经 optional adapter 加入；缺依赖明确 skipped，不混入默认离线启动 |

### D1. 统一样本、运行清单和输出结构

**涉及源码**：新增 `evals/framework/models.py`、`evals/framework/manifest.py`、`evals/framework/datasets.py`、`evals/framework/results.py`；修改 `evals/quality_eval/base.py`、`evals/quality_eval/suite.py`；新增 `evals/task_eval/__init__.py`、`evals/agent_eval/__init__.py`。

**修改步骤**：

- [x] TaskCase 定义 case_id、dataset_version、split、query、as_of、report_type、source_policy、source_bundle、requirements、gold_facts、gold_evidence、budget、faults、tags。
- [ ] AgentCase 定义 node_kind、input_artifact、allowed_tools、tool_fixtures、expected_constraints、gold_output_refs、budget；输入只包含该节点当时能看到的内容。
- [ ] RunManifest 保存 commit、dirty diff hash、Python/依赖摘要、模型/采样参数、prompt hash、配置 hash、dataset hash、source snapshot hash、seed、judge 版本和运行模式。
- [x] 结果状态定义 passed/failed/error/skipped/not_applicable；metric score 可空，保留 reason、分母、样本数、trace_refs。失败不能进入“跳过后平均分更高”的路径。
- [x] 保存每例结果和最终聚合；输出到忽略的 `evals/results/<run_id>/`，不把生产报告和凭据写入 git。仓库仅保存小型自编 fixtures、标注 schema 和静态基准配置。

M0 补充：AgentCase 已实现可见输入投影、工具白名单和约束，工具 fixtures 通过 replay_key 关联独立文件；manifest 已记录离线 fixture 配置与源码/输入/数据指纹。真实模型采样参数、裁判配置及完整运行适配尚待接入，相关完整步骤保留未勾选。

**验收**：新增 `tests/evals/test_eval_contracts.py`、`tests/evals/test_result_aggregation.py`；相同输入 manifest 可比，配置不同时明确差异，缺少裁判数据不得默认记为 1 分。

### D2. 建立首批任务集、节点集和标注流程

**涉及源码**：新增 `evals/datasets/task_cases.v1.jsonl`、`evals/datasets/agent_cases.v1.jsonl`、`evals/datasets/source_bundles/`、`evals/datasets/rubrics/`、`evals/datasets/dataset_manifest.json`、`evals/datasets/README.md`；复用现有 SimpleQA 样本和可合法使用的本地合成资料，新增 `scripts/validate_eval_dataset.py`。

**首批规模建议**：80 个任务，作为覆盖起点而非统计充分性承诺；每类 10 个：事实核对、多来源比较、长篇综述、时间版本冲突、本地文档、web/local 混合、证据不足/矛盾、工具与运行故障。语言标签至少覆盖中文与英文，报告模式与 MCP 通过标签做成对覆盖，避免全笛卡尔积导致成本失控。

按来源家族/主题分组分割为开发集 40、校准集 20、保留集 20，不能同一问题改写后跨集。缺乏授权的真实资料不进入可提交 fixtures；允许本机快照但只在本地 manifest 引用。时间敏感样例固定 as_of 和来源日期，不在离线测试中使用“今天”。

节点集先按 planner、retriever/browser、context selector、writer、reviewer/fact checker、reviser、MCP tool selector、orchestrator 八类，每类至少 10 个输入；添加“工具返回格式错误、空结果、冲突证据、引用不存在、超时、预算不足”等反例。

**执行步骤**：

- [ ] 为每个任务预先编写 requirement 列表及权重、可接受答案/拒答条件、支持与反驳证据坐标；不要从候选模型答案反向生成唯一评分标准。
- [ ] 每个需要语义判断的校准样例由两位标注者独立标注，记录争议与裁决。首轮可从小批开始，但必须报告实际双标数量与一致率。
- [x] validator 检查 ID 唯一、split 无来源泄漏、引用文件/hash/坐标有效、gold 不出现在被测 agent 可见字段。
- [ ] 保留集冻结版本，prompt 调优只看开发/校准集；发布评测使用保留集，之后新增版本而非回填修改成绩。

**验收**：新增 `tests/evals/test_dataset_validation.py`；故意重复 ID、泄漏 gold、缺源文件和坐标越界都失败；每例可追溯到标注版本。

### D3. 三种运行模式与确定性工具回放

**涉及源码**：新增 `evals/framework/providers.py`、`evals/framework/replay.py`、`evals/framework/network_guard.py`、`evals/framework/budget.py`、`evals/task_eval/run.py`、`evals/task_eval/adapters.py`；修改 `evals/quality_eval/run_eval.py`、`evals/quality_eval/benchmark.py`、`evals/context_filter/collect.py`；生产侧修改 `traceable_deep_researcher/runtime/tracing.py`、`traceable_deep_researcher/utils/llm.py::create_chat_completion`、`traceable_deep_researcher/utils/costs.py` 与 `traceable_deep_researcher/mcp/research.py` 的可选追踪钩子。

| 模式 | 执行方式 | 能得出的结论 |
|---|---|---|
| offline | 固定工具结果与模型结果，禁用外网；可对冻结报告做确定性评分 | 工程约束、结构指标、评分器正确性和回放一致性 |
| frozen-tools | 固定来源与工具环境，实际运行指定模型；可调用语义裁判 | 模型/提示词/节点策略对同一证据条件的效果，仍会产生模型费用 |
| live | 真实搜索/抓取/模型/裁判并记录快照 | 当前环境下端到端效果；受网页和供应商变化影响 |

**执行步骤**：

- [x] ToolReplay 按 tool name、规范化参数、调用上下文和 fixture key 匹配；缺少 fixture 立即报错，禁止回退到真实网络。可重复查询定义可重放次数，不依赖不稳定的并发到达次序。
- [ ] 旧行为轨迹适合回归回放；比较新规划策略时需要独立的可查询冻结语料工具环境，不能只提供旧策略访问过的请求，否则会偏袒旧策略。
- [x] offline 在 runner 内安装网络阻断，不能只设置 TDR_BLOCK_NETWORK 却依赖仅 pytest 才执行的 conftest；只对 UI 集成允许明确的 loopback 地址。
- [ ] 模型和检索器以实例注入，禁止 benchmark 对全局类/环境变量打补丁；必要的旧适配器放独立进程，退出后状态不污染其他配置。
- [ ] 预算包括 task、judge、retry 三部分；达到预算停止新调用，保存已完成样例和未执行原因。未知供应商费用记 unknown，并以调用/token 上限兜底。
- [ ] run 与 score 分开：可只评分已有产物；在线模式必须显式 mode 和正数预算，默认 offline，不能因机器已有 API key 就自动联网。

**验收**：新增 `tests/evals/test_offline_guard.py`、`tests/evals/test_tool_replay.py`、`tests/evals/test_eval_budget.py`；离线缺 fixture 时真实 provider 调用数为零，两个并发配置互不影响，评分既有结果不重新研究。

### D4. 任务级指标与统计口径

**涉及源码**：新增 `evals/task_eval/metrics.py`、`evals/task_eval/suite.py`；修改 `evals/quality_eval/metrics.py`、`evals/quality_eval/suite.py`，通过 adapter 复用现有确定性函数。

| 指标 | 定义/分母 | 依据与限制 |
|---|---|---|
| 交付成功率 | 满足 required artifacts/终态要求的任务数 ÷ 全部实际启动任务数 | 超时和执行错误计失败；未启动单列。标明 offline 还是模型实跑 |
| 需求覆盖率 | 满足的预标注 requirement 权重和 ÷ 总权重 | 评测 requirement 固定；不能只看生成提纲自评 |
| 事实正确率 | 正确回答的 gold facts ÷ 所有应回答 gold facts | 分开统计错误、拒答和缺失；有矛盾或无答案样例按规定拒答评分 |
| 关键论断支持覆盖率 | 有有效原文且被判 supported 的关键论断数 ÷ 所有审计发现的关键论断数 | 分母不只包含模型自报 claims；遗漏的关键事实也进入分母 |
| 引用支持精确率 | 确实支持所绑定 claim 的引用关系数 ÷ 已给出的引用关系数 | partial 单列，不混成 supported；无引用为 N/A，同时覆盖率不能满分 |
| 无依据/矛盾论断率 | unsupported 或 contradicted 关键论断数 ÷ 可核查关键论断数 | unknown 单列；样本为零不记完美分数 |
| 正确拒答率 | 在无可得证据样例中明确表达不足的任务数 ÷ 此类样例数 | 同时报告可回答样例的错误拒答率，防止“全拒答”刷分 |
| 来源与时效合规率 | 满足 source_policy/as_of 的任务数 ÷ 适用任务数 | 域名多样性另作描述性统计，不替代合规与正确性 |
| 恢复成功率 | 注入故障后在约定恢复粒度内成功的任务数 ÷ 可恢复故障案例数 | 单列重复远程调用、重复产物和丢失事件 |
| 审核泄漏次数 | 未通过却被发布为 verified 的任务数 | 确定性硬门槛必须为 0 |
| 成本与延迟 | 每任务 token/工具调用/已知费用、unknown 费用覆盖率、p50/p95 | 任务执行、人工等待、导出和评分成本分别统计；失败任务也计成本 |

**修改步骤**：实现每个指标的适用条件、分母和错误状态；给结构性指标构造手工可算的小例子；给语义指标保留原始 verdict、证据与裁判版本。先输出分维度表，不以一个平均总分掩盖工程失败或引用缺陷。

**验收**：新增 `tests/evals/test_task_metrics.py`；包括没有引用、全拒答、同域不同文章、未完成任务和缺少 judge 结果。已有域名引用指标可继续输出，但不得混入精确支持指标列。

### D5. 智能体级指标、节点回放与责任定位

**涉及源码**：新增 `evals/agent_eval/run.py`、`evals/agent_eval/adapters.py`、`evals/agent_eval/metrics.py`、`evals/agent_eval/suite.py`；修改以下节点注入 tracing/依赖，不改变默认研究策略。

| 节点与源码 | 冻结输入/环境 | 重点指标与故障样例 |
|---|---|---|
| `traceable_deep_researcher/skills/researcher.py::plan_research`、`multi_agents/agents/editor.py::plan_research` | query、初始资料、约束、预算 | 必要子问题覆盖、重复子问题率、计划可执行性；时限冲突/模糊需求 |
| `traceable_deep_researcher/skills/researcher.py::_process_sub_query`、`traceable_deep_researcher/skills/browser.py::browse_urls`、`multi_agents/agents/researcher.py` | 子问题、冻结搜索集合、可返回页面 | gold source recall@k、无效抓取率、重复调用率、内容保留；403/空页/错误 MIME |
| `traceable_deep_researcher/context/select.py` 及三个过滤器 | 相同页面、query、token 上限 | gold evidence recall、所选片段 precision、坐标保真、token 开销；长文噪声/中英混合 |
| `traceable_deep_researcher/skills/writer.py`、`traceable_deep_researcher/actions/report_generation.py`、`multi_agents/agents/writer.py` | 同一 ContextBundle 与提纲 | requirement coverage、无依据 claim、有效引用、格式遵循；证据冲突/证据不足 |
| `multi_agents/agents/reviewer.py`、`multi_agents/agents/fact_checker.py` | 人工植入问题的草稿与固定证据 | issue precision/recall、严重问题漏检率、错误放行率；虚构数字/失效引用 |
| `multi_agents/agents/reviser.py` | 草稿、issue_id、修改边界 | 指定问题修复率、新增问题率、正确内容保留率；只改措辞却不改事实 |
| `traceable_deep_researcher/mcp/tool_selector.py`、`traceable_deep_researcher/mcp/research.py` | 固定工具 schema 和返回 | 工具选择、参数合法率、调用结果利用率、无效循环；工具异常/返回注入指令 |
| `multi_agents/agents/orchestrator.py`、`multi_agents/agents/editor.py` | 固定节点输出、审核事件、预算 | 路由正确率、修订上限、取消传播、交接字段完整性；超限/重复反馈/节点失败 |

**执行步骤**：

- [ ] 每个 adapter 暴露统一 `execute(case, dependencies) → NodeRun`，NodeRun 包含 input/output refs、span tree、usage、errors；记录实际节点版本。
- [ ] 写作节点评测使用 gold context 与实际检索 context 两组：前者测写作上限，后者测实际交接损失。检索差造成的错误不要全归因给 writer。
- [ ] reviewer/reviser 使用预植入且标注的问题，统计 TP/FP/FN；不要只看模型自评“我已修复”。
- [ ] 固定其余节点，只替换一个候选节点，运行成对任务；比较该节点指标与最终任务指标，识别局部改善但全局退化。
- [ ] 对 planner/researcher 的新工具轨迹使用冻结语料环境，给相同预算和工具能力；不以“与旧轨迹完全一致”作为智能体质量要求。

**验收**：新增 `tests/evals/test_agent_adapters.py`、`tests/evals/test_agent_metrics.py`、`tests/evals/test_node_ablation.py`。一份评测报告能定位“来源未找到”“筛选丢证据”“写作添加断言”或“核查漏报”，无法定位时保留 unknown，不作强因果归因。

### D6. 校准语义裁判，防止评分器成为新误差来源

**涉及源码**：新增 `evals/framework/judges.py`、`evals/framework/judge_calibration.py`、`evals/datasets/rubrics/claim_support.v1.md`、`evals/datasets/rubrics/report_quality.v1.md`；修改 `evals/quality_eval/perturbation.py`、`evals/context_filter/judge.py`、`evals/hallucination_eval/evaluate.py`。

**修改步骤**：

- [ ] 裁判输入只包含问题、评分标准、候选结果和允许的证据；隐藏候选模型名与版本，候选正文/来源中任何指令按数据处理。
- [ ] claim support 使用结构化四类 verdict 和证据位置，设置 JSON/schema 失败状态；错误不默认为 supported 或 skipped。
- [ ] 对成对偏好运行 A/B 与 B/A，分歧记 tie/unstable；不把同一输出自评直接当客观结果。
- [ ] 在人工双标校准集计算 confusion matrix、macro-F1、严重无依据论断漏检率和一致率；裁判未达到校准门槛时只提供辅助结果，不能作为自动发布依据。
- [ ] 扩展现有 perturbation：删除证据、替换数字/日期、错配同域文章、添加不相关引用、改写正确结论、增加无用长段，检验指标是否按预期变化。
- [ ] judge 与生成模型配置分开记录；抽取 claim、判定支持、评分三步费用分别累计。独立裁判降低自评偏差，但不承诺消除偏差。

**验收**：新增 `tests/evals/test_judge_contract.py`、`tests/evals/test_metric_perturbations.py`；固定裁判响应可离线验证解析与聚合，真实裁判校准需单独模型运行和人工样本，结果明确注明规模与局限。

### D7. 对照实验、统计和发布门槛

**涉及源码**：新增 `evals/framework/compare.py`、`evals/framework/reporting.py`、`evals/baselines/baseline.v1.json`；修改 `evals/quality_eval/benchmark.py`。

**修改方式**：首轮基线记录本提交、脏工作区 hash 和实际参数，不能沿用上游历史成绩。新旧版本使用同一 case_id/source bundle/budget；随机策略至少做 3 次独立重复作为起点，按“问题”聚类计算区间，不把同题重复当成独立样本。输出 paired delta、bootstrap 区间、样本数、失败数、N/A 和裁判缺失率；样本不足时标记证据不足。线上来源变化的比较独立展示，不能混入冻结来源实验。

建议首版门槛，需在开发/校准集确定后冻结，不能看到保留集成绩后调低：

| 门槛 | 首版规则 |
|---|---|
| 确定性工程与完整性 | 离线关键生命周期案例全部通过；重复产物、错误审核放行、有效证据坐标错误均为 0 |
| 评测有效性 | 必需评分器错误数为 0；主动 skipped/N/A 必须有原因与分母，缺少必需结果不能通过门禁 |
| 任务质量不退化 | 关键支持覆盖率与事实正确率的 paired delta 95% 区间下界不低于 -0.02；此 2 个百分点为初始容忍建议，校准后冻结 |
| 成本/延迟 | 同环境成本中位数与 p95 执行耗时不超过冻结基线的 1.20 倍，除非有明确的质量收益记录和项目负责人接受 |
| 裁判可用性 | 校准集支持分类 macro-F1 建议至少 0.85；严重无依据样例漏检必须单列。未达标或区间过宽时转人工复核，不出自动通过结论 |

这些阈值是计划中的候选规则，不是已有实测值。20 个保留任务通常只能提供初步信号；区间过宽时应增加独立问题，不能把“未发现显著差异”解释为已经证明等效。

**验收**：新增 `tests/evals/test_paired_comparison.py`、`tests/evals/test_statistics.py`。使用手工可算的成对分数验证差值方向、失败任务计入、缺失样例拒绝直接配对，以及同题多次运行按问题聚类；固定 bootstrap seed 时结果可重复。对完全相同的两组数据，paired delta 为 0；对清单不兼容的数据拒绝输出“改进”结论，提供配置差异。

### D8. 接入 CI、结果报告和使用文档

**涉及源码**：修改 `.github/workflows/tests.yml`、`pyproject.toml`、`tests/conftest.py`、`evals/README.md`、`.gitignore`；新增 `.github/workflows/evals-offline.yml`、`.github/workflows/evals-live.yml`、`docs/evaluation.md`、`evals/run.py`、`evals/report.py`。

**修改步骤**：

- [ ] pytest 增加 offline/live 标记和集合校验；默认 PR 跑离线契约、结构指标、固定轨迹与新模块测试。现有状态污染测试保留隔离策略，不在本轮顺带大改全套测试框架。
- [ ] 新 evals-offline job 调用统一 CLI，阻断外网、验证 dataset、运行小型 smoke 集并校验硬门槛；生成 JSON 与本地 HTML/Markdown 汇总，作为有保留期的 CI artifact，不提交到仓库。
- [ ] 新 evals-live 仅 workflow_dispatch 手动触发，要求显式数据集、模型和预算；运行在可信分支，不给未信任 PR 凭据。任务需求没有包含安排定时付费运行，本轮不启用 schedule。
- [ ] 报告分别展示任务指标、节点指标、成本、失败详情和 claim/source 跳转；不需要首版新增线上评测管理后台。
- [ ] docs/evaluation.md 写明三种模式、真实费用来源、配置示例、数据标注、基线更新与不可比条件；纠正旧 README 中“零成本指标”等容易被理解为整次执行零成本的措辞。

**验收**：新增 `tests/evals/test_cli.py`、`tests/evals/test_release_gate.py`；CLI 用 exit code 0/1/2 区分通过/门槛失败/配置或执行错误。离线 CI 不需要模型密钥，错误评分器不能得到绿色通过。

## 7. 关键契约和实现样例

以下样例用于约束实现细节，尚未写入应用源码。数据库、HTTP、模型适配按前面逐文件步骤实现；不能把这些片段直接视为完整产品功能。每个工作包先完成对应的契约失败测试，再接入运行路径。

### 7.1 事件 envelope 与运行结果

建议新增 `backend/server/tasks/models.py` 中的基础事件模型；事件 payload 再按 event_type 用独立 Pydantic 模型验证。状态类沿用第 2.3 节枚举。

```python
from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

class TaskEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    version: int = 1
    research_id: str = Field(min_length=1)
    attempt_id: str | None = None
    seq: int = Field(ge=1)
    type: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any] = Field(default_factory=dict)
```

核心 `traceable_deep_researcher/runtime/contracts.py` 的结果类型使用标准库，不引入后端依赖：

```python
from dataclasses import dataclass, field
from typing import Any

@dataclass
class ResearchResult:
    report_markdown: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    context_refs: list[str] = field(default_factory=list)
    cost_summary: dict[str, Any] = field(default_factory=dict)
    review_status: str = "not_requested"
    warnings: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
```

`run_research` 的四个分支全部返回此类型；报告写入只能访问 `result.report_markdown`。禁止在 HTTP 层再次判断“这是字符串还是元组”。测试 `tests/backend/test_research_result_adapters.py` 必须以多代理输出完整字符串为输入，断言持久正文等于整篇文本而非第一个字符。

### 7.2 研究提交与订阅协议样例

拟新增请求/响应：

```json
{
  "request": {
    "task": "比较两份本地方案的成本与限制",
    "report_type": "research_report",
    "report_source": "local",
    "tone": "Objective",
    "source_urls": [],
    "document_urls": [],
    "query_domains": [],
    "mcp_enabled": false,
    "include_human_feedback": false,
    "budget": {"max_tool_calls": 20, "max_seconds": 300}
  },
  "response_202": {
    "research_id": "r-example-001",
    "status": "queued",
    "last_seq": 1,
    "status_url": "/api/research/r-example-001"
  },
  "subscribe": {
    "version": 1,
    "type": "subscribe",
    "research_id": "r-example-001",
    "after_seq": 1
  }
}
```

流程不变量：

- [ ] 提交操作：校验请求 → 原子查重/插入 task 与 task.created → 提交事务 → 返回 ID。
- [ ] 报告完成：校验当前 fencing_token → 写冻结正文 → 原子插入 report_version、report.ready 和状态 → 提交事务 → 唤醒订阅者。
- [ ] 重连操作：仅携带 research_id/after_seq；禁止创建新任务。
- [ ] 恢复操作：创建新 attempt；已完成阶段复用经过输入 hash 校验的 checkpoint；新报告使用新 draft/version。

注意 local/hybrid 的“只使用本地来源”需要 source_policy 明确约束。当前规划过程可能使用搜索，实施时在 `traceable_deep_researcher/skills/researcher.py::plan_research` 和 `traceable_deep_researcher/actions/query_processing.py::get_search_results` 加入允许来源检查；离线 local 任务必须用本地检索/固定工具规划，不能只改 report_source 标签。

### 7.3 修订上限的纯函数与回归测试

建议新增 `multi_agents/agents/review_policy.py`，由 plan/fact/draft 三种路由适配使用，显式传入 verdict 和已完成修订次数：

```python
from typing import Literal

Verdict = Literal["approved", "needs_revision", "rejected", "unknown"]
Route = Literal["accept", "revise", "needs_review", "reject"]

def decide_review_route(
    verdict: Verdict, completed_revisions: int, max_revisions: int
) -> Route:
    if completed_revisions < 0 or max_revisions < 0:
        raise ValueError("revision counts must be non-negative")
    if verdict == "approved":
        return "accept"
    if verdict == "rejected":
        return "reject"
    if verdict == "needs_revision":
        return "revise" if completed_revisions < max_revisions else "needs_review"
    return "needs_review"
```

新增 `tests/test_review_policy.py` 的首批测试：

```python
import pytest
from multi_agents.agents.review_policy import decide_review_route

@pytest.mark.parametrize("completed,expected", [(0, "revise"), (2, "revise"), (3, "needs_review")])
def test_revision_limit_does_not_approve(completed, expected):
    assert decide_review_route("needs_revision", completed, 3) == expected

def test_unknown_review_is_not_approval():
    assert decide_review_route("unknown", 0, 3) == "needs_review"

def test_explicit_approval_passes():
    assert decide_review_route("approved", 3, 3) == "accept"

def test_negative_revision_count_is_rejected():
    with pytest.raises(ValueError):
        decide_review_route("needs_revision", -1, 3)
```

先运行此文件，新增模块尚不存在时预期收集失败；加实现后预期通过。随后更新图边绑定及跨节点测试，证明函数被真正调用。旧配置 `max_revisions=None` 的无限修订语义不能静默保留：迁移时明确拒绝或转换为有预算上限的显式选项，服务端默认采用有限值。

### 7.4 原文切片校验与中文/emoji 测试

新增 `traceable_deep_researcher/evidence/validation.py` 的纯函数部分：

```python
from hashlib import sha256

def validate_evidence_span(
    canonical_text: str, text_hash: str, start: int, end: int, quote: str
) -> None:
    actual_hash = sha256(canonical_text.encode("utf-8")).hexdigest()
    if actual_hash != text_hash:
        raise ValueError("snapshot_hash_mismatch")
    if not (0 <= start < end <= len(canonical_text)):
        raise ValueError("invalid_span_range")
    if canonical_text[start:end] != quote:
        raise ValueError("quote_mismatch")
```

新增 `tests/evidence/test_evidence_spans.py` 的基础测试，随后补 blob 和 repository 集成：

```python
from hashlib import sha256
import pytest
from traceable_deep_researcher.evidence.validation import validate_evidence_span

def test_codepoint_offsets_with_emoji():
    text = "甲😀乙\n证据"
    digest = sha256(text.encode("utf-8")).hexdigest()
    validate_evidence_span(text, digest, 1, 3, "😀乙")

def test_modified_snapshot_is_rejected():
    original = "成本为 10。"
    digest = sha256(original.encode("utf-8")).hexdigest()
    with pytest.raises(ValueError, match="snapshot_hash_mismatch"):
        validate_evidence_span("成本为 20。", digest, 0, 7, "成本为 20。")

def test_fabricated_quote_is_rejected():
    text = "成本为 10。"
    digest = sha256(text.encode("utf-8")).hexdigest()
    with pytest.raises(ValueError, match="quote_mismatch"):
        validate_evidence_span(text, digest, 0, len(text), "成本为 20。")
```

原文规范化先于该函数，text_hash 必须对应实际存储的 canonical_text。前端拿到 quote 直接展示，不重新计算 Python 字符坐标。

### 7.5 评测样本与缺失结果规则

任务样本的一个拟定结构如下；source_bundle 引用由 D2 创建的自编固定资料，文件在实施时随样本集一并添加：

```json
{
  "case_id": "local-comparison-001",
  "dataset_version": "1",
  "split": "dev",
  "query": "比较方案甲乙的年度成本，并说明资料不足之处。",
  "as_of": "2026-10-01",
  "report_type": "research_report",
  "source_policy": {"allowed_kinds": ["local"], "network_allowed": false},
  "source_bundle": "local-comparison-001",
  "requirements": [
    {"id": "r1", "text": "正确列出甲乙年度成本", "weight": 2},
    {"id": "r2", "text": "说明资料未包含维护费用", "weight": 1}
  ],
  "gold_facts": [
    {"id": "f1", "fact": "方案甲年度成本为 10 万元"},
    {"id": "f2", "fact": "方案乙年度成本为 12 万元"}
  ],
  "gold_evidence": ["fixture-甲-cost", "fixture-乙-cost"],
  "budget": {"max_tool_calls": 8, "max_seconds": 60},
  "faults": [],
  "tags": ["zh", "local", "comparison", "missing-evidence"]
}
```

fixture 文本分别写“方案甲年度订阅成本为 10 万元。维护费用未提供。”与“方案乙年度订阅成本为 12 万元。维护费用未提供。”；gold_evidence 坐标由 validator 从固定文本和人工标注生成并验证。gold_facts/requirements 中只把用户可见要求传给被测系统，标准答案和证据标签只给评分器。

新增 `evals/framework/gates.py` 的必需评分器门禁：

```python
from collections.abc import Mapping

def required_metrics_complete(
    states: Mapping[str, str], required: set[str]
) -> bool:
    return all(states.get(name) in {"passed", "failed"} for name in required)
```

这里的 complete 仅代表拿到有效评分结果，failed 仍需后续 threshold gate 判失败；error/skipped/not_applicable/缺失不能满足必需结果要求。测试 `tests/evals/test_release_gate.py`：

```python
from evals.framework.gates import required_metrics_complete

def test_missing_or_skipped_required_metric_blocks_gate():
    assert not required_metrics_complete({}, {"claim_support"})
    assert not required_metrics_complete({"claim_support": "skipped"}, {"claim_support"})

def test_valid_negative_score_is_complete_but_not_a_pass():
    assert required_metrics_complete({"claim_support": "failed"}, {"claim_support"})
```

<a id="delivery-order"></a>

## 8. 实施顺序、依赖与拆分

### 8.1 推荐里程碑

四项是交付主题，不是要求按 A→B→C→D 完全串行。D 的样本、网络隔离和基线从第一阶段建立，之后每项改动都能对照。

当前任务清单（2026-10-30）：

- [x] M0-01：运行上下文、研究结果、前后端请求/状态/事件契约及共享类型样本。
- [x] M0-02：任务/节点评测契约、运行 manifest、错误状态和实际评分分母。
- [x] M0-03：8 个任务、8 个节点的自编开发集及证据坐标/hash/引用校验。
- [x] M0-04：实例隔离回放、runner 网络阻断、统一 CLI 与既有结果汇总。
- [x] M0-05：SQLite/LangGraph 跨进程恢复小样、154 项离线测试、前端生产构建及实施记录。
- [x] M1：A1–A7 代码、隔离验收及本地部署切换完成。用户明确授权后，停写并创建一致性备份、升级实际数据库 v1→v4、启动新版前后端；报告/聊天数量保持 0，备份恢复和只读健康检查通过。单 API/单研究 worker，basic 阶段、detailed 完成章节、deep 完成分支可复用，多代理仅最终结果；人工审核和节点恢复属 M2/B3。
- [ ] M2：统一入口与持久审核闭环。
- [ ] M3：最小证据链与原文核查。
- [ ] M4：全路径覆盖、真实任务/智能体评测、裁判校准与 CI。

M1 已完成本地部署切换，不等于 M2–M4 交付。下一步按批次 06 推进 B1/B2 的剩余静态/嵌入入口统一、B3/B4 持久审核。D2 完整标注集、D3 在线模式和 B/C/D 整体交付仍待实施。Next.js 桌面/手机统一入口作为 M1 的恢复依赖已先行完成。

| 阶段 | 依赖 | 工作范围 | 阶段退出标准 |
|---|---|---|---|
| M0 契约与基线 | 当前源码 | 第 2 节、D1/D2/D3 的离线基础；锁定请求、事件和结果类型 | 小型 fixture suite 能运行，明确旧行为基线与已知失败 |
| M1 任务可靠交付 | M0 | A1–A7；先 basic，再 detailed/deep/multi 的结果适配 | 刷新继续、状态恢复、正文先到、导出可重试、历史不依赖页面 |
| M2 功能闭环 | A2/A5、M0 | B1–B6；D4 的恢复/审核指标 | 移动端与桌面统一；审核重启可恢复；无超限放行 |
| M3 最小证据链 | A1/A4/A6、M0 | C1–C6，先 basic web/local；D4/D6 证据指标 | 点击结论可核查当时原文；篡改或改写不会沿用旧通过状态 |
| M4 全路径与评测交付 | M2/M3 | C7、D4–D8、全部模式回归 | 模式覆盖矩阵完整、任务和节点报告齐全、CI 门槛可执行 |

### 8.2 变更批次建议

每批都形成独立可审阅差异；是否提交/推送遵循用户授权，不因技能建议而自动执行。

| 批次 | 涉及步骤 | 首要文件 | 回归重点 |
|---|---|---|---|
| 01 | 公共契约、D1/D2 基础 | runtime/contracts、tasks/models、evals/framework/models、dataset fixtures | schema 与数据分割 |
| 02 | A1 | storage、report_store、migration script | 旧历史导入/损坏拒绝 |
| 03 | A2/A3 | tasks/service/repository/worker、app、run_agent adapter | 幂等、任务领取、统一结果 |
| 04 | A4/A5 | checkpoints、events、useResearchTask | 阶段恢复、事件回放、旧 WS |
| 05 | A6/A7 | exports、publisher、history、Compose | 导出失败隔离、重启持久化 |
| 06 | B1/B2 | page、mobile、static、embedded、Next proxies | 多入口相同行为 |
| 07 | B3/B4 | reviews、HumanAgent、ReviewStatus | 单次消费、持久等待 |
| 08 | B5/B6 | review_policy、orchestrator/editor、E2E | 超限不放行、端到端闭环 |
| 09 | C1/C2 | evidence storage/ingestion、来源接入 | 快照先于筛选 |
| 10 | C3 | context bundle/filters | 坐标与上下文兼容 |
| 11 | C4/C5 | writer/prompts、claims/validation/publication | 原子论断与版本门禁 |
| 12 | C6/C7 | evidence API/UI、嵌套研究 | 可视证据与多模式覆盖 |
| 13 | D3/D4 | replay/providers/task metrics | 固定来源比较、真实分母 |
| 14 | D5/D6 | agent adapters/judges/perturbation | 节点定位、裁判校准 |
| 15 | D7/D8 | compare/report/CI/docs | 统计、门槛、操作说明 |

每批执行清单：

- [ ] 读取该步骤列出的现有函数及相邻测试，确认基线与文档一致。
- [ ] 为该批新增一个最小失败案例，先确认旧实现会在目标行为上失败，排除测试自身配置错误。
- [ ] 实现该批契约和最小运行路径；新增目录补齐 `__init__.py`，新增依赖更新对应锁文件。
- [ ] 运行该批测试及直接受影响的兼容测试，保存实际命令与结果。
- [ ] 有前端修改时运行类型/生产构建与对应 E2E；有迁移/导出修改时运行容器验收。
- [ ] 更新部署/架构/评测文档；记录数据与配置迁移方式；检查没有运行产物被加入代码差异。

以上是工作拆分，不承诺固定工期。完成 M0 的存储、LangGraph 恢复与结构化写作小样后再估算日历时间，避免在关键兼容问题未验证前给出虚假的精确日期。

## 9. 配置、接口与部署清单

### 9.1 当前与拟新增配置

本表为完整路线图设计值，不能直接视为当前支持。M1 实际名称/default 以 [部署配置表](deployment.md#persistent-research-tasks-m1) 为准：`TDR_WORKER_LEASE_SECONDS=30`、`TDR_WORKER_POLL_SECONDS=0.1`、`TDR_WORKER_SHUTDOWN_SECONDS=5`、`TDR_HTTP_WAIT_SECONDS=30`、`TDR_EVENT_RETENTION=20000`、`TDR_EXPORT_MAX_SECONDS=180`。当前单 worker，无自动研究重试；其余并发/审核/evidence 开关尚未实现。

集中由 `backend/server/settings.py` 或对应 eval settings 解析；模型/检索现有设置仍由 Config 管理。新增开关应在构造期读取，不在模块 import 时固定，便于测试与多任务隔离。

| 设置 | 建议初始值 | 用途 |
|---|---|---|
| `TDR_DATABASE_URL` | `sqlite:///./data/tdr.db` | 任务/报告/证据元数据库 |
| `TDR_TASK_WORKER_ENABLED` | `true` | 首版单实例 worker |
| `TDR_TASK_MAX_CONCURRENCY` | `2` | 同时运行的研究任务数；人工等待释放槽位 |
| `TDR_TASK_LEASE_SECONDS` | `90` | 初始租约长度；续租间隔应小于其三分之一，并通过故障注入验证 |
| `TDR_TASK_MAX_ATTEMPTS` | `3` | 自动恢复的尝试上限；不可恢复错误不自动重跑 |
| `TDR_EVENT_RETENTION_DAYS` | `30` | 事件回放窗口，过期走状态/报告快照 |
| `TDR_EXPORT_MAX_CONCURRENCY` | `1` | 控制 PDF/DOCX CPU/内存负载 |
| `TDR_REVIEW_TIMEOUT_SECONDS` | `86400` | 默认审核等待期限，超时不批准 |
| `TDR_EVIDENCE_DIR` | `./data/evidence` | 内容快照持久卷 |
| `TDR_LINEAGE_MODE` | `off`，验收后改 `record` | off/record/enforce；record 收集并展示，enforce 启用 verified 门禁 |
| `TDR_EVAL_MODE` | `offline` | runner 默认模式 |
| `TDR_EVAL_MAX_COST_USD` | `0` | 默认不允许付费；非离线运行显式设置，费用未知用 token/call 上限 |
| `TDR_BLOCK_NETWORK` | 测试为 `1` | 延续已有约定；评测 CLI 也实际执行阻断 |

保持供应商原有密钥名称，不为改名复制真实密钥。旧 REPORT_STORE_PATH 仅供迁移/兼容读取，新增数据库设置使用 TDR_ 前缀；.env.example 只写占位值与说明，不创建真实 .env。文件存储与数据库需一起备份，单独备份数据库不能恢复已删除的证据原文。

### 9.2 接口完整清单（当前与拟新增）

M1 已提供 research 提交/查询/取消/恢复/事件和 WS；导出实际路由为 `/api/research/{id}/exports`、`/exports/{format}/retry`、`/exports/{format}/download?job_id=...`，归属与不可变版本在 job 上校验。下面的 feedback、claims、evidence 与报告版本路由仍为 M2/M3 设计，不是当前可调用接口。

| 方法与路由 | 输入/输出与异常 |
|---|---|
| POST `/api/research` | 幂等创建；202 返回 ID；422 请求非法，409 幂等内容冲突 |
| GET `/api/research` | 分页状态列表，不返回全部快照正文 |
| GET `/api/research/{id}` | 状态、审核、报告版本、导出摘要和 last_seq；不存在 404 |
| GET `/api/research/{id}/events?after_seq=...` | 分页事件回放，供 WS 以外的恢复/诊断使用；保留期失效明确 resync |
| POST `/api/research/{id}/cancel` | 幂等取消请求；终态返回已有状态 |
| POST `/api/research/{id}/resume` | 从有效 checkpoint 创建 attempt；运行中/不兼容 409 |
| POST `/api/research/{id}/feedback` | CAS 消费 review_id 与目标版本；过期/重复冲突 409 |
| GET `/api/reports/{id}/versions/{version}/exports` | 每种格式独立状态 |
| POST `/api/reports/{id}/versions/{version}/exports/{format}/retry` | 相同产物幂等，非法格式 422；版本不存在 404 |
| GET `/api/reports/{id}/versions/{version}/claims` | claim 与证据索引、核查状态 |
| GET `/api/reports/{id}/versions/{version}/evidence/{evidence_id}` | quote、前后文和来源元数据；报告未引用此证据返回 404 |
| WS `/ws` | 旧协议适配与新 subscribe envelope；单一接收循环 |

所有前端代理路径按上述 API 一对一创建，避免只改 FastAPI 忘记 Next route。接口错误返回统一 code/message/retryable/research_id，不暴露供应商凭据或数据库路径。

<a id="verification"></a>

## 10. 验证命令与验收操作

下列保留完整方案的未来验证命令，部分 B/C 文件尚未实现。M1 本次实际执行命令和结果见 [validation](validation.md)；不能把下面尚不存在的测试写为通过。根目录 `E:\Deep Researcher`，不能把 `.venv-graphify` 当作应用环境。

### 10.1 后端与核心离线验证

```powershell
$env:TDR_BLOCK_NETWORK = '1'
python -m pytest tests/backend/test_task_api.py tests/backend/test_task_worker.py tests/backend/test_task_leases.py -q
python -m pytest tests/backend/test_task_event_replay.py tests/backend/test_export_jobs.py tests/backend/test_review_inbox.py -q
python -m pytest tests/test_review_policy.py tests/test_human_review_resume.py tests/test_multi_agents_route_bindings.py -q
python -m pytest tests/runtime tests/evidence tests/evals -q
python -m pytest tests/ --collect-only -q
```

预期每条命令退出码 0，无外网请求；修改前新增行为测试应能显示对应失败。Windows 若遇既有测试全局状态污染，按文件独立进程执行并记录结果；Linux CI 继续遵循现有 `--forked` 和 live 文件排除配置，不能照搬 Linux 进程选项到 Windows。

### 10.2 前端验证

在 `E:\Deep Researcher\frontend\nextjs` 执行；测试脚本由 B6 添加，不能在添加前宣称可用：

```powershell
npm ci
npm run test:unit -- --run
npm run build
npm run test:e2e
```

`test:unit` 建议映射 vitest；`test:e2e` 映射 playwright test。预期组件测试和桌面/移动浏览器套件通过，生产构建退出 0。浏览器下载与依赖安装发生在测试准备阶段，业务运行阶段仅连接测试服务，无付费调用。

### 10.3 评测命令（拟新增 CLI）

`evals/run.py` 根据 suite 分发 task_eval/agent_eval；`evals/report.py` 读取已有结果，不触发研究。dataset validator 使用 manifest 指定文件与哈希。

```powershell
python scripts/validate_eval_dataset.py --manifest evals/datasets/dataset_manifest.json
python -m evals.run --suite task --mode offline --split dev --limit 8 --out evals/results/task-smoke
python -m evals.run --suite agent --mode offline --split dev --out evals/results/agent-smoke
python -m evals.report --runs evals/results/task-smoke evals/results/agent-smoke --out evals/results/review
```

预期没有 API key 也可完成；真实模型/搜索调用次数为 0；结果包含各自 manifest、样例结果、分母、失败清单及费用模式。固定模型输出的 task-smoke 必须注明 engineering replay，不能写“模型研究质量达到 X%”。真实模型评测只在后续显式选择 frozen-tools/live 并配置预算时运行。

### 10.4 贯穿四项的最终验收场景

| 场景 | 操作 | 必须观察到的结果 |
|---|---|---|
| 网络中断 | 研究中断开页面连接，再打开同一任务 | research_id 不变，任务继续，事件不重复，恢复到当前正文 |
| 服务重启 | 来源收集完成后重启后端 | 从受支持 checkpoint 恢复；不支持部分明确 interrupted；旧 worker 无权提交 |
| 导出失败 | 注入 PDF renderer 失败 | 正文与历史已可读，DOCX 可成功，PDF 可独立重试 |
| 人工反馈 | 多代理计划审核时刷新，再修改/批准 | 恢复同一个 review；只消费一次；旧版本响应被拒绝 |
| 审核超限 | 核查持续返回问题直到上限 | needs_review/草稿，不显示 approved，不进入 verified 发布 |
| 证据复核 | 点击一个数字结论，随后修改来源网页 | 仍看到抓取时的原文和时间；quote 与快照 hash 一致 |
| 报告修订 | 修改已审核论断或引用 | 生成新版本，旧审批不能沿用；旧版本仍可复核 |
| 指标可信度 | 删引用、错配同域文章、植入错误数字 | 结构指标与语义支持指标按预期响应，不只比较域名 |
| 节点归因 | 固定检索结果替换 writer，再固定 writer 替换筛选器 | 两组实验明确区分写作错误与证据丢失，保留成对任务结果 |
| 全部模式 | basic/detailed/deep/multi_agents 逐一运行离线 fixtures | 正文、任务状态、证据和评测结果可关联；独立 deep_agents 另列适配结果 |

## 11. 迁移、回滚与主要实施风险

### 11.1 分阶段启用与回滚

- [ ] 上线前备份 reports.json、数据库、证据 blob 和导出目录，验证恢复到临时目录可读。
- [ ] 存储迁移先增量增加 schema，不立即删除旧 JSON；首次切换维护窗口内停止写入，导入校验后开启新服务。
- [ ] 出现数据库/worker 问题时停止领取任务，保留数据，以兼容新 schema 的上一个服务版本回滚；不要直接删除数据库退回旧 JSON。
- [ ] 若必须退回只支持旧 JSON 的版本，先维护模式导出兼容报告/聊天快照，再切换；任务、事件和 lineage 数据仍保留在数据库备份中，旧版 UI 明示这些能力不可用。
- [ ] lineage 先 record 后 enforce；关闭新任务的强制策略，不抹去已有 verified 报告的真实版本/校验记录。新的未校验结果不能沿用旧标签。
- [ ] 评测门槛版本化，发现裁判问题可停用自动质量门禁并转人工检查；确定性数据完整性门禁继续保留。

### 11.2 需要优先验证的技术风险

| 风险 | 验证/处置 | 对应步骤 |
|---|---|---|
| LangGraph 版本范围较宽，现用图未持久 checkpoint | M0 做最小 interrupt/resume/重启样例，锁定兼容版本；运行时对象不进入 checkpoint | B3 |
| 核心仍有字符串上下文、多处直接格式化 | 结构化 bundle 加兼容 renderer；每个 fallback 单独验证，不做一次性返回类型替换 | C2/C3 |
| 多代理已有自己的输出目录和 exporter | 统一交付 adapter；CLI 保留独立选项，服务路径只能有一个权威发布者 | A2/A6 |
| SQLite 写入竞争/长事务 | 短事务、claim CAS、续租/提交 fencing；首版限制单机，不宣称跨主机高可用 | A1/A3 |
| 流式写作与最终结构化 claims 不一致 | 草稿和最终版本分开，最终 replace 而非 append，hash 绑定 | A4/C4 |
| 来源 token 裁剪或摘要丢失原文映射 | 边界裁剪/derived 标签；无法精确映射即 unavailable | C3 |
| 现有评测会联网或使用全局 monkeypatch | 实例注入、显式模式、runner 自带网络 guard、跨配置进程隔离 | D3 |
| 模型裁判偏差、样本量不足 | 人工双标、盲评反序、扰动检验、区间与缺失率；不足时不自动通过 | D2/D6/D7 |

## 12. 交付物与完成清单

- [x] A：数据库迁移脚本、TaskService/worker、恢复与事件协议、独立导出、服务端历史及文档，代码/隔离验收和授权后的 A7 本地切换均已完成；能力边界见 M1 记录。
- [ ] B：统一研究客户端、静态/嵌入兼容、持久人工审核、明确审核路由、桌面/移动 E2E。
- [ ] C：来源快照与片段模型、上下文身份保留、claim/citation 绑定、版本发布校验、原文查看 UI、模式覆盖矩阵。
- [ ] D：版本化任务/节点数据集、三种运行模式、任务/智能体指标、裁判校准、基线对照、离线 CI 与手动在线评测入口。
- [ ] 更新 `docs/architecture.md`、`docs/deployment.md`、`docs/migration.md`、`docs/validation.md`，新增 `docs/evaluation.md`；validation 只写本轮实际执行结果。
- [ ] 逐步更新 Graphify 图和 `docs/project-chain.zh-CN.md`，区分静态依赖和实际运行验证；图输出仍作为本地产物，不自动提交。
- [ ] 保存实际测试命令、构建与迁移结果；检查真实 .env、凭据、生成报告、数据库、缓存和评测运行结果均未进入提交候选。

M0 与 M1 已完成当前范围。下一实施入口为批次 06 / B1–B2 剩余入口适配，再推进 B3–B6。完成标准仍是各工作包的用户流程与验收证据齐全，不因已有目录或接口提前完成 M2–M4。
