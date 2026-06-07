from __future__ import annotations

import asyncio

from app.workers.workflow_runner import run_pending_workflow_jobs, workflow_job_id


def test_workflow_job_id_accepts_job_id_id_and_run_id():
    assert workflow_job_id({"job_id": "job_1"}) == "job_1"
    assert workflow_job_id({"id": "job_2"}) == "job_2"
    assert workflow_job_id({"run_id": "job_3"}) == "job_3"
    assert workflow_job_id({}) == ""


def test_run_pending_workflow_jobs_counts_completed_skipped_and_failed():
    calls: list[str] = []

    def list_runs(**kwargs):
        assert kwargs["workflow"] == "test_workflow"
        assert kwargs["statuses"] == ["queued"]
        assert kwargs["limit"] == 4
        return [
            {"job_id": "done"},
            {"id": "skip"},
            {"run_id": "fail"},
            {"job_id": ""},
        ]

    async def run_one(job_id: str):
        calls.append(job_id)
        if job_id == "skip":
            return {"ok": False, "skipped": True, "reason": "claimed"}
        if job_id == "fail":
            return {"ok": False, "reason": "bad"}
        return {"ok": True}

    result = asyncio.run(
        run_pending_workflow_jobs(
            organization_id=None,
            workflow="test_workflow",
            list_runs=list_runs,
            run_one=run_one,
            limit=4,
            max_limit=10,
        )
    )

    assert calls == ["done", "skip", "fail"]
    assert result == {
        "ok": False,
        "picked": 3,
        "completed": 1,
        "skipped": 1,
        "failed": 1,
        "errors": [{"job_id": "fail", "error": "bad"}],
    }
