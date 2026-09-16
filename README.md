# Resume Screening MVP

本机 Playwright/HTML 快照 Agent + 内网 FastAPI 简历库。规格见 `docs/superpowers/specs/2026-09-16-boss-resume-screening-design.md`。

## 结构

- `packages/domain`：硬筛、指纹、LLM schema、打招呼决策
- `apps/api`：内网 API、SQLite、文件存储、文件夹监视
- `apps/agent`：本机流水线与 CLI（`--fixture` 跑通；真站选择器需校准）
- `apps/web`：Vue 3 管理台

## 快速开始

```bash
python -m pip install -e packages/domain
python -m pip install fastapi uvicorn sqlalchemy python-multipart pydantic-settings pypdf python-docx httpx pytest
copy .env.example .env

# 启动 API（默认 Token: dev-token-change-me）
python -m uvicorn resume_api.main:app --app-dir apps/api/src --reload --port 8000

# 管理台
cd apps/web && npm install && npm run dev

# Agent 用 fixture 跑一轮（需 API 已启动且有启用岗位）
python -m resume_agent.cli run --fixture tests/fixtures/boss_list.html
```

共享文件夹默认监视 `./data/inbox`，稳定写入后自动入库。

## 测试

```bash
make test
```

## 合规说明

自动化操作 BOSS 直聘可能违反平台协议并有封号风险。本系统限速、检测风控页后停机，不绕过验证码。请仅使用本人招聘账号，并自行评估合规。

## 真站验收清单

1. 本机登录 BOSS 招聘端并确认会话
2. 校准 `resume_agent/parse_page.py` 选择器后接入 Playwright
3. 验证硬筛、打分、打招呼、附件下载、入库与交换冷却
