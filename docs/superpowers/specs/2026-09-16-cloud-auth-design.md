# 云端部署 + 登录鉴权 — 架构改版规格

- 日期：2026-09-16
- 状态：已批准（用户确认）
- 基线规格：[2026-09-16-boss-resume-screening-design.md](./2026-09-16-boss-resume-screening-design.md)
- 相关调研：
  - [docs/research/2026-09-16-cloud-auth-architecture.md](../../research/2026-09-16-cloud-auth-architecture.md)
  - [docs/research/2026-09-16-fastapi-structure.md](../../research/2026-09-16-fastapi-structure.md)

## 1. 改版目标

将简历库与管理台从「内网 NAS + 全局 API Token」改为 **云服务器公网部署 + 用户登录鉴权**；BOSS Playwright Agent **仍在招聘同学本机**，通过个人 API Key 调用云端 API。

### 1.1 成功标准

- 用户可通过账号密码注册/登录管理台；受保护 API 必须带有效 JWT。
- 用户可生成/吊销个人 API Key；本机 Agent 仅凭 API Key 访问业务接口。
- 单机 Docker Compose 可拉起 Nginx + API + PostgreSQL + 文件卷。
- 业务能力（硬筛、打分、招呼、简历库、交换冷却）行为不变，仅部署与鉴权层替换。

### 1.2 非目标

- 多租户（多公司数据隔离）
- 飞书/OAuth 第三方登录（可二期）
- Agent 上云、对象存储（OSS/S3）
- 生产环境默认开启文件夹监视入库

## 2. 已确认决策

| 项 | 选择 |
|----|------|
| Agent 位置 | 本机（A） |
| 鉴权 | 账号密码 + JWT；Agent 用个人 API Key（A） |
| 上云形态 | 单机 Docker Compose（方案 1） |
| 数据范围 | 单实例内团队共享简历库；不做公司级租户 |

## 3. 目标架构

```
[招聘本机]                              [云服务器 Docker Compose]
 Playwright Agent                        Nginx (HTTPS)
  BOSS Profile（本机）                    ├─ Vue 静态管理台
  → 硬筛 / LLM / 打招呼 / 附件            ├─ FastAPI
  → HTTPS + X-Api-Key                     ├─ PostgreSQL
                                          └─ resume_files 卷
```

边界：

- 云端持有用户、JD、简历、交换、审计。
- 本机不存简历主数据。
- 废弃：内网 NAS 作为生产部署、全局共享 `API_TOKEN` / `X-Api-Token` 作为唯一鉴权。

## 4. 鉴权设计

### 4.1 用户

- `User`：`id`, `username`（或 email）, `password_hash`（bcrypt）, `role` ∈ {`admin`,`member`}, `is_active`, `created_at`
- 首个注册用户自动 `admin`
- `ALLOW_REGISTER`：生产默认 `false`；关闭后仅 admin 开户（`POST /auth/users` 或管理台）

### 4.2 Web 会话（JWT）

- `POST /auth/register`（受 `ALLOW_REGISTER` 约束）
- `POST /auth/login` → `{ access_token, refresh_token, token_type: "bearer" }`
- Access 默认 2h；Refresh 默认 14d（MVP 可先响应体返回；Web 存 sessionStorage/memory）
- `POST /auth/refresh` 换发 access
- 业务接口：`Authorization: Bearer <access_jwt>`
- `GET /auth/me` 当前用户

### 4.3 Agent API Key

- `ApiKey`：`id`, `user_id`, `name`, `key_prefix`, `key_hash`, `created_at`, `revoked_at`
- 创建时返回一次性明文（如 `rs_` + 随机）；之后不可再读明文
- Agent 请求头：**`X-Api-Key: <plaintext>`**（固定此一种，避免与 JWT Bearer 混淆）
- 管理台：列表（前缀+名称）、创建、吊销
- 校验：哈希比对且未吊销且用户 `is_active`

### 4.4 统一鉴权依赖

