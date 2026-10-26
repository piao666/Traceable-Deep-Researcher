# M0 离线评测与契约验证

当前交付为 [四项优化方案](optimization-plan.zh-CN.md) 的 M0：运行契约、评测契约、固定工具/模型产物回放和小型工程基线。具体设计与执行记录见 [M0 实施清单](m0-implementation-plan.zh-CN.md)。

## 能验证的内容

- 研究请求、预算、任务事件、订阅命令与 Python/TypeScript 共享样本的字段约束。
- RunContext 子步骤身份与依赖传递，ResearchResult 的独立默认集合；核心契约可在没有供应商依赖时导入。
- 数据集哈希、引用文件路径、来源文本、Unicode 原文片段坐标、组别隔离和工具回放身份。
- 固定产物的工程约束，以及来源域名与参考文献域名的一致性描述指标。
- 评分失败、跳过、不适用与有效低分的区别；失败分数参与真实分母，缺少必需结果不能通过门禁。
- 临时 SQLite 事务/重开，以及 LangGraph SQLite 检查点在两个独立进程间的暂停与恢复。

当前 8 个任务和 8 个节点样本均为自编合成开发样本。`evaluation_kind=engineering_replay` 表示回放固定产物，不代表运行了真实研究智能体，也不代表事实正确率、证据语义支持率或真实模型成功率。节点样本覆盖八种节点的输入/输出契约，实际节点替换实验属于后续 D5。

当前生产 WS/HTTP 路由尚未接入新任务契约、持久队列或 ReviewInbox；新增协议为 M1 提供接口基础。恢复小样独立于应用，不能当成线上任务已具备断线/重启恢复能力。

## 准备环境

Python 3.12 或更高。可用项目现有环境；也可以建立独立验证环境。下列命令不会运行研究服务：

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r evals/requirements-m0.txt
```

`evals/requirements-m0.txt` 锁定本次风险小样所验证的 LangGraph/SQLite 检查点版本，不替代应用的 `pyproject.toml`。单独运行回放 CLI 只需要 Pydantic；LangGraph 仅用于恢复小样。依赖安装可以联网，以下评测执行默认离线。

## 验证数据集

在仓库根目录执行：

```powershell
.venv/Scripts/python.exe scripts/validate_eval_dataset.py
```

可以用位置参数指定其他 manifest 路径。输出包括 `valid`、样本数和数据集/来源哈希。数据文件被修改但没有更新 pin、缺少 fixture、来源坐标越界或跨 split 复用组别时返回退出码 2。

评分标准与候选产物分别处理：无效 JSON/来源引用是数据配置错误；合法但内容不达标的候选进入评分，不能在加载阶段被要求先满足标准答案。数据文件的确切结构见 [数据集说明](../evals/datasets/README.md)。

## 运行两套工程回放

选择尚不存在的输出目录，运行：

```powershell
.venv/Scripts/python.exe -m evals.run --suite task --out evals/results/task-m0
.venv/Scripts/python.exe -m evals.run --suite agent --out evals/results/agent-m0
.venv/Scripts/python.exe -m evals.report --runs evals/results/task-m0 evals/results/agent-m0 --out evals/results/review-m0
```

可选参数为 `--manifest`、`--split`、`--limit`、`--seed`；当前仅有 dev 集。seed 记录实验参数，固定回放本身没有随机采样。相同配置按文件顺序选择样本，不因环境里存在 API key 而启用在线服务。

CLI 支持的实际模式只有 offline。`--mode live`、`--mode frozen-tools`，以及把 `TDR_EVAL_MODE` 设置为这些值，都会明确拒绝运行。后续增加真实模型执行器后才会开放这些模式。

每次执行生成：

| 文件 | 内容 |
|---|---|
| `manifest.json` | 代码提交、脏状态/源码指纹、依赖、数据集/来源/配置/输入 hash、seed、fixture 模型与模式 |
| `results.json` | 每个样例的产物、指标、错误、fixture 调用次数 |
| `summary.json` | 每例终态计数、每项指标实际评分分母和状态计数 |

`dirty_diff_hash` 包含限定源码范围的 tracked diff 与 untracked 源码指纹；不保存 diff 正文或环境凭据。`prompt_hash` 当前表示白名单回放输入的 hash，不是一个真实供应商 prompt。输出目录被忽略提交且不覆盖已有目录。提供 `--out` 指向其他路径时，同样应把产物留在本机。

退出码：0 为选定工程检查通过，1 为候选得到有效评分但不达标，2 为配置/数据错误或执行错误。执行过程中的 fixture miss 会在结果中记录 error；加载前就发现的坏配置不会创建成功结果。

## 错误与指标兼容性

新框架使用 passed/failed/error/skipped/not_applicable。只有 passed/failed 可以携带 0–1 范围的有限分数。聚合对 error/skipped/N/A 分别计数；有效 0 分不会被剔除。必需指标缺失或不可评分时门禁阻止通过，完整评分本身也不等于达到质量阈值。

旧 `MetricResult.skipped` 为旧调用者保留：error 也仍表示“没有可用分数”，但新增 `status` 明确区分原因。旧字典键不变，错误哨兵保留 `status=error`；`is_skipped` 继续帮助旧调用方跳过不可计算分数。解析、提取、逐项裁判和来源权威性裁判失败都不会伪装成有效 0 分或规则分数；未配置来源权威性裁判时，原有规则回退仍可使用。

`legacy_domain_reference_alignment` 复用已有引用函数，仅比较域名集合。它不是精确 URL 引用正确率，更不是 claim-evidence 语义支持度。重复引用、同域不同文章都不能单靠这个指标判断正确性。

## 运行验收

```powershell
$env:TDR_BLOCK_NETWORK = '1'
$env:LANGSMITH_TRACING = 'false'
$env:LANGCHAIN_TRACING_V2 = 'false'
.venv/Scripts/python.exe -m pytest tests/runtime tests/backend/test_task_contracts.py tests/evals tests/test_quality_metrics.py -q
```

恢复小样需要 requirements-m0 的可选依赖；没有 LangGraph SQLite 时，相关测试会明确 skip，其余离线测试仍可运行，不能将 skip 当成已验证恢复。

前端契约与构建：

```powershell
# 在 frontend/nextjs 中，沿用 Dockerfile 的安装方式
npm ci --legacy-peer-deps --ignore-scripts --no-audit --no-fund
npm run build
# 回到仓库根目录
node scripts/check_research_contract_types.mjs
```

类型校验脚本把共享 JSON 样本作为虚拟 TypeScript 源文件交给编译器，没有写入应用源码。已有业务页面、HTTP 与 WS 协议保持原运行路径，完整研究需要应用依赖与供应商配置，本阶段没有执行真实研究任务。

## 已知业务基线

以下来自原项目静态源码核对，M0 没有把它们标成已修复：断开 WS 仍会取消当前连接任务；历史保存仍主要由前端完成；移动端仍有独立聊天入口；人工反馈仍未接入持久审核；多代理超限接受路由仍需 M2 修正；逐论断证据持久化仍需 M3。M0 的绿色回放检查不覆盖这些线上用户流程。
