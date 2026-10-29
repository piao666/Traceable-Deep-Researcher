# M1 / 批次 02 / A1：生产报告存储与旧历史迁移

规划日期：2026-10-26。依据为总方案第 2.4、A1、8.1/8.2、11.1 节，以及 M0 实施记录。先记录本计划，再编写失败测试、实现和验收；本阶段不自动提交或推送。

## 1. 范围与已读基线

本批交付 A1，不将 M1 整体勾选完成。A2/A3 的 TaskService、worker、任务租约，A4/A5 的恢复与事件，以及 A6/A7 的导出解耦和服务端自动历史保存仍按原依赖实施。

已读 `backend/server/report_store.py`、`app.py` 的报告 CRUD/聊天/lifespan、现有聊天路由测试、Next.js reports 代理与 history hook、Compose、环境样例、部署和迁移说明。

当前 ReportStore 每次读写完整 JSON，使用进程内 asyncio 锁，读取损坏文件时返回空字典。PUT 和聊天路由先读后整体覆盖，有丢失并发修改的风险。Next.js 接口期待 `{reports: [...]}`、`{report: {...}}`，报告包含 id/question/answer/orderedData/chatMessages/timestamp。已有 Graphify 本地文件及 `.dockerignore` 改动保留。

## 2. 设计决定

1. 使用已有依赖 SQLAlchemy 的 SQLite 同步引擎；文件库开启 WAL、foreign_keys、busy_timeout。写事务使用 BEGIN IMMEDIATE，数据库操作通过线程执行，连接不跨线程共享。
2. `storage/migrations/001_tasks.sql` 建立 schema 版本、报告当前投影、不可覆盖报告版本、聊天和迁移凭据表。本批只建实际使用的报告表；任务/事件/租约表由 A2/A3 在新迁移中加入，不预建未经实现验证的空架构。
3. `storage/models.py` 提供 SQLAlchemy Core 表映射；`tasks/repository.py` 集中报告 SQL。ReportStore 保留 list/get/upsert/delete，增加分页、原子 patch 和聊天追加；内容变更生成新版本，单纯聊天/时间更新不伪造正文版本。旧报告额外字段和聊天原对象保留。
4. 列表保持旧返回结构和无参数行为，增加可选 limit/offset，按 timestamp 降序及 ID 稳定排序。PUT 与聊天写回使用事务内变更，避免覆盖并发写入的其他字段/消息。
5. 采用显式迁移：CLI 执行 schema 升级，API 启动只检查版本。迁移在数据库写锁内串行，失败回滚；未知/较新 schema 拒绝启动。不在模块 import 时创建数据库。
6. 新配置 `TDR_DATABASE_URL` 默认 `sqlite:///./data/tdr.db`。旧 `REPORT_STORE_PATH` 只定位待迁移 JSON。存在未导入或已变化的旧文件时拒绝启动，提示操作员先维护停写、dry-run 和导入；不静默建空库。
7. 迁移默认 dry-run，不创建数据库或备份，报告记录数、异常 ID 和冲突。拒绝重复 JSON key、非对象顶层、ID 不匹配、非法字段及非有限数字。实际导入前保存源文件原始字节备份和 SHA-256 清单，并复核源文件未变化。
8. 导入以源 hash + report ID 留凭据；同源重跑跳过，已有同内容记录可登记为已导入，不覆盖不同内容。显式 `--update-imported` 允许维护期间增量更新，但只允许同源且目标仍等于上次导入内容的记录，防止覆盖数据库中的后续修改。
9. 一个导入批次的报告、版本、聊天和凭据在同一事务写入。失败全部回滚，备份保留。历史标记 origin=legacy_import、lineage_status=unavailable，不创建虚构任务、事件或证据。
10. 不运行真实数据迁移；只用临时文件和数据库验证。部署目录、数据库及备份加入忽略；不触碰真实 `.env`，不调用付费服务。

## 3. 实施顺序与验收清单

- [x] A1-01：读取现有清单和调用点，完成本详细计划。
- [x] A1-02：先写失败测试，证明缺少数据库 repository/迁移行为。
- [x] A1-03：实现数据库、schema 版本检查、表映射与事务 repository。
- [x] A1-04：实现 ReportStore 兼容门面及 CRUD 分页、原子更新和聊天接线。
- [x] A1-05：实现 dry-run/备份/幂等/冲突/安全增量/回滚及 CLI。
- [x] A1-06：同步部署、迁移、配置样例、忽略规则、架构和总任务清单。
- [x] A1-07：完成离线测试、已有聊天路由回归、M0 回归与迁移 CLI 验收。
- [x] A1-08：2026-10-29 补齐 Linux 容器验收；实际环境、命令和结果见第 5 节。

