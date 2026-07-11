# MCP Sync Navigation & Parsing Incident Ledger

## Date
2026-07-03

## Summary
记录本轮 MCP 同步尝试、确认有效的部分和安全复核后的撤回项。本文不是“全部修复完成”的声明。

## Codex Audit Correction（2026-07-03）

- 保留：重登复用账号 ID、近 7 日播放语义、作品列表解析、只读 SPA tab 点击。
- 修复：视频指标 API 改用产品 `HermesAgentService` 持有的 Store；原 `AgentCoreStore.instance()` 并不存在。
- 撤回：任意 `browser_evaluate`、导出/下载/“确定”点击、无条件删除 Chromium Singleton 锁。
- 隐私：移除无条件写入 50KB 原始 snapshot；调试数据不得默认落盘。
- 真实性：数据中心导航未验证成功时返回空，不得用“文本长度足够”把主页冒充数据中心页面。
- 性能：默认同步不再调用已知失败的数据中心路由；仅在 `MARKETING_OS_MCP_DATA_CENTER_EXPERIMENTAL=1` 时实验，结果明确返回 `ok/unavailable`。
- 指标口径：取消把累计获赞与不同窗口的评论/分享相加成“interaction”；保留原始字段，等待同窗口指标后再计算。

## Changes Made

### 1. Account Identity: `_persist_mcp_authenticated_account` (server.py)
**Problem:** Re-login always created a new account with placeholder identity instead of reusing the existing account.
**Fix:** Check if account already exists by ID; if so, update status to `connected` instead of creating a new one.

### 2. Total Views Parsing (server.py)
**Problem:** `total_views` was parsed from video list items (e.g. 178.2万) or ref numbers (e.g. 256 from `ref=e256`), not the actual data center 7-day view count.
**Fix:** New `dc_views` regex matches the nested data center structure: `播放量 → container → "14"`. Falls back to profile header views if data center value not found.
**Note:** The value is **7-day views**, not cumulative. Frontend label updated from "累计播放" to "近7日播放".

### 3. Sub-page Navigation via SPA Click (server.py)
**Problem:** `browser_navigate` to `/creator-micro/content-manage` and `/data-center/follow-data` didn't trigger SPA route changes. Content manage page stayed on home; data center page only rendered sidebar.
**Fix:** `_mcp_snapshot_for_url` now:
1. Takes a snapshot to find the menu item's Playwright ref
2. Uses `browser_click` with `{element, target}` to click the menu item
3. Waits for SPA route to settle
4. Retries snapshot with longer delays (3+4+5+5s vs 2+3+3s)
5. 以路由专属可解析证据验证成功，不再以文本长度冒充页面到达
6. Dismisses blocking dialog popups ("我知道了") before taking final snapshot

### 4. Browser Click Policy (mcp_browser_policy.py)
**Changes:**
- Added `数据中心` to `_ACCOUNT_SYNC_CLICK_LABELS` whitelist
- 仅保留无副作用的 `我知道了`；语义不明确的 `确定` 已移除
- Relaxed `target` regex from `e\d{1,8}` to `[a-z0-9]{1,12}` to support ref formats like `e54`, `f3e940`

### 5. Frontend Label (Accounts.tsx)
- Changed "累计播放" to "近7日播放"

## Current Status

### Working
- ✅ Home page snapshot 可解析脱敏账号身份和基础指标（台账不记录真人昵称与完整平台 ID）
- ✅ Content manage page: 11.6K chars, 4 videos with per-video metrics (play, like, comment, share)
- ✅ Dialog dismissal: "我知道了" popup dismissed successfully
- ✅ Account identity persistence: re-login reuses existing account
- ✅ Total views: correctly parsed as 7-day views (14) from data center

### Not Working
- ❌ Data center page navigation: clicking `数据中心` menu item does not trigger SPA route change. Page stays on home. The click executes but SPA doesn't navigate. Possible causes:
  - The `menuitem` element may need a different click target (e.g. the parent `listitem` with `cursor=pointer`)
  - The SPA may require a specific interaction pattern (hover to expand submenu, then click sub-item)
  - The `browser_click` may be clicking the wrong ref (menuitem vs listitem)
  - **Next step:** Try clicking the `listitem` parent (which has `cursor=pointer`) instead of the `menuitem` child, or try `browser_navigate` to the data center URL after dismissing any dialogs

## Files Modified
- `engine/marketing-os/server.py` — `_persist_mcp_authenticated_account`, `_parse_creator_account_snapshot`, `_mcp_snapshot_for_url`
- `engine/agent_core/mcp_browser_policy.py` — `_ACCOUNT_SYNC_CLICK_LABELS`, `target` regex
- `src/pages/Accounts.tsx` — frontend label

## Debug Snapshot Policy

原先默认生成的三份原始 snapshot 文件已判定为隐私风险并删除。后续只有显式 trace 开关、脱敏、大小上限和保留期限同时满足时才允许落盘。

## 最终收口验证

- 2026-07-03：1084 项 pytest 全绿；TypeScript、Electron syntax、`git diff --check`、Vite production build 通过。
- 真实应用数据目录 secret scanner 通过；源码目录误生成的 `agent-runtime/` 和三份原始 snapshot 已删除并加入忽略规则。
- 新增 `tests/test_glm_incident_regression.py`，永久守卫任意 JS、导出/下载/模糊确认、Singleton 锁删除、原始 snapshot 落盘和伪 Store 单例。
