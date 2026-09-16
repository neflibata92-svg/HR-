# Resume Screening MVP

本机 Playwright Agent + 内网 FastAPI 简历库。规格见 `docs/superpowers/specs/2026-09-16-boss-resume-screening-design.md`。

## 结构

- `packages/domain`：硬筛、指纹、LLM schema、打招呼决策
- `apps/api`：内网 API、SQLite、文件存储、文件夹监视
- `apps/agent`：本机流水线 / fixture / **真站 Playwright**
- `apps/web`：Vue 3 管理台

## 快速开始

```bash
python -m pip install -e packages/domain
python -m pip install fastapi uvicorn sqlalchemy python-multipart pydantic-settings pypdf python-docx httpx pytest playwright
python -m playwright install chromium
copy .env.example .env

# 启动 API（默认 Token: dev-token-change-me）
python -m uvicorn resume_api.main:app --app-dir apps/api/src --reload --port 8000

# 管理台
cd apps/web && npm install && npm run dev
```

### Fixture 联调

```bash
# 需 API 已启动，并在管理台创建启用岗位
$env:PYTHONPATH="apps/agent/src;packages/domain/src;apps/api/src"
python -m resume_agent run --fixture tests/fixtures/boss_list.html
```

### 真站 Playwright

1. 编辑 `apps/agent/boss_selectors.json`（卡片/打招呼/输入框选择器，按你账号页 DOM 校准）
2. 岗位的 `boss_entry_url` 填推荐/搜索页完整 URL（或依赖 JSON 里的 `default_recommend_url`）
3. 首次登录保存 Profile：

```bash
$env:PYTHONPATH="apps/agent/src;packages/domain/src"
python -m resume_agent login
# 浏览器打开后手动登录，回到终端按 Enter
```

4. 跑真站一轮：

```bash
python -m resume_agent run --live
# 或指定入口
python -m resume_agent run --live --entry-url "https://www.zhipin.com/web/chat/recommend"
```

风控/验证码页会截图到 `data/screenshots` 并停机。招呼后会尝试下载附件并上传简历库。

共享文件夹默认监视 `./data/inbox`，稳定写入后自动入库。

## 测试

```bash
make test
```

## 合规说明

自动化操作 BOSS 直聘可能违反平台协议并有封号风险。本系统限速、检测风控页后停机，不绕过验证码。请仅使用本人招聘账号，并自行评估合规。

## 真站验收清单

1. `login` 后关闭再开，会话仍在
2. `run --live` 能识别卡片；否则校准 `card_selectors` 后重试
3. 硬筛不通过者不打招呼；达阈值者发送话术
4. 候选人回附件后入库成功
5. 管理台可标记交换并在 30 天内拦截
