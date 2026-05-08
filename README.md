# stock-research-tracker

个人使用的 A 股自选股经营信息跟踪与投资假设复核系统。

本项目不是自动荐股系统，不做自动交易、量化回测、因子选股或实时行情，也不输出买卖建议、目标价或短期股价预测。

## 当前功能

- 自选股公司管理和公司详情页
- 公告、新闻、财务采集入口
- 数据源 adapter、采集记录、失败记录和 local fallback 标记
- 信息流来源追踪
- 人工复核闭环：确认、驳回、编辑后确认
- 投资假设详情和假设验证
- 统一证据详情页
- 研究记录和证据引用链
- 买入前纪律检查表：人工填写逻辑、证据、风险、仓位和证伪预案
- 研究快照 Markdown 草稿
- Dashboard 今日研究工作台

## 本地启动

```bash
cp .env.example .env
docker compose up -d --build
```

本机访问：

- Web: `http://127.0.0.1:8324/`
- Health: `http://127.0.0.1:8324/api/health`
- API Docs: `http://127.0.0.1:8324/docs`

本机 Docker 由 OrbStack 管理时，仍使用标准 `docker` / `docker compose` 命令。

## 常用页面

- 工作台：`/`
- 信息流：`/feed`
- 人工复核：`/review`
- 公司详情：`/companies/1`
- 采集调试：`/ingestion`
- 证据详情：`/evidence/3`
- 研究记录：`/research-notes`
- 纪律检查：`/discipline-checks`
- 研究快照：`/report-drafts/new`

## 本地验证命令

后端必须使用项目虚拟环境：

```bash
.venv/bin/python -m compileall backend/app
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests
```

前端：

```bash
cd frontend
npm run build
```

容器：

```bash
docker compose up -d --build
```

## 注意事项

- 前端生产 API baseURL 默认为 `/api`。
- Vite `base` 为 `/`，适合部署在站点根路径。
- 自动采集数据默认进入 `pending`，必须人工复核。
- `local` source 是本地 fallback，不代表外部真实新数据。
- 研究快照只是已有内容整理，不是投资建议。
- 纪律检查只用于个人流程约束，不代表系统建议买入，也不会执行交易。

更多说明见：

- [用户使用指南](docs/user-guide.md)
- [系统概览](docs/system-overview.md)
- [Backlog](docs/backlog.md)
- [技术债记录](docs/technical-debt.md)
