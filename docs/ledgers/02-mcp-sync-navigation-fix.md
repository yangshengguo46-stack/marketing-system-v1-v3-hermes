# MCP Sync Navigation & Parsing Fixes

## Date
2026-07-03

## Summary
Fixed MCP sync snapshot parsing for Douyin Creator Center, including account identity, total views label, and sub-page navigation via SPA click.

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
5. Validates content length ≥ 8000 chars (sidebar alone is ~3K)
6. Dismisses blocking dialog popups ("我知道了") before taking final snapshot

### 4. Browser Click Policy (mcp_browser_policy.py)
**Changes:**
- Added `数据中心` to `_ACCOUNT_SYNC_CLICK_LABELS` whitelist
- Added `我知道了`, `确定` for dialog dismissal
- Relaxed `target` regex from `e\d{1,8}` to `[a-z0-9]{1,12}` to support ref formats like `e54`, `f3e940`

### 5. Frontend Label (Accounts.tsx)
- Changed "累计播放" to "近7日播放"

## Current Status

### Working
- ✅ Home page snapshot: 47K chars, account identity (杨炎昭, 66867825385), profile stats (followers=4, likes=56, following=2)
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

## Debug Snapshot Files
Located at `~/Library/Application Support/marketing-os-desktop/config/`:
- `mcp_snapshot_debug.txt` — Home page (47K chars, working)
- `mcp_snapshot_content_debug.txt` — Content manage page (11.6K chars, working)
- `mcp_snapshot_data_debug.txt` — Data center (45K chars but still home page content, NOT working)
