# Research: 云端部署 + SPA 登录鉴权（2026-09-16）

## 结论（面向本项目）

- **API + Web 上云**：FastAPI + PostgreSQL（或托管 DB）+ 对象存储存简历；Vue SPA 走 HTTPS。
- **鉴权主流**：OAuth2 Password + JWT（FastAPI 官方模式）；更稳妥为短时 access token + refresh（HttpOnly cookie / 或 Agent 用 long-lived API key 分端）。
- **Agent 不宜默认上云 headed**：BOSS 登录/验证码依赖真人与本机环境；推荐 **本机 Agent → 云端 API（用户 JWT 或机器凭证）**。
- Docker Compose（API + Postgres + Nginx 静态前端）是小团队上云常见起步。

## 参考

- https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/
- https://github.com/jason810496/FastAPI-Vue-OAuth2
- https://github.com/persteenolsen/vue-fastapi-jwt-reuse-detection-httponly-client
