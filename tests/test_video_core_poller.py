"""TaskPoller 单元测试（VIDEO-04）：全部走离线 harness，无网络无 sleep。"""

import asyncio

from engine.video_core.poller import PollJob, TaskPoller
from engine.video_core.adapter import TaskFailedError, VideoTaskStatus
from engine.video_core.project_store import ProjectStore
from engine.video_core.schema import ShotStatus
from engine.video_core.testing import MockAdapter, make_demo_project


async def _fake_download(url: str, dest) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"fake-video-bytes")


def _make_poller(tmp_path, adapter, **kwargs):
    store = ProjectStore(tmp_path)
    store.create(make_demo_project("proj"))
    poller = TaskPoller(
        adapter, store, download=_fake_download, base_interval_sec=0.0, **kwargs
    )
    return store, poller


def test_success_lifecycle_updates_shot_and_downloads(tmp_path):
    async def run():
        adapter = MockAdapter(polls_until_done=2)
        store, poller = _make_poller(tmp_path, adapter)
        poller.add(PollJob(project_id="proj", shot_id="shot-2", task_id="mock-task-99"))

        first = await poller.poll_once()   # RUNNING → 退避保留
        second = await poller.poll_once()  # SUCCEEDED → 终态
        return store, poller, first, second

    store, poller, first, second = asyncio.run(run())
    assert (first, second) == (0, 1)
    assert poller.pending_count == 0
    shot = store.load("proj").get_shot("shot-2")
    assert shot.status == ShotStatus.GENERATED
    assert shot.version == 1
    assert shot.task_id == ""
    assert shot.duration_sec == 5.0
    video = store.project_dir("proj") / shot.file_path
    assert video.read_bytes() == b"fake-video-bytes"


def test_failure_marks_qc_failed_and_increments_retry(tmp_path):
    async def run():
        adapter = MockAdapter(fail_task_ids={"mock-task-99"})
        store, poller = _make_poller(tmp_path, adapter)
        poller.add(PollJob(project_id="proj", shot_id="shot-2", task_id="mock-task-99"))
        await poller.poll_once()
        return store

    store = asyncio.run(run())
    shot = store.load("proj").get_shot("shot-2")
    assert shot.status == ShotStatus.QC_FAILED
    assert shot.retry_count == 1
    assert any("mock failure" in n for n in shot.continuity_notes)


def test_download_failure_is_retryable_qc_failed(tmp_path):
    seen = []

    async def failing_download(url, dest):
        raise OSError("disk full")

    async def on_done(job, result):
        seen.append(result)

    async def run():
        adapter = MockAdapter(polls_until_done=1)
        store = ProjectStore(tmp_path)
        store.create(make_demo_project("proj"))
        poller = TaskPoller(
            adapter, store, download=failing_download, on_done=on_done,
            base_interval_sec=0.0,
        )
        poller.add(PollJob(project_id="proj", shot_id="shot-2", task_id="mock-task-99"))
        await poller.poll_once()
        return store

    store = asyncio.run(run())
    shot = store.load("proj").get_shot("shot-2")
    assert shot.status == ShotStatus.QC_FAILED
    assert shot.task_id == ""
    assert any("download failed" in n for n in shot.continuity_notes)
    assert seen[0].status == VideoTaskStatus.FAILED
    assert "disk full" in seen[0].error_message


def test_terminal_adapter_exception_does_not_backoff_forever(tmp_path):
    class TerminalFailureAdapter(MockAdapter):
        async def query_video_task(self, task_id):
            raise TaskFailedError("provider rejected task")

    async def run():
        store, poller = _make_poller(tmp_path, TerminalFailureAdapter())
        poller.add(PollJob(project_id="proj", shot_id="shot-2", task_id="rejected-task"))
        terminal = await poller.poll_once()
        return store, poller, terminal

    store, poller, terminal = asyncio.run(run())
    assert terminal == 1
    assert poller.pending_count == 0
    shot = store.load("proj").get_shot("shot-2")
    assert shot.status == ShotStatus.QC_FAILED
    assert "provider rejected task" in shot.continuity_notes[-1]


def test_add_dedupes_same_task_id(tmp_path):
    async def run():
        adapter = MockAdapter()
        _, poller = _make_poller(tmp_path, adapter)
        poller.add(PollJob(project_id="proj", shot_id="shot-2", task_id="t-1"))
        poller.add(PollJob(project_id="proj", shot_id="shot-2", task_id="t-1"))
        return poller

    poller = asyncio.run(run())
    assert poller.pending_count == 1


def test_recover_picks_up_pending_shots(tmp_path):
    async def run():
        adapter = MockAdapter()
        store, poller = _make_poller(tmp_path, adapter)
        count = await poller.recover()
        return count, poller

    count, poller = asyncio.run(run())
    # demo 画布里 shot-2 处于 submitted + task_id
    assert count == 1
    assert poller.pending_count == 1


def test_backoff_interval_grows_and_caps(tmp_path):
    async def run():
        adapter = MockAdapter(polls_until_done=100)  # 一直 RUNNING
        store = ProjectStore(tmp_path)
        store.create(make_demo_project("proj"))
        poller = TaskPoller(
            adapter, store, download=_fake_download,
            base_interval_sec=10.0, backoff_factor=1.5, max_interval_sec=20.0,
        )
        job = PollJob(project_id="proj", shot_id="shot-2", task_id="mock-task-99")
        poller.add(job)
        job.next_poll_at = 0  # 强制到期
        await poller.poll_once()
        first_interval = job.interval_sec
        job.next_poll_at = 0
        await poller.poll_once()
        return first_interval, job.interval_sec

    first, second = asyncio.run(run())
    assert first == 15.0            # 10 × 1.5
    assert second == 20.0           # 封顶


def test_on_done_callback_fires(tmp_path):
    seen = []

    async def on_done(job, result):
        seen.append((job.shot_id, result.status.value))

    async def run():
        adapter = MockAdapter(polls_until_done=1)
        store = ProjectStore(tmp_path)
        store.create(make_demo_project("proj"))
        poller = TaskPoller(
            adapter, store, download=_fake_download,
            on_done=on_done, base_interval_sec=0.0,
        )
        poller.add(PollJob(project_id="proj", shot_id="shot-2", task_id="mock-task-99"))
        await poller.poll_once()

    asyncio.run(run())
    assert seen == [("shot-2", "succeeded")]


def test_start_stop_loop_reaches_terminal_state(tmp_path):
    async def run():
        adapter = MockAdapter(polls_until_done=2)
        store = ProjectStore(tmp_path)
        store.create(make_demo_project("proj"))
        poller = TaskPoller(
            adapter, store, download=_fake_download,
            base_interval_sec=0.0, tick_sec=0.01,
        )
        poller.add(PollJob(project_id="proj", shot_id="shot-2", task_id="mock-task-99"))
        await poller.start()
        for _ in range(200):
            if poller.pending_count == 0:
                break
            await asyncio.sleep(0.01)
        await poller.stop()
        return store, poller

    store, poller = asyncio.run(run())
    assert poller.pending_count == 0
    assert store.load("proj").get_shot("shot-2").status == ShotStatus.GENERATED
