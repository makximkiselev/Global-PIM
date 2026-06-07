from __future__ import annotations

from copy import deepcopy

from app.core import workflow_jobs


def test_start_worker_process_builds_detached_python_module_command(monkeypatch):
    calls: list[dict] = []

    def fake_popen(command, **kwargs):
        calls.append({"command": command, **kwargs})
        return object()

    monkeypatch.setattr(workflow_jobs.subprocess, "Popen", fake_popen)
    monkeypatch.setenv("PYTHONPATH", "/existing/path")

    workflow_jobs.start_worker_process("app.workers.example", "job_1", "org_1")

    assert len(calls) == 1
    call = calls[0]
    assert call["command"] == [
        workflow_jobs.sys.executable,
        "-m",
        "app.workers.example",
        "--job-id",
        "job_1",
        "--organization-id",
        "org_1",
    ]
    assert str(workflow_jobs.backend_root()) in call["env"]["PYTHONPATH"]
    assert "/existing/path" in call["env"]["PYTHONPATH"]
    assert call["cwd"] == str(workflow_jobs.repo_root())
    assert call["start_new_session"] is True


def test_prune_stale_workflow_jobs_marks_only_expired_jobs(monkeypatch):
    saved: list[dict] = []
    jobs = [
        {"id": "stale", "status": "running", "updated_ts": 100.0},
        {"id": "fresh", "status": "queued", "updated_ts": 190.0},
        {"id": "missing_ts", "status": "running"},
    ]

    def list_jobs(**kwargs):
        assert kwargs["workflow"] == "test_workflow"
        assert kwargs["statuses"] == ["queued", "running"]
        return deepcopy(jobs)

    def save_job(job, *, workflow):
        assert workflow == "test_workflow"
        saved.append(deepcopy(job))
        return job

    monkeypatch.setattr(workflow_jobs, "list_workflow_jobs", list_jobs)
    monkeypatch.setattr(workflow_jobs, "save_workflow_job", save_job)
    monkeypatch.setattr(workflow_jobs, "now_iso", lambda: "2026-06-07T10:00:00+00:00")

    count = workflow_jobs.prune_stale_workflow_jobs(
        workflow="test_workflow",
        ttl_seconds=50.0,
        message="stale message",
        error="STALE_TEST_JOB",
        now_ts=200.0,
    )

    assert count == 1
    assert saved == [
        {
            "id": "stale",
            "status": "failed",
            "phase": "stale",
            "message": "stale message",
            "finished_at": "2026-06-07T10:00:00+00:00",
            "updated_ts": 200.0,
            "error": "STALE_TEST_JOB",
        }
    ]


def test_run_persisted_workflow_job_marks_completed(monkeypatch):
    saved: list[dict] = []
    job = {"id": "job_1", "job_id": "job_1", "status": "queued", "request": {"limit": 1}}

    monkeypatch.setattr(workflow_jobs, "get_workflow_job", lambda job_id, *, workflow: dict(job))
    monkeypatch.setattr(workflow_jobs, "now_iso", lambda: "2026-06-07T10:00:00+00:00")

    def save_job(payload, *, workflow):
        saved.append(dict(payload))
        return payload

    monkeypatch.setattr(workflow_jobs, "save_workflow_job", save_job)

    workflow_jobs.run_persisted_workflow_job(
        "job_1",
        workflow="test_workflow",
        parse_request=lambda payload: payload,
        execute=lambda request: {"run_id": "run_1", "summary": {"limit": request["limit"]}},
        running_phase="preparing",
        running_message="running",
        completed_message="done",
        invalid_request_message="bad request",
        failed_message="failed",
    )

    assert [item["status"] for item in saved] == ["running", "completed"]
    assert saved[-1]["run_id"] == "run_1"
    assert saved[-1]["summary"] == {"limit": 1}


def test_run_persisted_workflow_job_marks_invalid_request_failed(monkeypatch):
    saved: list[dict] = []
    job = {"id": "job_1", "job_id": "job_1", "status": "queued", "request": {"bad": True}}

    monkeypatch.setattr(workflow_jobs, "get_workflow_job", lambda job_id, *, workflow: dict(job))
    monkeypatch.setattr(workflow_jobs, "now_iso", lambda: "2026-06-07T10:00:00+00:00")
    monkeypatch.setattr(workflow_jobs, "save_workflow_job", lambda payload, *, workflow: saved.append(dict(payload)) or payload)

    def parse_request(payload):
        raise ValueError("invalid")

    workflow_jobs.run_persisted_workflow_job(
        "job_1",
        workflow="test_workflow",
        parse_request=parse_request,
        execute=lambda request: {"run_id": "run_1"},
        running_phase="preparing",
        running_message="running",
        completed_message="done",
        invalid_request_message="bad request",
        failed_message="failed",
    )

    assert len(saved) == 1
    assert saved[0]["status"] == "failed"
    assert saved[0]["message"] == "bad request"
    assert saved[0]["error"].startswith("ValueError:")
