import json
from pathlib import Path

import pytest

from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains import MediaAssetRepository, ProductionAudioRepository
from hermes_state import SessionDB


def _paths(tmp_path):
    state_path = tmp_path / "state.db"
    SessionDB(db_path=state_path).close()
    return MarketingDataPaths(tmp_path, tmp_path / "config", state_path)


class FakeTTS:
    def __init__(self, *, fail=False):
        self.calls = 0
        self.fail = fail

    def __call__(self, text, output_path):
        self.calls += 1
        if self.fail:
            return json.dumps({"success": False, "error": "provider unavailable"})
        target = Path(output_path)
        target.write_bytes(b"real-audio")
        return json.dumps({
            "success": True,
            "file_path": str(target),
            "provider": "test_tts",
        })


def test_voice_job_requires_approval_and_imports_real_output(tmp_path):
    paths = _paths(tmp_path)
    runner = FakeTTS()
    repo = ProductionAudioRepository(paths, tts_runner=runner)
    prepared = repo.prepare_voice(
        user_id="u1", account_id="acct-1", name="第一版旁白",
        script_text="这是经过确认的旁白。",
    )
    repeated = repo.prepare_voice(
        user_id="u1", account_id="acct-1", name="第一版旁白",
        script_text="这是经过确认的旁白。",
    )
    assert repeated["id"] == prepared["id"]
    with pytest.raises(ValueError, match="approved"):
        repo.execute(job_id=prepared["id"], user_id="u1", account_id="acct-1")
    with pytest.raises(ValueError, match="explicit human approval"):
        repo.approve(
            job_id=prepared["id"], user_id="u1", account_id="acct-1",
            approval_ref="review-1", confirmed_by_user=False,
        )

    repo.approve(
        job_id=prepared["id"], user_id="u1", account_id="acct-1",
        approval_ref="review-1", confirmed_by_user=True,
    )
    completed = repo.execute(
        job_id=prepared["id"], user_id="u1", account_id="acct-1"
    )

    assert completed["status"] == "completed"
    assert completed["provider"] == "test_tts"
    assert completed["receipt"]["script_sha256"] == prepared["script_sha256"]
    asset = MediaAssetRepository(paths).get(
        asset_id=completed["output_asset_id"], user_id="u1"
    )
    assert asset["role"] == "voice"
    assert asset["provider"] == "hermes_tts:test_tts"
    assert asset["receipt"]["approval_ref"] == "review-1"
    assert (MediaAssetRepository(paths).root / asset["local_path"]).read_bytes() == b"real-audio"
    assert runner.calls == 1


def test_failed_voice_job_can_be_reapproved_without_false_success(tmp_path):
    paths = _paths(tmp_path)
    runner = FakeTTS(fail=True)
    repo = ProductionAudioRepository(paths, tts_runner=runner)
    job = repo.prepare_voice(
        user_id="u1", account_id="acct-1", name="旁白", script_text="失败测试"
    )
    repo.approve(
        job_id=job["id"], user_id="u1", account_id="acct-1",
        approval_ref="review-1", confirmed_by_user=True,
    )
    with pytest.raises(RuntimeError, match="provider unavailable"):
        repo.execute(job_id=job["id"], user_id="u1", account_id="acct-1")
    failed = repo.get(job_id=job["id"], user_id="u1", account_id="acct-1")
    assert failed["status"] == "failed"
    assert failed["output_asset_id"] is None

    runner.fail = False
    repo.approve(
        job_id=job["id"], user_id="u1", account_id="acct-1",
        approval_ref="review-2", confirmed_by_user=True,
    )
    assert repo.execute(
        job_id=job["id"], user_id="u1", account_id="acct-1"
    )["status"] == "completed"


def test_voice_job_is_account_scoped(tmp_path):
    paths = _paths(tmp_path)
    repo = ProductionAudioRepository(paths, tts_runner=FakeTTS())
    job = repo.prepare_voice(
        user_id="u1", account_id="acct-1", name="旁白", script_text="账号隔离"
    )
    with pytest.raises(KeyError):
        repo.get(job_id=job["id"], user_id="u1", account_id="acct-2")
