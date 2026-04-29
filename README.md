# stock-research-tracker

个人使用的 A 股自选股经营信息跟踪系统（V2 轻量版）。

> 定位：经营信息跟踪 + 投资逻辑验证。不是量化交易系统，不做自动交易/回测/因子选股。

## 1. 快速启动（本地 / 服务器）

```bash
cp .env.example .env
docker compose up -d --build
```

启动后访问：

- Web 首页: `http://<你的服务器IP>:8324/`
- 健康检查: `http://<你的服务器IP>:8324/api/health`
- FastAPI 文档: `http://<你的服务器IP>:8324/docs`

---

## 2. 部署文档（Docker Compose）

### 2.1 服务器准备

建议环境：

- Linux (Ubuntu 22.04+)
- Docker 24+
- Docker Compose v2+
- 2C4G 起步

安装（Ubuntu 示例）：

```bash
sudo apt update
sudo apt install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER
```

> 执行 `newgrp docker` 或重新登录后生效。

### 2.2 拉取代码并启动

```bash
git clone <你的仓库地址> stock-research-tracker
cd stock-research-tracker
cp .env.example .env
docker compose up -d --build
```

### 2.3 常用运维命令

```bash
# 查看状态
docker compose ps

# 查看日志
docker compose logs -f backend
docker compose logs -f nginx

# 重启
docker compose restart backend

# 停止
docker compose down

# 升级后重建
git pull
docker compose up -d --build
```

### 2.4 端口与反向代理

固定对外端口为 `8324`（避免占用你机器上已有 `8080` 服务）。

如果你已有上层 Nginx / Caddy，可把域名反代到 `127.0.0.1:8324`。

### 2.5 生产建议

- 将 `POSTGRES_PASSWORD` 改为强密码（并同步 `DATABASE_URL`）。
- 定期备份 PostgreSQL volume（`pgdata`）。
- 建议配置 HTTPS（上层反代证书）。
- 建议加系统级防火墙仅开放 80/443（或你实际端口）。


### 2.6 国内服务器构建加速（Python 依赖）

项目的 `backend/Dockerfile` 已默认使用清华 PyPI 镜像：

- `https://pypi.tuna.tsinghua.edu.cn/simple`
- `--trusted-host pypi.tuna.tsinghua.edu.cn`

如果你在国内服务器执行 `docker compose build backend` 仍然较慢，可检查服务器 DNS/网络出口，或在低峰时段构建。

---

## 3. 环境变量

`.env.example` 已给出默认项：

- `DATABASE_URL`
- `AI_ENABLED`
- `AI_PROVIDER`
- `AI_API_KEY`
- `AI_BASE_URL`
- `AI_MODEL_FAST`
- `AI_MODEL_STRONG`
- `AI_ENABLE_WEB_SEARCH`
- `FETCH_ANNOUNCEMENT_ENABLED`
- `FETCH_NEWS_ENABLED`

V2 默认可用 `MockAIProvider` 跑通，无需真实 AI Key。

---

## 4. 当前能力（V2 核心）

- 公司/业务线管理
- 公告、新闻 mock 入库
- 规则分类 + 风险识别
- AI 逻辑影响判断（增强/削弱/中性/不确定）
- 业务线证据库（正负面证据沉淀）
- 逻辑摘要接口（30天统计）
- 周报逻辑验证段落生成

---

## 5. 关键 API

- `GET /api/health`
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

---

## 6. 数据备份（最小可用）

```bash
# 导出
mkdir -p backups
docker exec -t $(docker compose ps -q db) pg_dump -U postgres stock_research > backups/stock_research_$(date +%F).sql

# 导入（空库）
cat backups/your_backup.sql | docker exec -i $(docker compose ps -q db) psql -U postgres -d stock_research
```



## 7. 前端访问排查（端口改成 8324 但打不开）

```bash
# 1) 看映射是否生效
docker compose ps

# 2) 本机探活
curl -I http://127.0.0.1:8324/
curl -s http://127.0.0.1:8324/api/health

# 3) 查看 nginx 日志
docker compose logs -f nginx
```

如果 `curl /api/health` 返回 `{"status":"ok"}`，但浏览器打不开，通常是服务器安全组/防火墙未放行 `8324`。
