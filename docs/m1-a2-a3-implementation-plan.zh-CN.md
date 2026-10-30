# M1／批次 03：统一任务服务与持久 worker

规划日期：2026-10-30。依据：[总计划 A2–A7](optimization-plan.zh-CN.md#work-a)、A1 实施与验收记录。用户授权按顺序升级；本次不自动提交或推送。

## 1. 顺序与边界

先交付 A2/A3，再交付 A4/A5，最后 A6/A7。每批独立验收后更新总清单。生产历史迁移先检查是否确有旧文件，不读取或输出真实密钥，不把隔离测试结果记成真实数据迁移完成。

批次 03 建立任务、尝试、事件基础表及统一执行适配；事件查询用于连接与执行解耦，完整浏览器恢复在 A5 交付。A4 检查点尚未具备时，进程丢失只能标记 interrupted；手动 resume 创建新的 attempt 并明确可能重跑、重复计费。人工审核的持久等待属于 B3，在接通前拒绝需要人工审核的持久任务，避免静默跳过审核。

## 2. 设计与兼容

1. 新增 schema 002；显式迁移命令原子升级 v1→v2。原 001 校验和保持不变，未知版本、篡改和半成品 schema 拒绝启动；服务端只检查，不自动升级。现有报告及不可变版本保留。
2. TaskRepository 独立于现有 ReportRepository；SQLite 短事务串行化提交、领取、续租、取消、完成和事件序号。request_hash 使用规范 JSON；Idempotency-Key 相同且内容不同返回 409。
3. POST /api/research 返回 202 和服务端 ID；GET 列表/单项、cancel、resume 共享 TaskService。状态、审核、导出、attempt 和 last_seq 分开返回。初版单 API 进程、一个 worker；通过租约和 fencing token 防止过期执行提交。
4. worker 持有执行 task，与 socket 生命周期独立。正常退出有界等待；无法完成的执行标记 interrupted。过期租约失效旧 token，不能自动宣称成功或静默重跑远程模型调用。
5. 普通、detailed、deep、multi_agents 统一 ResearchResult，保留旧 run_agent 公开返回形态。所有 runner 产物必须为可序列化快照；生产 API 不将 researcher 活对象写库。
6. 旧 /report/ 后台入口委托服务；前台以有界等待查询同一任务，等待超时不取消研究。旧 WS start 创建任务并转发事件；断线只停止订阅。聊天的连接级任务仍按原有清理语义取消。
7. 配置及请求中不持久化 headers、原始 MCP env 或密钥。旧临时凭据只存内存，以任务 ID 引用；进程重启缺失时明确 requires_credentials。新 API 只接受服务端管理的 MCP 引用，未配置引用拒绝提交。
8. 预算和来源策略必须实际执行或显式拒绝不支持选项，不能只验证字段。执行超时可强制取消，工具/费用硬预算未接线前拒绝相应限制；受限网络策略不交给未支持的旧 runner。
9. 报告完成时在同一事务保存报告投影、版本、终态与事件。首批保留原导出兼容逻辑；A6 再独立导出作业。避免旧前端完成保存覆盖服务端权威版本的改动在 A7 完成。

## 3. 实施与验收清单

- [x] 03-01：读取总清单、现有调用点和 A1 数据库约束，记录详细计划。
- [x] 03-02：先写任务 API／幂等、schema 升级、租约竞争与过期 token 的失败测试。
- [x] 03-03：实现显式 schema 升级、任务 repository 与事务状态迁移。
- [x] 03-04：实现 TaskService、任务 API、凭据引用和统一结果适配。
- [x] 03-05：实现 worker 领取、续租、超时、取消、退出及过期执行隔离。
- [x] 03-06：接入旧 HTTP/WS，验证断线清理与后台执行继续，保留原聊天回归。
- [x] 03-07：运行 M0/A1 与新增离线回归，必要前端类型/构建，隔离 Linux 容器升级和重启验证。
- [x] 03-08：更新部署、架构、总清单和本页执行证据；进入批次 04。

测试禁止调用真实模型、搜索或裁判。worker 使用注入的固定 runner，API 使用真实 FastAPI lifespan、路由、SQLite；故障覆盖重复提交、取消/完成竞争、双 worker 竞争、租约过期后旧写入拒绝、服务重开、凭据丢失及多代理完整正文。容器验证使用隔离卷，不替换当前人工核验服务或接触其真实 .env。

## 4. 后续批次

批次 04：A4 检查点与 A5 有序持久事件回放、重连去重和前端任务入口。批次 05：A6 独立导出重试、A7 服务端历史与部署切换。每批新增具体计划和验收证据，不提前勾选完成。

## 5. 执行记录

2026-10-30：先运行新增测试，因缺少 task_repository 收集失败，随后实现。新增与既有组合回归 **216 passed，76.54 秒，无跳过**；覆盖 M0/A1、任务 API、租约竞争、旧 token 拒绝、取消/完成竞争、超时 finally 清理、临时凭据丢失、WS 断线继续及旧 HTTP 多代理完整正文。schema 未知版本负面对照由修改全部版本行调整为只修改最新一行，避免两条迁移记录产生唯一键冲突而未执行原校验目的。

`NEXT_TELEMETRY_DISABLED=1 npm run build` 通过编译、lint、类型和生产构建。`docker build --progress=plain --tag tdr-task-validation:20261030 .` 成功；容器入口改为 exec 形式，使停止信号到达 uvicorn；启动器明确拒绝多 API worker 配置。

`.venv/Scripts/python.exe scripts/verify_task_container.py --image tdr-task-validation:20261030` 完成 **7 项 Linux 检查，26.98 秒，退出码 0，cleanup_errors=[]，provider_calls=0**。真实 API、完整容器依赖与 SQLite，研究边界使用固定 Basic/Detailed/multi 适配器；验证四种研究类型、完整正文、服务端历史与有序事件、强制杀进程后的持久队列和 interrupted、新 attempt 及显式取消。镜像仅作隔离验证，没有替换人工核验中的服务或迁移真实数据库。

能力边界：仅部署单 API 进程；当前预算只强制执行秒数上限，显式工具/token/费用硬上限会被拒绝；新 API 的人工审核、无网络策略和服务端 MCP 引用解析器尚未接入，均明确拒绝。旧 WS 临时 MCP 配置仅留内存，过期或重启后显示 requires_credentials。多代理当前只接受默认网络来源。后续批次保留这些边界，不静默降低约束。
