# Research: Playwright 真站持久登录（2026-09-16）

## 结论

- 招聘账号长期会话优先 `chromium.launch_persistent_context(user_data_dir, headless=False)`，使用**独立空目录**作为自动化 Profile，勿指向日常 Chrome User Data。
- 首次运行：打开登录页 → 人工完成登录/验证码 → 正常关闭以落盘；后续复用同一目录。
- 同一 `user_data_dir` 不可多开。
- 若会话 Cookie 丢失，可尝试 `channel="chromium"` 或启动参数 `--restore-last-session`（副作用：恢复上次标签页）。

## 对本项目

- CLI：`login`（人工登录）、`run --live`（真站一轮）、保留 `--fixture`。
- 选择器外置 `boss_selectors.json`，DOM 变更只改配置。
- 风控关键词命中：截图 + 心跳 `paused` + 停机。

## 参考

- https://playwright.dev/python/docs/api/class-browsertype
- https://playwright.dev/python/docs/auth
- https://www.browserstack.com/guide/playwright-persistent-context
