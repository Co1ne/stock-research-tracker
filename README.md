# stock-research-tracker

个人使用的 A 股自选股经营信息跟踪系统，定位是“经营信息跟踪 + 投资逻辑验证”。它不是量化交易系统，不做自动交易、回测或因子选股。

## Quick Start

```bash
cp .env.example .env
docker compose up -d --build
```

启动后访问：

- Web: `http://<server-ip>:8324/`
- Health: `http://<server-ip>:8324/api/health`
- FastAPI docs: `http://<server-ip>:8324/docs`

## Local Frontend Build Check

不依赖 Docker 时，可以先在开发环境验证前端构建：

```bash
cd frontend
npm install
npm run build
```

期望结果：

- `frontend/dist/index.html` 存在。
- `frontend/dist/assets/` 存在，并包含带 hash 的 `.js` / `.css` 文件。
- `dist/index.html` 中资源路径以 `/assets/` 开头，适合部署在站点根路径。

## Blank Page Troubleshooting

如果部署后页面空白，但 Network 请求基本都是 `200`，优先检查浏览器 Console：

- 是否有 JS runtime error。
- 是否有 MIME type error。
- 是否有 `Failed to resolve module`。
- 是否有 `Cannot read properties of undefined`。
- 是否有 `process is not defined`。
- 是否请求了 `http://backend:8000`。浏览器不能访问 Docker 内部 hostname，生产前端应请求 `/api`。

Network 重点检查：

- `/` 或 `/index.html` 是否返回 `200`。
- `/assets/*.js` 是否返回 `200`，且 `Content-Type` 是 `application/javascript` 或等价 JS MIME。
- `/assets/*.css` 是否返回 `200`，且 `Content-Type` 是 `text/css`。
- JS 文件响应体是否真的是 JavaScript，而不是 `index.html`。
- `/api/health` 是否返回 `200` 和 `{"status":"ok"}`。
- API 请求是否走 `/api/...`，而不是 `http://backend:8000/...`。

服务器上可手动执行的验证命令：

```bash
docker compose ps
docker compose logs frontend --tail=100
docker compose logs nginx --tail=100
docker compose logs backend --tail=100
curl -I http://127.0.0.1:8324/
curl -I http://127.0.0.1:8324/assets/<actual-js-file-name>
curl -I http://127.0.0.1:8324/api/health
```

如果请求都是 `200` 但页面仍空白，最关键检查：

- JS 文件是不是返回了 HTML。
- Console 是否有运行时错误。
- App 是否挂载到 `#app` 并渲染了 `router-view`。
- API baseURL 是否写死为 `backend:8000`。
- 数据为空时是否访问了 `undefined.xxx`。

## API

- `GET /api/health`
- `POST /api/companies/initialize`
- `GET /api/companies/initialize/{task_id}`
- `POST /api/companies/initialize/{task_id}/confirm`
- `POST /api/fetch/announcements`
- `POST /api/fetch/news`
- `POST /api/fetch/financials`
- `GET /api/fetch/status`
- `GET /api/jobs/runs`
- `GET /api/announcements`
- `GET /api/news`
- `POST /api/companies`
- `GET /api/companies`
- `POST /api/business-lines`
- `POST /api/mock/announcement`
- `POST /api/mock/news`
- `POST /api/announcements/{id}/analyze-logic`
- `POST /api/news/{id}/analyze-logic`
- `POST /api/logic-analysis/run-pending`
- `GET /api/companies/{id}/evidence`
- `GET /api/business-lines/{id}/evidence`
- `GET /api/companies/{id}/logic-summary`
- `POST /api/reports/daily`

## Notes

- 前端生产 API baseURL 默认为 `/api`，可通过 `VITE_API_BASE_URL` 覆盖。
- Vite `base` 明确配置为 `/`，适合部署在 `http://ip:port/` 根路径。
- 前端 Nginx 只对页面路由 fallback 到 `index.html`；`/assets/` 找不到会返回 `404`，避免 JS/CSS 请求错误地拿到 HTML。
- 真实数据源默认使用 AKShare。mock 新闻/公告接口仅用于测试和兜底，不作为主流程。
- 后端本地验证必须使用 `.venv`：`.venv/bin/python -m compileall backend/app`，以及 `cd backend && ../.venv/bin/python -m pytest`。
