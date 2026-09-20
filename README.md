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

1. 打开管理台注册首个用户（自动 admin）  
2. 生成 API Key，写入本机 `.env` 的 `API_KEY`  
3. Agent：

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
- 生产建议：`ALLOW_REGISTER=false`，由 admin 开户；配置 HTTPS 证书  
- 本机 Agent：`API_BASE_URL=https://你的域名`，`API_KEY=rs_...`

## 测试

```bash
make test
```

## 合规

自动化 BOSS 可能违反平台协议。限速、风控停机、不绕过验证码；仅用本人招聘账号。
