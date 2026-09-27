# Resume Screening

本机 Playwright Agent + 云端 FastAPI 简历库（JWT / API Key）。  
规格：`docs/superpowers/specs/2026-09-16-boss-resume-screening-design.md`  
云端鉴权改版：`docs/superpowers/specs/2026-09-16-cloud-auth-design.md`

## 本地开发

```bash
python -m pip install -e packages/domain
python -m pip install fastapi uvicorn sqlalchemy python-multipart pydantic-settings pypdf python-docx httpx pytest pyjwt bcrypt playwright
cp .env.example .env

# API（Windows PowerShell 用分号分隔 PYTHONPATH，macOS/Linux 用冒号）
PYTHONPATH="apps/api/src:packages/domain/src" python -m uvicorn resume_api.main:app --reload --port 8000

# Web
cd apps/web && npm install && npm run dev
```

1. 打开管理台注册首个用户（自动成为 HR 总负责人）。
2. 生产环境注册默认关闭；由 HR 总负责人创建、停用、启用 HR 账号，并重置临时密码。
3. 新建或重置密码后的 HR 首次登录必须修改密码，之后才能进入工作台。
4. 每位 HR 生成自己的 Agent API Key，只写入本人电脑 `.env` 的 `API_KEY`。
5. 在 HR 本机启动 Agent：

```bash
PYTHONPATH="apps/agent/src:packages/domain/src:apps/api/src" python -m resume_agent login
PYTHONPATH="apps/agent/src:packages/domain/src:apps/api/src" python -m resume_agent run --live
```

## 云服务器 Docker Compose

在 `deploy/.env` 至少设置以下变量，再启动服务：

```dotenv
POSTGRES_PASSWORD=请使用随机强密码
JWT_SECRET=请使用足够长的随机字符串
CORS_ORIGINS=https://你的管理台域名
LLM_API_KEY=第三方大模型密钥
```

```bash
cd deploy
docker compose config
docker compose up -d --build
```

- Compose 缺少数据库密码、JWT 密钥或明确的 CORS 来源时会直接拒绝启动，避免误用示例值进入生产。
- 只有 Nginx 暴露端口；API、Web 和 PostgreSQL 仅在容器内部网络通信。
- 入口应使用 `https://你的域名/`，并在外层配置 HTTPS 证书；`ALLOW_REGISTER` 默认是 `false`。
- 停用账号是软停用：禁止该 HR 登录和调用接口，但不删除历史数据。
- 第三方大模型的 `LLM_API_KEY` 只放在 API 服务器或 Secret 管理系统。Web 和本机 Agent 都不得持有它。
- 本机 Agent 只持当前 HR 的个人系统 `API_KEY`，并通过 `API_BASE_URL=https://你的域名` 调用后端。
- `BROWSER_USER_DATA_DIR` 包含招聘账号登录状态，`SCREENSHOT_DIR` 和 `DOWNLOAD_DIR` 可能包含候选人隐私。三类目录必须留在 HR 本机，不得挂载到云服务器、同步盘、代码仓库或共享目录。

## 自动测试

```bash
make test-domain
make test-api
make test-agent
make test-web
make typecheck-web
make build-web
make test-all
git diff --check
```

`make test-all` 会依次运行领域、API、Agent、Web 组件测试、Vue TypeScript 类型检查和 Web 生产构建。

## 迁移验证边界

- SQLite：必须先复制 legacy 数据库，在副本上连续执行两次迁移；两次都应成功，并核对候选人、简历、评分、联系记录数量以及外键完整性。
- PostgreSQL：只有在真实 PostgreSQL 测试库完成 DDL、回填、唯一约束和合并撤销事务测试后，才能标记为“已验证”。仅凭 SQLite 测试或 Docker 配置不能作此声明。
- 任何迁移都先备份，禁止直接拿唯一的生产数据库试跑。

## 人工验收

本地 fixture（测试数据）需覆盖：1 人、50 人、页面不足、关键资料缺失、全局重复联系、发送确认失败、断点恢复、风控暂停。

真站只能人工小批量验收：

1. HR 登录 BOSS，并亲自设置岗位、筛选条件和排序；Agent 不得修改筛选器。
2. 运行极小批次，观察采集、评分、复核和联系记录。
3. 验证码、频控或其他风控出现后，确认 Agent 立即暂停；不得绕过验证码。
4. 确认只有页面明确显示发送成功时才记为已联系；失败或结果未知不得记成功。
5. CI、自动测试和无人值守任务不得访问 BOSS 真站。

## 合规

自动化招聘平台操作可能违反平台协议。仅使用本人有权操作的招聘账号，遵守平台条款、候选人隐私与数据保留要求；限速、遇风控停机、不绕过验证码，平台合规结论需由公司负责人或法务人工确认。