测试矩阵：CRUD 和分页；中文/emoji/未知字段；内容版本不可覆盖；并发不同报告写入、同报告 patch/聊天追加；外键/WAL/重开持久性；缺失/过新 schema；两个迁移者串行；损坏/重复 key/非法 ID；空和缺失文件；备份字节/hash；重复导入；同 ID 冲突；安全增量及目标被改后的冲突；中途失败全事务回滚；旧 JSON 保持不变；未迁移源阻止服务启动。

## 4. 执行记录

本批没有前端源码改动，不重复生产构建。生产研究流程及供应商评测不属于本批验收，所有迁移验证使用 pytest 临时目录；没有读取或迁移用户的真实报告。

### 4.1 红绿验证与修正

- 首次运行两个新增存储/迁移测试文件：收集阶段因 `backend.server.storage` 缺失失败，确认目标行为未实现。
- 首次实现后 23 项通过，双迁移者测试在启用 WAL 时暴露 `database is locked`；增加仅针对 SQLite BUSY/LOCKED 的有界重试，随后 24 项通过。
- 报告版本只由正文/内容变化递增；旧聊天保持原消息身份和版本。patch、追加聊天和导入使用事务；过期聊天回复不能写入新版报告，返回 409。
- schema hash 使用规范化换行后的 UTF-8，避免 Windows/Linux 检查值不同。
- 备份和导入同受数据库写锁保护；CLI apply 在校验源 JSON 后串行初始化 schema，两个独立导入进程均能完成并保持幂等。
- 加入备份失败、源文件变化、schema DDL 回滚和导入中途失败的负面测试；CLI JSON 输出使用 ASCII 转义，避免 Windows 控制台不能输出 emoji。

### 4.2 已执行验证

```powershell
$env:TDR_BLOCK_NETWORK = '1'
$env:LANGSMITH_TRACING = 'false'
$env:LANGCHAIN_TRACING_V2 = 'false'
.venv/Scripts/python.exe -m pytest tests/backend/test_report_repository.py tests/backend/test_report_store_migration.py tests/backend/test_report_migration_cli.py tests/backend/test_report_chat_route_uniqueness.py tests/backend/test_report_storage_api.py tests/runtime tests/backend/test_task_contracts.py tests/evals tests/test_quality_metrics.py -q --tb=short -p no:cacheprovider
```

最终组合回归 **190 passed，28.94 秒，无跳过**：本批 36 项（含原聊天路由 2 项）及既有 M0 154 项。API 测试运行真实 FastAPI 路由、lifespan、HTTP 请求和 SQLite，但把研究/导出模块替换为禁止调用的边界，并使用固定聊天回复，不能当作完整模型依赖栈或容器启动验证。沿用 M0 已确认的 Windows 沙箱限制处理，涉及 asyncio/临时目录的测试在受控沙箱外运行，并保留上述外网阻断与关闭 tracing 的设置。

受影响模块和测试的 `compileall`、`git diff --check`、Compose YAML 与 data 挂载静态检查已通过。项目已声明 SQLAlchemy，无新增项目依赖或锁文件变更；本机验证使用 SQLAlchemy 2.0.41、SQLite 3.49.1、FastAPI 0.115.12、Python 3.12.10。

### 4.3 未完成的部署验收

2026-10-26 时本机未找到 Docker/Podman，`wsl --list --quiet` 显示 WSL 未安装；当时未运行 Linux 容器、非 root 卷权限、容器替换持久性及真实维护切换。本限制已在 2026-10-29 安装后补验关闭，见第 5 节；真实生产切换仍未执行，M1 其余工作仍未完成。

具备容器环境后：按 `docs/migration.md` 使用隔离 data 卷和自编历史执行 dry-run/apply/重复导入，核对中文正文与聊天；启动真实后端并通过 HTTP 验证分页/CRUD，替换容器复验；检查不迁移/不兼容 schema 时启动失败，并验证备份恢复到独立目录可读。验收不得使用付费研究调用。

## 5. 容器验收补验计划（2026-10-29）

