from __future__ import annotations

from copy import deepcopy

from app.core import workflow_jobs


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
