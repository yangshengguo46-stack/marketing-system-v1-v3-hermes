---
name: operate-social-platforms
description: Operate a user's bound social-media account through the account-aware Marketing Browser MCP. Use for platform login checks, creator-center data collection, content editor actions, draft preparation, publishing, post verification, metric collection, or recovery from uncertain browser outcomes on Douyin, Zhihu, WeChat Official Accounts, Xiaohongshu, Bilibili, Channels, or TikTok.
---

# Operate social platforms

Use the current Hermes conversation account scope. Never ask the model to choose or restate an
`account_id` when the conversation is already bound; Hermes injects it into the MCP call.

## Run the workflow

1. Read the current account context before making account-specific decisions.
2. Open or inspect the platform with the Marketing Browser MCP. Start with `browser_snapshot`;
   navigate only when the current page is not useful.
3. Detect login from visible creator identity or an authenticated creator page. Do not infer login
   from a successful page load alone.
4. If login is required, open the official login page in headed mode, explain the single user action
   needed, then wait and verify the authenticated page. Never request, print, copy, or summarize
   cookies, tokens, QR payloads, passwords, or verification codes.
5. For read operations, capture the visible source, collection time, account, platform, and missing
   fields. Preserve unknown as unknown; never convert it to zero.
6. For editor operations, use the approved ContentAsset platform variant. Save or preview before any
   irreversible action.
7. Before final publish, require the native publish action and one-shot approval path. A browser click
   is not proof of success.
8. Verify success from the resulting work page, platform post ID, stable post URL, or creator-center
   work list. If verification is absent, report `unknown` and query before retrying.

## Browser discipline

- Use only the account-scoped Marketing Browser MCP for the bound platform. Generic
  `browser_*` tools run in a separate temporary profile and are never a fallback for
  account login, creator data, drafts, publishing, metrics, or verification.
- If the account-scoped MCP tool is unavailable, report the internal capability as
  unavailable and stop. Do not open the platform in another browser backend.
- Prefer accessibility snapshot refs and form tools over coordinate clicks or arbitrary JavaScript.
- Use `browser_evaluate` only for read-only extraction when the snapshot cannot expose the field.
- Do not use `browser_run_code_unsafe` for login, publishing, deletion, payment, messages, or account
  settings.
- Stay inside the bound platform account. Never navigate to another account profile to borrow login.
- Re-snapshot after navigation, dialog handling, account switch, editor mode change, or failed action.
- Stop on captcha, risk-control verification, unexpected account identity, or ambiguous destructive UI
  and ask for the minimum human action.

Read [references/platform-boundaries.md](references/platform-boundaries.md) when the task involves
publishing, account switching, risk control, or post verification.
