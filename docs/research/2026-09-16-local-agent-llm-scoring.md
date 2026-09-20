# Research: 本机自动化 + LLM 简历打分架构（2026-09-16）

引用自公开资料检索（最多 2 次主题搜索），供方案选型引用。

## 浏览器自动化

来源要点：

- 本机招聘类自动化常见形态：**API/控制台 → 队列 → Playwright Worker → 审计库**。
- 长期登录招聘账号优先用 **Playwright persistent context / 持久化浏览器 Profile**，而不是一次性 `storageState` 快照（便于人工接管、续跑、保持会话）。
- Worker 与 API 分离更稳；MVP 可同机进程，但任务要可重试、有幂等键与证据截图。

参考：

- https://www.technetexperts.com/scalable-browser-automation-queue-architecture/
- https://dev.to/web4browser/playwright-storagestate-vs-persistent-context-which-one-should-you-use-for-multi-account-k86
- https://github.com/nmdra/AgentHire（FastAPI + SQLite + 评估流水线参考）

## LLM 简历 × JD 匹配

来源要点：

- 主流稳健做法是 **硬约束过滤 →（可选）语义/规则特征 → 打分 → 可解释理由**。
- 不少方案主张：**确定性算分 + LLM 只写理由**，降低幻觉与不可复现；也有产品采用 **单次 LLM 直接出分+理由**（实现快，需强 schema/校验）。
- 本项目用户已选定「LLM 细打分 + 固定阈值打招呼」；设计上应强制 JSON schema、引用证据字段，并保留硬筛在 LLM 之前。

参考：

- https://www.respan.ai/resources/ai-sourcing-agent
- https://github.com/Muskanbawistale/semantic-resume-ranking-system
- https://github.com/Eslamelzamkan/talent-scout-screening

## 对本项目的含义

| 决策 | 建议 |
|------|------|
| 跑 BOSS | 本机 headed Playwright + 持久化 Profile |
| 共享库 | 内网 FastAPI（或等价）+ 文件存储 + DB |
| 打分 | 硬筛本地算；细分调 LLM；分数未达阈值不打招呼 |
| 交换冷却 | 共享库记录 `exchange_events`，30 天窗口全员可见 |
