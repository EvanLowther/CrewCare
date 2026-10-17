"""planit.worker.jobs with a fake database connection."""

from contextlib import contextmanager

from planit.worker import jobs


class FakeDB:
    """Hands out queued jobs from CLAIM_SQL and records FINISH_SQL updates."""

    def __init__(self, queued):
        self.queued, self.finished = list(queued), []

    def execute(self, sql, params=None):
        if sql == jobs.CLAIM_SQL:
            job = self.queued.pop(0) if self.queued else None
            return type("Cursor", (), {"fetchone": lambda _self: job})()
        self.finished.append(params)
        return None

    @contextmanager
    def connection(self):
        yield self


def test_poll_runs_each_job_and_records_failures(monkeypatch):
    db = FakeDB([{"id": 1, "kind": "ok", "params": {"x": 1}},
                 {"id": 2, "kind": "boom", "params": {}},
                 {"id": 3, "kind": "unknown", "params": {}}])
    seen = []

    def boom(params):
        raise ValueError("bad site")

    monkeypatch.setattr(jobs, "connection", db.connection)
    monkeypatch.setattr(jobs, "HANDLERS", {"ok": seen.append, "boom": boom})

    assert jobs.poll() == 3
    assert seen == [{"x": 1}]
    assert db.finished == [("done", None, 1), ("failed", "ValueError: bad site", 2),
                           ("failed", "NotImplementedError: no handler for job kind 'unknown'", 3)]


def test_poll_with_nothing_pending(monkeypatch):
    monkeypatch.setattr(jobs, "connection", FakeDB([]).connection)
    assert jobs.poll() == 0
