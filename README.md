# Resume Screening

本机 Playwright Agent + 云端 FastAPI 简历库（JWT / API Key）。  
规格：`docs/superpowers/specs/2026-09-16-boss-resume-screening-design.md`  
云端鉴权改版：`docs/superpowers/specs/2026-09-16-cloud-auth-design.md`

## 本地开发

```bash
python -m pip install -e packages/domain
python -m pip install fastapi uvicorn sqlalchemy python-multipart pydantic-settings pypdf python-docx httpx pytest pyjwt bcrypt playwright
copy .env.example .env

# API
$env:PYTHONPATH="apps/api/src;packages/domain/src"
python -m uvicorn resume_api.main:app --reload --port 8000

# Web
cd apps/web && npm install && npm run dev
```

1. 打开管理台注册首个用户（自动成为 HR 总负责人）
2. HR 总负责人可创建、停用、启用普通 HR，并重置其临时密码
3. 新建或重置密码后的 HR 首次登录必须修改密码，之后才能进入工作台
4. 每位 HR 生成并使用自己的 Agent API Key，将其写入本人电脑 `.env` 的 `API_KEY`
5. Agent：

```bash
$env:PYTHONPATH="apps/agent/src;packages/domain/src;apps/api/src"
python -m resume_agent login
python -m resume_agent run --live
```

## 云服务器 Docker Compose

```bash
cd deploy
# 务必修改 docker-compose.yml 中 JWT_SECRET / 数据库密码
docker compose up -d --build
```

- 入口：`http://服务器IP/`（Nginx → Web + `/api` + `/auth`）  
- 生产建议：`ALLOW_REGISTER=false`，由 HR 总负责人开户；配置 HTTPS 证书
- 停用账号是软停用：禁止该 HR 登录和调用接口，但不删除历史数据
- 本机 Agent：`API_BASE_URL=https://你的域名`，`API_KEY=rs_...`；每位 HR 使用自己的个人系统 API Key
- 第三方大模型的 `LLM_API_KEY` 只配置在 API 服务器或 Secret 管理系统中。Agent 统一调用后端评分接口，不保存或直连第三方密钥

## 测试

```bash
make test-all
```

`make test-all` 会依次运行 Python 测试、Web 组件测试和 Web 生产构建。

## 合规

自动化 BOSS 可能违反平台协议。限速、风控停机、不绕过验证码；仅用本人招聘账号。