- FastAPI dependency：接受 **JWT 或 API Key** 之一，解析为 `CurrentUser`
- 审计字段：`actor_user_id` 写入 Exchange / Score / Outreach / AgentRun / Resume（可空兼容旧行）

### 4.5 权限（MVP）

| 角色 | 能力 |
|------|------|
| member | 简历库 CRUD、JD、交换标记、自己的 API Key、看 Agent 状态 |
| admin | member 全部 + 开户/停用用户 + `ALLOW_REGISTER` 等全局配置 |

不做按岗位 ACL。

### 4.6 废弃与兼容

- 生产：禁用全局 `API_TOKEN`
- 本地开发：可用 `DEV_API_TOKEN` 旁路（仅 `ENV=development`），测试保持简单

## 5. 部署设计

### 5.1 Compose 服务

| 服务 | 说明 |
|------|------|
| `nginx` | 443、静态 Vue、反代 `/api`、`/auth` |
| `api` | FastAPI + uvicorn |
| `db` | PostgreSQL 16 |
| volumes | `pgdata`, `resume_files` |

### 5.2 配置（环境变量）

- `DATABASE_URL`（Postgres）
- `JWT_SECRET` / `JWT_ACCESS_MINUTES` / `JWT_REFRESH_DAYS`
- `ALLOW_REGISTER`
- `CORS_ORIGINS`
- `STORAGE_DIR`（指向文件卷）
- `ENV=production|development`

### 5.3 存量简历

- 生产默认：**Web 批量上传**
- 云端文件夹监视：非默认；可选配置但不作为上云必做

### 5.4 本机 Agent 配置

```env
API_BASE_URL=https://your-domain.com
API_KEY=rs_xxxx
```

删除对全局 `API_TOKEN` 的生产依赖。

## 6. 数据模型增量

在基线模型上增加：

- `User`, `ApiKey`
- 业务表可选 `actor_user_id`（FK → User，可空）
- `ExchangeEvent.operator` 保留展示名；同时写 `actor_user_id` 便于审计

生产文件路径落在云盘卷，不再表述为「NAS」。

## 7. Web 改动要点

- 登录 / 注册页（受配置）
- 路由守卫：无 JWT 跳转登录
- API 客户端带 Bearer
- 「API 密钥」页：创建、复制一次、吊销
- 去掉仅依赖 localStorage 全局 Token 的简易模式（可迁移为登录后 JWT）

## 8. Agent 改动要点

- `ApiClient`：`X-Api-Key` 替代 `X-Api-Token`
- 配置项：`api_key`；保留 `api_base_url`
- 401/403：心跳标红并停止新招呼

## 9. 测试

- 注册/登录/刷新 JWT
- 无凭证 401；错误密码 401
- API Key 创建后可访问；吊销后 401
- JWT 与 API Key 均可写交换事件且带 `actor_user_id`
- admin 开户；member 不能开户
- Compose smoke：健康检查 + 登录（实现计划阶段）

## 10. 实现切片（建议顺序）

1. User/ApiKey 模型 + auth 路由 + 双凭证 dependency  
2. 替换现有路由鉴权；加 `actor_user_id`  
3. Agent / Web 改凭证  
4. Postgres + Docker Compose + Nginx 模板  
5. README 上云步骤；`ALLOW_REGISTER` 生产关闭说明  

## 11. 风险

| 风险 | 缓解 |
|------|------|
| JWT_SECRET 泄露 | 环境变量/密钥管理；轮换需重登 |
| API Key 泄露 | 仅显示一次、可吊销、前缀便于排查 |
| 公网暴露简历 | HTTPS 强制；鉴权全覆盖；定期备份 |
| SQLite→Postgres 差异 | 开发可用 SQLite；CI 可选 Postgres；Compose 用 Postgres |

## 12. 对基线规格的覆盖声明

本文件生效后，基线中以下表述以本文件为准：

- 「内网 NAS/小主机」→ 云服务器 Compose  
- 「内网账号或 Token / 服务 Token」→ JWT + 个人 API Key  
- 生产库 → PostgreSQL  
- 文件夹监视 → 非云端默认路径  
