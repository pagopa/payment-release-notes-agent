"""Per-job correlation id, so every log line of a job can be found in Log Analytics.

The worker sets it at the start of its thread; code deeper in the stack (LLM
calls, JSON parsing) reads it to prefix its log lines without having the job
id passed through every signature. Each worker runs in its own thread, so a
ContextVar keeps concurrent jobs separated.
"""

from contextvars import ContextVar

_job_id: ContextVar[str] = ContextVar("job_id", default="")


def set_job_id(job_id: str) -> None:
    _job_id.set(job_id or "")


def get_job_id() -> str:
    return _job_id.get()


def job_tag() -> str:
    """Log prefix like "[job:<uuid>] ", or "" outside a job."""
    job_id = _job_id.get()
    return f"[job:{job_id}] " if job_id else ""
