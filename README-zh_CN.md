# Traceable Deep Researcher

由 **Piao666** 维护的自托管研究应用，支持网络/本地文档研究、报告生成和追问。

- [项目仓库](https://github.com/piao666/Traceable-Deep-Researcher)
- [联系邮箱](mailto:dahaipiao9@gmail.com)
- 复制 `.env.example` 为 `.env`，配置模型和搜索服务，执行 `docker compose up --build -d`。
- 默认界面：[localhost:8000](http://localhost:8000)。
- Next.js 界面：`docker compose --profile web up --build -d`，访问 [localhost:3000](http://localhost:3000)。

当前已有研究、来源链接、日志和报告保存；参考项目中的正文快照、原文坐标、Claim 证明与报告溯源尚未合入。
Python/npm 包及 Codex 插件是后续方向，本轮未发布。

参见 [说明](README.md)、[部署](docs/deployment.md)、[架构](docs/architecture.md)、[迁移](docs/migration.md)及 [来源](UPSTREAM.md)。
