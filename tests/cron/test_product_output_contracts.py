from unittest.mock import MagicMock, patch

from cron.scheduler import run_job


def _job():
    return {
        "id": "daily-topic-job",
        "name": "daily topics",
        "prompt": "preflight daily topics",
        "model": "test-model",
        "enabled_toolsets": ["marketing", "web"],
        "product_contract": "marketing.daily_topic_recommendations.v1",
        "marketing_account_id": "acct-main",
    }


def _runtime():
    return {
        "api_key": "test-key",
        "base_url": "https://example.invalid/v1",
        "provider": "openrouter",
        "api_mode": "chat_completions",
    }


def test_scheduler_binds_marketing_scope_and_validates_before_success(tmp_path):
    fake_db = MagicMock()
    fake_db.update_session_marketing_scope.return_value = True
    agent = MagicMock()
    agent.run_conversation.return_value = {
        "final_response": "canonical preflight output",
        "completed": True,
    }

    with (
        patch("cron.scheduler._hermes_home", tmp_path),
        patch("cron.scheduler._resolve_origin", return_value=None),
        patch("dotenv.load_dotenv"),
        patch("hermes_state.SessionDB", return_value=fake_db),
        patch(
            "hermes_cli.runtime_provider.resolve_runtime_provider",
            return_value=_runtime(),
        ),
        patch("run_agent.AIAgent", return_value=agent),
        patch(
            "agent.marketing.session_scope.resolve_account_scope",
            return_value={
                "user_id": "default",
                "entity_id": "entity-main",
                "account_id": "acct-main",
                "platform": "douyin",
                "connected": True,
            },
        ),
        patch("cron.product_output_contracts.validate_product_cron_output") as validate,
    ):
        success, _output, final, error = run_job(_job())

    assert success is True
    assert final == "canonical preflight output"
    assert error is None
    agent._ensure_db_session.assert_called_once_with()
    fake_db.update_session_marketing_scope.assert_called_once()
    bound = fake_db.update_session_marketing_scope.call_args
    assert bound.kwargs["marketing_entity_id"] == "entity-main"
    validate.assert_called_once()
    assert validate.call_args.kwargs["content"] == "canonical preflight output"


def test_scheduler_fails_closed_when_model_rewrites_canonical_output(tmp_path):
    fake_db = MagicMock()
    fake_db.update_session_marketing_scope.return_value = True
    agent = MagicMock()
    agent.run_conversation.return_value = {
        "final_response": "rewritten model prose",
        "completed": True,
    }

    with (
        patch("cron.scheduler._hermes_home", tmp_path),
        patch("cron.scheduler._resolve_origin", return_value=None),
        patch("dotenv.load_dotenv"),
        patch("hermes_state.SessionDB", return_value=fake_db),
        patch(
            "hermes_cli.runtime_provider.resolve_runtime_provider",
            return_value=_runtime(),
        ),
        patch("run_agent.AIAgent", return_value=agent),
        patch(
            "agent.marketing.session_scope.resolve_account_scope",
            return_value={
                "user_id": "default",
                "entity_id": "entity-main",
                "account_id": "acct-main",
                "platform": "douyin",
                "connected": True,
            },
        ),
        patch(
            "cron.product_output_contracts.validate_product_cron_output",
            side_effect=ValueError("output differs from approved delivery"),
        ),
    ):
        success, _output, final, error = run_job(_job())

    assert success is False
    assert final == ""
    assert "differs from approved delivery" in error