用户已安装 Docker 和 WSL。主机检查确认 Docker Desktop 的 Linux 引擎可用，WSL 默认 Ubuntu、版本 2；沙箱内的 WSL ACCESS_DENIED 不再作为主机未安装的依据。按执行计划及验证技能补验，继续使用当前 `codex/work` 上尚未提交的 A1 改动。

1. 用仓库 Dockerfile 构建独立标签 `tdr-a1-validation:20261029`，不覆盖部署镜像标签；构建允许下载依赖。
2. 编写可重跑的容器 smoke 脚本，仅创建带随机后缀的临时容器和数据卷；运行时 `--network none`，不加载 `.env`，以容器内 loopback HTTP 检查真实 API。
3. 以镜像默认非 root 用户创建中文/emoji/聊天合成历史，验证 dry-run 无新数据库、apply 备份字节/hash、重复导入及迁移标签。
4. 启动真实默认 uvicorn 入口，验证报告 CRUD、分页及导入聊天；替换容器复验同一卷；停止写入后复制完整数据到独立恢复卷，再启动校验。
5. 在单独负面卷验证空 schema、未知 schema、未导入旧历史均拒绝启动。全程不调用研究、导出或生成聊天接口。
6. 无论成功失败都清理本次创建的容器和卷，保留本地镜像/构建缓存；检查结果留在忽略的 `evals/results/`，只把可复现脚本和实际验证记录纳入代码差异。
7. 若真实容器暴露代码问题，先定位及记录失败，再修正受影响部分并重跑相关离线/容器验证；仅在全部通过后关闭 A1-08，M1/A2–A7 仍待实施。

### 5.1 实际执行与结果

```powershell
docker build --progress=plain --tag tdr-a1-validation:20261029 .
docker compose config --quiet
.venv/Scripts/python.exe scripts/verify_a1_container.py --image tdr-a1-validation:20261029 --out evals/results/a1-container-20261029/summary.json
```

- Docker Desktop 4.96.3，Engine 29.9.2；`docker-desktop` 为 Running / WSL2，Ubuntu 为默认 WSL2 发行版。
- 仓库 Dockerfile 构建成功；最终验证镜像 ID 为 `sha256:65c9c1bf5248054e4e47d7efe216495f15ea11319e9403edc6dd834db097108f`。
- Linux 镜像：Python 3.14.10、SQLite 3.40.1、SQLAlchemy 2.1.6、FastAPI 0.162.0；镜像默认非 root 用户，真实 uvicorn 入口启动成功，没有替换研究模块或 API 实现。
- **13 项容器检查全部通过，96.94 秒，退出码 0；cleanup_errors=[]**。覆盖镜像排除 `.env`/本地评测产物、非 root 写卷、helper CLI 超时清理、dry-run、原字节备份 SHA-256、重复导入、中文/emoji/聊天、真实 HTTP CRUD/分页、替换持久性、独立卷恢复及三种启动拒绝。
- 所有运行时容器使用 `--network none`，没有调用研究或生成聊天接口，没有真实模型或搜索调用。数据为本脚本自编历史，不读取真实 `.env` 或历史报告。
- 本次重新执行既有 **190 项离线测试：190 passed，55.79 秒，无跳过**。另有容器清理保护 **2 项测试先失败、修正后通过（0.13 秒）**，验证 helper 超时回收和拒绝误删其他 run 的资源。
- 独立代码复核发现 helper 的匿名 `docker run --rm` 在 CLI 超时后可能继续运行；已改为预登记、随机前缀、run 归属标签和 finally 删除，最终清理逐项继续。复核关闭该 P2，真实容器超时探针也通过。
- `.dockerignore` 追加排除 `evals/results`；最终镜像已实际检查该目录与真实 `.env` 均未包含。镜像和构建缓存留在本机，临时容器与卷已清理。
- 原始 summary 留在忽略目录；本轮未修改研究运行逻辑、未迁移真实数据、未提交或推送。A1-08 关闭，A2–A7 尚未实施。

### 5.2 提交授权（2026-10-29）

用户在完成上述验收后授权将本阶段成果提交并推送到 GitHub。提交范围为 A1 生产报告存储、旧历史迁移、离线/容器验收代码及对应配置、部署和任务清单文档；继续使用 `codex/work` 分支。Graphify 本地分析产物、评测输出、数据库、备份及真实 `.env` 不纳入提交。第 5.1 节“未提交或推送”描述验收执行时的状态。
