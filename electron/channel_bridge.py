"""Small JSON-lines bridge between Electron and Hermes messaging gateways."""

from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json
import os
import subprocess
import sys
from pathlib import Path


HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
HERMES_ROOT = Path(os.environ.get("HERMES_AGENT_ROOT", HERMES_HOME / "hermes-agent"))
if str(HERMES_ROOT) not in sys.path:
    sys.path.insert(0, str(HERMES_ROOT))


def emit(event: str, **payload) -> None:
    sys.stdout.write(json.dumps({"event": event, **payload}, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def qr_data_uri(value: str) -> str:
    try:
        import qrcode
    except Exception:
        return ""

    try:
        stream = io.BytesIO()
        qrcode.make(value).save(stream, format="PNG")
        return "data:image/png;base64," + base64.b64encode(stream.getvalue()).decode("ascii")
    except Exception:
        return ""


def env_values() -> dict[str, str]:
    from dotenv import dotenv_values

    return {key: str(value or "") for key, value in dotenv_values(HERMES_HOME / ".env").items()}


def save_values(values: dict[str, str]) -> None:
    from hermes_cli.config import save_env_value

    for key, value in values.items():
        save_env_value(key, value)


def hermes_executable() -> str:
    candidates = [
        HERMES_ROOT / ".venv" / "bin" / "hermes",
        Path.home() / ".local" / "bin" / "hermes",
        HERMES_ROOT / "venv" / "bin" / "hermes",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return "hermes"


def restart_gateway() -> None:
    executable = hermes_executable()
    subprocess.run(
        [executable, "gateway", "stop"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    result = subprocess.run(
        [executable, "gateway", "start"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "Hermes gateway start failed").strip())


def status() -> None:
    values = env_values()
    weixin_id = values.get("WEIXIN_ACCOUNT_ID", "")
    weixin_account = HERMES_HOME / "weixin" / "accounts" / f"{weixin_id}.json"
    payload = {
        "weixin": {
            "connected": bool(weixin_id and weixin_account.exists()),
            "ready_to_push": bool(values.get("WEIXIN_HOME_CHANNEL")),
            "identity": weixin_id[:12],
        },
        "feishu": {
            "connected": bool(values.get("FEISHU_APP_ID") and values.get("FEISHU_APP_SECRET")),
            "ready_to_push": bool(values.get("FEISHU_HOME_CHANNEL")),
            "identity": values.get("FEISHU_BOT_NAME", ""),
        },
    }
    emit("status", channels=payload)


def configure() -> None:
    """Point the native Hermes runtime at the product's canonical data directory."""
    target = str(os.environ.get("MARKETING_OS_CONFIG_DIR", "")).strip()
    if not target:
        raise RuntimeError("缺少桌面数据目录")
    values = env_values()
    desired = {"MARKETING_OS_CONFIG_DIR": target}
    changed = any(values.get(key, "") != value for key, value in desired.items())
    if changed:
        save_values(desired)
        configured = bool(
            values.get("WEIXIN_ACCOUNT_ID")
            or (values.get("FEISHU_APP_ID") and values.get("FEISHU_APP_SECRET"))
        )
        if configured:
            restart_gateway()
    emit("configured", config_dir=target, changed=changed)


async def connect_weixin() -> None:
    import builtins
    from gateway.platforms.weixin import qr_login

    try:
        import qrcode
    except Exception:
        qrcode = None  # type: ignore[assignment]

    original_print = builtins.print
    original_ascii = qrcode.QRCode.print_ascii if qrcode is not None else None
    qr_sent = False

    def intercepted_print(*args, **kwargs):
        nonlocal qr_sent
        line = " ".join(str(arg) for arg in args).strip()
        if not qr_sent and line.startswith(("https://", "http://")):
            qr_sent = True
            emit("qr", platform="weixin", qr_url=line, qr_image=qr_data_uri(line))

    builtins.print = intercepted_print
    if qrcode is not None:
        qrcode.QRCode.print_ascii = lambda *_args, **_kwargs: None
    try:
        credentials = await qr_login(str(HERMES_HOME), timeout_seconds=480)
    finally:
        builtins.print = original_print
        if qrcode is not None and original_ascii is not None:
            qrcode.QRCode.print_ascii = original_ascii

    if not credentials:
        raise RuntimeError("微信扫码未完成或二维码已失效")
    values = {
        "WEIXIN_ACCOUNT_ID": credentials["account_id"],
        "WEIXIN_DM_POLICY": "pairing",
        "WEIXIN_GROUP_POLICY": "disabled",
    }
    # The QR owner is the safest default recipient and can chat immediately.
    if credentials.get("user_id"):
        values["WEIXIN_ALLOWED_USERS"] = credentials["user_id"]
        values["WEIXIN_HOME_CHANNEL"] = credentials["user_id"]
    save_values(values)
    restart_gateway()
    emit("connected", platform="weixin", ready_to_push=bool(credentials.get("user_id")))


def connect_feishu() -> None:
    from plugins.platforms.feishu.adapter import (
        _begin_registration,
        _init_registration,
        _poll_registration,
        probe_bot,
    )

    _init_registration("feishu")
    begin = _begin_registration("feishu")
    emit("qr", platform="feishu", qr_url=begin["qr_url"], qr_image=qr_data_uri(begin["qr_url"]))
    credentials = _poll_registration(
        device_code=begin["device_code"],
        interval=begin["interval"],
        expire_in=min(begin["expire_in"], 600),
        domain="feishu",
    )
    if not credentials:
        raise RuntimeError("飞书扫码未完成或授权已取消")
    bot = probe_bot(credentials["app_id"], credentials["app_secret"], credentials["domain"]) or {}
    values = {
        "FEISHU_APP_ID": credentials["app_id"],
        "FEISHU_APP_SECRET": credentials["app_secret"],
        "FEISHU_DOMAIN": credentials.get("domain", "feishu"),
        "FEISHU_CONNECTION_MODE": "websocket",
        "FEISHU_ALLOW_ALL_USERS": "false",
        "FEISHU_GROUP_POLICY": "open",
    }
    if credentials.get("open_id"):
        values["FEISHU_ALLOWED_USERS"] = credentials["open_id"]
    if bot.get("bot_name"):
        values["FEISHU_BOT_NAME"] = bot["bot_name"]
    save_values(values)
    restart_gateway()
    emit("connected", platform="feishu", ready_to_push=False, bot_name=bot.get("bot_name"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["status", "connect", "configure"])
    parser.add_argument("--platform", choices=["weixin", "feishu"])
    args = parser.parse_args()
    try:
        if args.command == "status":
            status()
        elif args.command == "configure":
            configure()
        elif args.platform == "weixin":
            asyncio.run(connect_weixin())
        elif args.platform == "feishu":
            connect_feishu()
        else:
            raise RuntimeError("缺少消息平台")
    except Exception as exc:
        emit("error", platform=args.platform, message=str(exc))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
