"""Product closure guardrails for the desktop v0.1 shape.

These tests intentionally check only the user-facing shell and renderer
boundary. Historical ledgers, research notes, and backend compatibility routes
may still mention legacy names while the product surface stays clean.
"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def ts_array_block(source: str, name: str) -> str:
    match = re.search(rf"const {name}: Platform\[\]\s*=\s*\[(.*?)\]", source, re.S)
    assert match, f"{name} array not found"
    return match.group(1)


def test_main_sidebar_only_exposes_closure_navigation():
    source = read("src/components/AppSidebar.tsx")
    nav_block = source.split("const NAV_ITEMS = [", 1)[1].split("]", 1)[0]

    labels = re.findall(r"label: '([^']+)'", nav_block)
    ids = re.findall(r"id: '([^']+)'", nav_block)

    assert ids == ["overview", "chat", "factory", "accounts"]
    assert labels == ["工作台", "新对话", "内容工厂", "账号管理"]
    assert "const FACTORY_SUBNAV" in source
    assert "marketing-factory-subnav-collapsed" in source
    assert "nav-fold-toggle" in source
    assert "factory:article" in source
    assert "图文创作" in source
    assert "factory:video" in source
    assert "视频创作" in source
    for legacy_id in ("trending", "ideas", "analytics", "workflow", "memory", "publish"):
        assert legacy_id not in ids


def test_content_factory_secondary_routes_share_single_factory_runtime():
    app = read("src/App.tsx")
    creator = read("src/pages/Creator.tsx")
    topbar = read("src/components/TopBar.tsx")

    assert "page.startsWith('factory:') ? 'factory' : page" in app
    assert "page === 'factory:article' ? 'article'" in app
    assert "page === 'factory:video' ? 'video'" in app
    assert "'factory:article': '图文创作'" in topbar
    assert "'factory:video': '视频创作'" in topbar
    assert "mode?: FactoryMode" in creator
    assert "assetMatchesMode" in creator
    assert "article_soft" in creator
    assert "faceless_video" in creator


def test_renderer_uses_native_runtime_api_not_plugin_or_hermes_aliases():
    client = read("src/api/client.ts")
    preload = read("electron/preload.js")
    globals_ts = read("src/global.d.ts")

    assert "const BASE = '/api/marketing-os'" in client
    assert "/api/plugins/marketing-os" not in client
    assert "mOS.api" not in client
    assert "getHermesStatus" not in client
    assert "restartHermes" not in client
    assert "onHermesStatus" not in client

    assert "runtimeApi:" in preload
    assert "ipcRenderer.invoke('hermes:api'" not in preload
    assert "getHermesStatus" not in preload
    assert "restartHermes" not in preload
    assert "onHermesStatus" not in preload
    assert "api:" not in globals_ts


def test_content_production_plan_endpoint_is_native_and_allowlisted():
    client = read("src/api/client.ts")
    main = read("electron/main.js")

    assert "contentProductionPlan" in client
    assert "content/production/plan" in client
    assert "content/production/plan" in main
    assert "contentProductionPreflight" in client
    assert "content/production/preflight" in client
    assert "content/production/preflight" in main
    assert "learningCandidates" in client
    assert "learning/candidates" in client
    assert "learning/candidates" in main
    assert "weightCandidateReplay" in client
    assert "learning/weight-replay" in client
    assert "learning/weight-replay" in main
    assert "decideWeightCandidate" in client
    assert "learning/weight-decision" in client
    assert "learning/weight-decision" in main
    assert "createSoftArticleAsset" in client
    assert "content/production/article-soft" in client
    assert "content/production/article-soft" in main
    assert "createFacelessVideoAsset" in client
    assert "content/production/faceless-video" in client
    assert "content/production/faceless-video" in main
    assert "prepareFacelessRender" in client
    assert "content/production/faceless-render/prepare" in client
    assert "content/production/faceless-render/prepare" in main
    assert "renderFacelessAnimatic" in client
    assert "content/production/faceless-render/animatic" in client
    assert "content/production/faceless-render/animatic" in main
    assert "fillFacelessImageMaterials" in client
    assert "content/production/faceless-render/fill-image-materials" in client
    assert "content/production/faceless-render/fill-image-materials" in main
    assert "renderFacelessFinal" in client
    assert "content/production/faceless-render/final" in client
    assert "content/production/faceless-render/final" in main
    assert "indexTts2Status" in client
    assert "tts/index-tts2/status" in client
    assert "tts/index-tts2/status" in main
    assert "synthesizeVolcengineTtsV1" in client
    assert "tts/volcengine/v1/synthesize" in client
    assert "tts/volcengine/v1/synthesize" in main


def test_content_factory_prompt_routes_through_preflight():
    creator = read("src/pages/Creator.tsx")

    assert "marketing_draft_content_preflight" in creator
    assert "独立高阶视频预演 Agent" in creator
    assert "总预演不能替代镜头、节奏、美术和连续性判断" in creator
    assert "不要把工具名、数据库字段、预演流水账或完整证据列表原样贴给用户" in creator
    assert "思考/执行过程" in creator


def test_agent_panel_collapses_execution_noise_into_thinking_area():
    source = read("src/components/AgentPanel.tsx")

    assert "agent-thinking" in source
    assert "思考与执行" in source
    assert "执行计划" not in source
    assert "任务进度" not in source


def test_index_tts2_runtime_is_external_and_ignored():
    gitignore = read(".gitignore")
    script = read("scripts/bootstrap-index-tts2.sh")

    assert "runtime/index-tts/" in gitignore
    assert "github.com/index-tts/index-tts" in script
    assert "modelscope download --model IndexTeam/IndexTTS-2" in script


def test_account_sync_renderer_only_supplies_account_id():
    preload = read("electron/preload.js")
    accounts = read("src/pages/Accounts.tsx")

    assert "syncAccountMetrics: (accountId)" in preload
    assert "ipcRenderer.invoke('account:sync'" in preload
    assert "syncAccountSession" not in preload
    assert "syncAccountSession" not in accounts
    assert "mOS.syncAccountMetrics(account.id)" in accounts


def test_account_management_hides_weibo_from_product_targets():
    accounts = read("src/pages/Accounts.tsx")
    client = read("src/api/client.ts")

    domestic_block = ts_array_block(accounts, "DOMESTIC_PLATFORMS")
    global_block = ts_array_block(accounts, "GLOBAL_PLATFORMS")

    assert "weibo" not in domestic_block
    assert "weibo" not in global_block
    assert "weibo" not in client.split("export const PLATFORM_NAMES", 1)[1].split("}", 1)[0]
    assert "'zhihu'" in domestic_block
    assert "'wechat_official'" in domestic_block
    assert "wechat_official: '公众号'" in client
    assert "zhihu: '知乎'" in client


def test_account_login_entry_uses_unified_electron_browser():
    accounts = read("src/pages/Accounts.tsx")
    start_login = accounts.split("const startLogin", 1)[1].split("const cancelLogin", 1)[0]

    assert "mcpLoginStart" not in start_login
    assert "mcpLoginStatus" not in accounts
    assert "openLoginBrowser(platform, accountId)" in start_login
    assert "platform === 'douyin'" not in start_login


def test_wechat_channels_icon_keeps_orange_butterfly_on_white_tile():
    css = read("src/index.css")

    assert ".platform-mark-wechat_channels { --platform-bg: #ffffff; color: #f5a13a;" in css
    assert ".platform-mark-wechat_channels svg [stroke] { stroke: #f5a13a; }" in css
    assert ".app-shell.light .platform-mark-wechat_channels" in css
    assert ".app-shell.light .platform-mark-wechat_channels svg [stroke]" in css


def test_mobile_assistant_qr_dependencies_are_bootstrapped_and_tolerant():
    bootstrap = read("scripts/bootstrap-hermes-runtime.sh")
    bridge = read("electron/channel_bridge.py")
    accounts = read("src/pages/Accounts.tsx")
    main = read("electron/main.js")
    preload = read("electron/preload.js")
    globals_ts = read("src/global.d.ts")

    assert 'HERMES_SOURCE[mcp,feishu]' in bootstrap
    assert 'aiohttp==3.13.4' in bootstrap
    assert 'except Exception:\n        return ""' in bridge
    assert "event.qr_image || event.qr_url" in accounts
    assert "channel-link-button" in accounts
    assert "timeoutMs: platform === 'weixin' ? 45000 : 60000" in main
    assert "channels:cancel" in main
    assert "cancelChannel: (platform)" in preload
    assert "cancelChannel: (platform: MessagingPlatform)" in globals_ts
    assert "onCancel={cancel}" in accounts
    assert "busy ? '取消' : '扫码连接'" in accounts


def test_mobile_channels_use_single_native_hermes_agent_runtime():
    gateway_run = read("runtime/hermes-agent/gateway/run.py")
    messaging = read("runtime/hermes-agent/marketing_os/messaging.py")
    main = read("electron/main.js")
    channel_helper = read("electron/channel_bridge.py")

    assert not (ROOT / "runtime/hermes-agent/gateway/marketing_os_bridge.py").exists()
    assert "from marketing_os.messaging import prepare_inbound_message" in gateway_run
    assert "MARKETING_OS_MOBILE_BRIDGE_ENABLED" not in main
    assert "MARKETING_OS_MOBILE_BRIDGE_ENABLED" not in channel_helper
    assert 'desired = {"MARKETING_OS_CONFIG_DIR": target}' in channel_helper
    assert "/agent/sessions" not in messaging
    assert "/agent/messages" not in messaging
    assert "urllib" not in messaging


def test_content_production_is_owned_by_native_hermes_runtime():
    native_tools = read("runtime/hermes-agent/tools/marketing_os_tools.py")
    native_planner = read("runtime/hermes-agent/marketing_os/domains/content_production.py")
    native_assets = read("runtime/hermes-agent/marketing_os/domains/content_assets.py")
    legacy_planner = read("engine/agent_core/content_production.py")

    assert "marketing_plan_content_production" in native_tools
    assert "marketing_read_content_assets" in native_tools
    assert "marketing_draft_content_create" in native_tools
    assert "require_bound=True" in native_tools
    assert "content_production_plans" in native_assets
    assert "production plan not found in account scope" in native_assets
    assert "hermes-native-shared-capability-pool" in native_planner
    assert "engine.agent_core" not in native_tools
    assert "server_action" not in native_tools
    assert "Legacy compatibility planner" in legacy_planner


def test_workspace_filters_legacy_weibo_cache_without_showing_as_target():
    overview = read("src/pages/Overview.tsx")
    trending = read("src/pages/Trending.tsx")
    accounts = read("src/pages/Accounts.tsx")

    for source in (overview, trending, accounts):
        assert "HIDDEN_PLATFORMS" in source
        assert "'weibo'" in source


def test_video_project_remains_contract_skeleton_not_desktop_runtime_dependency():
    desktop_sources = [
        read("src/App.tsx"),
        read("src/api/client.ts"),
        read("electron/main.js"),
        read("engine/marketing-os/server.py"),
    ]
    for source in desktop_sources:
        assert "engine.video_core" not in source
        assert "engine.video_agents" not in source
