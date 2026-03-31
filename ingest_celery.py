"""
ingest_celery.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de celery/celery dans la KB Qdrant V6.

Focus : CORE patterns distributed task queue (task definition, retry logic,
canvas primitives, periodic scheduling, worker signals, result backends,
task routing, error handling, task state tracking).

Usage:
    .venv/bin/python3 ingest_celery.py
"""

from __future__ import annotations

import subprocess
import time
import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
)

from embedder import embed_documents_batch, embed_query
from kb_utils import build_payload, check_charte_violations, make_uuid, query_kb, audit_report

# ─── Constantes ──────────────────────────────────────────────────────────────
REPO_URL = "https://github.com/celery/celery.git"
REPO_NAME = "celery/celery"
REPO_LOCAL = "/tmp/celery"
LANGUAGE = "python"
FRAMEWORK = "generic"
STACK = "python+celery+redis+rabbitmq"
CHARTE_VERSION = "1.0"
TAG = "celery/celery"
SOURCE_REPO = "https://github.com/celery/celery"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Celery = distributed task queue with retry logic, canvas primitives, beat scheduling.
# Patterns CORE : app initialization, task definition, canvas (chain/group/chord),
# retry with backoff, periodic tasks, result backends, signals, task routing,
# worker configuration, error handling, rate limiting, state tracking.
# U-5 : task → job, user → xxx, message → payload, event → signal,
# order → sequence, item → element, post → entry, comment → annotation

PATTERNS: list[dict] = [
    # ── 1. App initialization with broker/backend config ─────────────────────
    {
        "normalized_code": """\
from celery import Celery

# Broker and result backend configuration
app = Celery(
    "xxx_service",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/1",
)

# Task configuration with retry defaults
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
)
""",
        "function": "app_initialization_broker_backend",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "celery_app.py",
    },
    # ── 2. Task decorator with retry backoff ──────────────────────────────────
    {
        "normalized_code": """\
from celery import shared_task
from celery.exceptions import MaxRetriesExceededError


@shared_task(
    bind=True,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3},
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def process_job(self, element_id: int) -> str:
    \"\"\"Process a single element with exponential backoff retry.\"\"\"
    try:
        # Simulate processing logic
        result = expensive_operation(element_id)
        return f"Processed element {element_id}: {result}"
    except Exception as exc:
        try:
            self.retry(exc=exc, countdown=2 ** self.request.retries)
        except MaxRetriesExceededError:
            return f"Failed to process element {element_id} after {self.max_retries} retries"
""",
        "function": "task_decorator_retry_backoff",
        "feature_type": "crud",
        "file_role": "route",
        "file_path": "celery_jobs.py",
    },
    # ── 3. Canvas primitives: chain, group, chord ────────────────────────────
    {
        "normalized_code": """\
from celery import group, chord, chain
from celery.canvas import Signature


# Chain: sequential task execution
workflow_chain = chain(
    fetch_data.s(element_id=123),
    transform_data.s(),
    save_to_backend.s(),
)

# Group: parallel task execution
parallel_workflow = group(
    analyze_batch.s(batch_idx=i, size=100)
    for i in range(10)
)

# Chord: parallel with callback
final_workflow = chord(
    [process_batch.s(i) for i in range(5)],
    aggregate_results.s(),
)

# Apply workflow asynchronously
result_chain = workflow_chain.apply_async()
result_group = parallel_workflow.apply_async()
result_chord = final_workflow.apply_async()

# Get aggregated results
final_value = result_chord.get()
""",
        "function": "canvas_chain_group_chord",
        "feature_type": "pipeline",
        "file_role": "route",
        "file_path": "celery_workflows.py",
    },
    # ── 4. Starmap: map-reduce with multiple arguments ──────────────────────
    {
        "normalized_code": """\
from celery import current_app


def process_elements(element_list: list[dict]) -> list:
    \"\"\"Apply job to multiple elements with different arguments.\"\"\"
    # Prepare argument pairs for starmap
    args_sequence = [
        (element["id"], element["name"], element.get("priority", 1))
        for element in element_list
    ]

    # Starmap applies job to each argument tuple in parallel
    signature = current_app.tasks["process_element"].starmap(args_sequence)
    result = signature.apply_async()

    # Collect all results
    processed = [r for r in result.get()]
    return processed


@current_app.task(bind=True)
def process_element(self, element_id: int, name: str, priority: int = 1) -> dict:
    \"\"\"Process single element with multiple parameters.\"\"\"
    return {
        "id": element_id,
        "name": name,
        "priority": priority,
        "processed_at": self.request.id,
    }
""",
        "function": "canvas_starmap_multiarg",
        "feature_type": "pipeline",
        "file_role": "utility",
        "file_path": "celery_workflows.py",
    },
    # ── 5. Periodic tasks with beat scheduler ────────────────────────────────
    {
        "normalized_code": """\
from celery import Celery
from celery.schedules import crontab

app = Celery("xxx_service")

# Beat schedule configuration
app.conf.beat_schedule = {
    "run-housekeeping-every-hour": {
        "task": "xxx_service.housekeeping_job",
        "schedule": crontab(minute=0),  # Every hour at :00
        "args": (),
        "kwargs": {"verbose": True},
    },
    "sync-data-every-5-minutes": {
        "task": "xxx_service.sync_remote_backend",
        "schedule": 300.0,  # Every 5 minutes
        "options": {"expires": 600},
    },
    "cleanup-expired-entries-daily": {
        "task": "xxx_service.cleanup_expired",
        "schedule": crontab(hour=2, minute=0),  # 2 AM UTC daily
        "args": ("expired",),
    },
}


@app.task
def housekeeping_job(verbose: bool = False) -> str:
    \"\"\"Periodic maintenance job executed by beat scheduler.\"\"\"
    if verbose:
        app.log.info("Starting housekeeping")
    cleanup_stale_locks()
    return "housekeeping_completed"
""",
        "function": "beat_periodic_tasks_crontab",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "celery_beat_schedule.py",
    },
    # ── 6. Result backend persistence and retrieval ──────────────────────────
    {
        "normalized_code": """\
from celery.result import AsyncResult


def fetch_job_result(job_id: str, timeout: int | None = None) -> dict:
    \"\"\"Retrieve result from backend with timeout.\"\"\"
    result = AsyncResult(job_id, app=app)

    if result.ready():
        try:
            value = result.get(timeout=timeout)
            return {
                "state": result.state,
                "result": value,
                "successful": result.successful(),
            }
        except Exception as exc:
            return {
                "state": result.state,
                "result": None,
                "error": str(exc),
                "successful": False,
            }
    else:
        return {
            "state": result.state,
            "result": None,
            "pending": True,
        }


def forget_job_result(job_id: str) -> None:
    \"\"\"Remove result from backend to free memory.\"\"\"
    result = AsyncResult(job_id, app=app)
    result.forget()
""",
        "function": "result_backend_get_forget",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "celery_results.py",
    },
    # ── 7. Task signals: before/after publish and success/failure ─────────────
    {
        "normalized_code": """\
from celery import signals
from celery.utils.log import get_task_logger


logger = get_task_logger(__name__)


@signals.before_task_publish.connect
def signal_before_publish(sender=None, body=None, **kwargs) -> None:
    \"\"\"Log or modify payload before execution is published to broker.\"\"\"
    logger.debug(f"Execution about to be sent: {sender}")


@signals.after_task_publish.connect
def signal_after_publish(sender=None, **kwargs) -> None:
    \"\"\"Trigger action after execution published successfully.\"\"\"
    logger.info(f"Execution published: {sender}")


@signals.task_success.connect
def signal_task_success(sender=None, result=None, **kwargs) -> None:
    \"\"\"Handler called when execution succeeds.\"\"\"
    logger.info(f"Execution {sender} succeeded with result: {result}")


@signals.task_failure.connect
def signal_task_failure(sender=None, task_id=None, exception=None, **kwargs) -> None:
    \"\"\"Handler called on execution failure.\"\"\"
    logger.error(f"Execution {sender} (id={task_id}) failed: {exception}")


@signals.task_retry.connect
def signal_task_retry(sender=None, reason=None, **kwargs) -> None:
    \"\"\"Handler called when retrying.\"\"\"
    logger.warning(f"Execution {sender} retrying: {reason}")
""",
        "function": "task_signals_publish_success_failure",
        "feature_type": "route",
        "file_role": "utility",
        "file_path": "celery_signal_handlers.py",
    },
    # ── 8. Task routing with exchanges and queues ────────────────────────────
    {
        "normalized_code": """\
from kombu import Exchange, Queue

app.conf.task_queues = (
    Queue(
        "default",
        Exchange("default", type="direct"),
        routing_key="default",
    ),
    Queue(
        "priority_jobs",
        Exchange("priority", type="direct"),
        routing_key="priority",
    ),
    Queue(
        "long_running",
        Exchange("long_running", type="direct"),
        routing_key="long_running",
        queue_arguments={"x-max-priority": 10},
    ),
)

app.conf.task_routes = {
    "xxx_service.critical_job": {"queue": "priority_jobs", "priority": 9},
    "xxx_service.process_element": {"queue": "default", "priority": 5},
    "xxx_service.heavy_computation": {
        "queue": "long_running",
        "time_limit": 3600,
    },
}

app.conf.task_default_priority = 5


@app.task(queue="priority_jobs", priority=9)
def critical_job(data: dict) -> dict:
    \"\"\"Routed to high-priority queue.\"\"\"
    return {"processed": data, "priority": "high"}
""",
        "function": "task_routing_queues_exchanges",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "celery_routing.py",
    },
    # ── 9. Rate limiting and throttling per task ──────────────────────────────
    {
        "normalized_code": """\
from celery import Task


@app.task(rate_limit="10/m")  # 10 per minute
def rate_limited_job(element_id: int) -> str:
    \"\"\"Execution is throttled to max 10 per minute.\"\"\"
    return f"Processed element {element_id}"


@app.task(rate_limit="100/h")  # 100 per hour
def bulk_process_job(batch: list[int]) -> list:
    \"\"\"Bulk operation with hourly rate limit.\"\"\"
    return [process_single(element) for element in batch]


class ThrottledExecution(Task):
    \"\"\"Custom execution class with rate limiting.\"\"\"
    rate_limit = "50/m"  # Default 50 per minute


@app.task(base=ThrottledExecution)
def custom_throttled_job(element_id: int) -> str:
    \"\"\"Using custom throttled execution class.\"\"\"
    return f"Custom throttled: {element_id}"
""",
        "function": "rate_limiting_throttling_tasks",
        "feature_type": "config",
        "file_role": "route",
        "file_path": "celery_jobs.py",
    },
    # ── 10. Worker configuration and execution options ──────────────────────
    {
        "normalized_code": """\
from celery import Celery

app = Celery("xxx_service")

# Worker pool and concurrency configuration
app.conf.update(
    worker_prefetch_multiplier=4,
    worker_max_tasks_per_child=1000,
    worker_disable_rate_limits=False,
    worker_log_color=True,
    worker_log_format="[%(asctime)s: %(levelname)s/%(processName)s] %(message)s",
    worker_task_log_format="[%(asctime)s: %(levelname)s/%(processName)s] %(message)s",
)

# Concurrency and pool settings
app.conf.worker_pool = "solo"  # Or: "prefork", "threads", "eventlet"
app.conf.worker_concurrency = 4  # Number of worker processes

# Autoscaling
app.conf.worker_autoscaler = "celery.worker.autoscale:Autoscaler"
app.conf.autoscale_max = 10  # Max pool size
app.conf.autoscale_min = 2   # Min pool size

# Execution timeout
app.conf.task_time_limit = 30 * 60  # Hard limit: 30 minutes
app.conf.task_soft_time_limit = 25 * 60  # Soft limit: 25 minutes


@app.on_after_configure.connect
def setup_on_startup(sender=None, **kwargs) -> None:
    \"\"\"Initialize worker state on startup.\"\"\"
    app.log.info("Celery worker starting")


@app.on_before_task_publish.connect
def task_before_publish(sender=None, **kwargs) -> None:
    \"\"\"Hook before any execution is sent to broker.\"\"\"
    app.log.debug("Execution being dispatched")
""",
        "function": "worker_configuration_pool_concurrency",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "celery_worker_config.py",
    },
    # ── 11. Acks_late with error handling (manual acknowledgment) ───────────
    {
        "normalized_code": """\
from celery import Task
from celery.exceptions import Reject, SoftTimeLimitExceeded


class SafeExecution(Task):
    \"\"\"Execution with manual ack (late acks).\"\"\"
    autoretry_for = (Exception,)
    retry_kwargs = {"max_retries": 3}
    retry_backoff = True
    acks_late = True  # Acknowledge after execution


@app.task(base=SafeExecution, bind=True)
def safe_operation(self, payload: dict) -> dict:
    \"\"\"With manual acknowledgment and error handling.\"\"\"
    try:
        result = validate_and_process(payload)
        return {"status": "success", "result": result}
    except SoftTimeLimitExceeded:
        # Time limit reached — allow retry
        raise self.retry(countdown=60)
    except ValueError as exc:
        # Expected error — don't retry
        return {"status": "invalid", "error": str(exc)}
    except Exception as exc:
        # Unexpected error — reject and requeue
        raise Reject(f"Failed: {exc}", requeue=True)


def validate_and_process(payload: dict) -> dict:
    \"\"\"Validate and process payload.\"\"\"
    if not payload.get("id"):
        raise ValueError("Missing id in payload")
    return {"processed_id": payload["id"], "timestamp": time.time()}
""",
        "function": "acks_late_manual_acknowledgment_error",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "celery_safe_tasks.py",
    },
    # ── 12. Task state tracking: pending, started, success, failure ──────────
    {
        "normalized_code": """\
from celery.result import AsyncResult
from celery import current_task, states


@app.task(bind=True, track_started=True)
def long_running_job(self, element_id: int) -> str:
    \"\"\"Track state transitions during execution.\"\"\"
    # Update state to STARTED
    self.update_state(state=states.STARTED, meta={"progress": 0})

    for i in range(10):
        time.sleep(1)
        # Update progress during execution
        progress = (i + 1) * 10
        self.update_state(
            state=states.PROGRESS,
            meta={"progress": progress, "current": i + 1, "total": 10},
        )

    # Automatic SUCCESS state on return
    return f"Completed element {element_id}"


def monitor_job_state(job_id: str) -> dict:
    \"\"\"Monitor state and retrieve progress info.\"\"\"
    result = AsyncResult(job_id, app=app)

    return {
        "id": job_id,
        "state": result.state,
        "ready": result.ready(),
        "successful": result.successful(),
        "failed": result.failed(),
        "info": result.info,
    }
""",
        "function": "task_state_tracking_progress_update",
        "feature_type": "route",
        "file_role": "utility",
        "file_path": "celery_task_monitoring.py",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "celery app initialization with redis broker and result backend",
    "task decorator with exponential backoff retry logic",
    "canvas chain group chord primitives parallel sequential execution",
    "periodic task scheduler beat crontab schedule",
    "task result get forget result backend persistence",
    "task signals before publish after publish success failure retry",
    "task routing queue exchange priority rate limit",
    "worker configuration pool concurrency autoscale prefork",
    "acks late manual acknowledgment safe task error handling",
    "task state tracking progress pending started completed",
]


def clone_repo() -> None:
    import os
    if os.path.isdir(REPO_LOCAL):
        return
    subprocess.run(
        ["git", "clone", REPO_URL, REPO_LOCAL, "--depth=1"],
        check=True, capture_output=True,
    )


def build_payloads() -> list[dict]:
    payloads = []
    for p in PATTERNS:
        payloads.append(
            build_payload(
                normalized_code=p["normalized_code"],
                function=p["function"],
                feature_type=p["feature_type"],
                file_role=p["file_role"],
                language=LANGUAGE,
                framework=FRAMEWORK,
                stack=STACK,
                file_path=p["file_path"],
                source_repo=SOURCE_REPO,
                tag=TAG,
                charte_version=CHARTE_VERSION,
            )
        )
    return payloads


def index_patterns(client: QdrantClient, payloads: list[dict]) -> int:
    codes = [p["normalized_code"] for p in payloads]
    vectors = embed_documents_batch(codes)
    points = []
    for vec, payload in zip(vectors, payloads):
        points.append(PointStruct(id=make_uuid(), vector=vec, payload=payload))
    client.upsert(collection_name=COLLECTION, points=points)
    return len(points)


def run_audit_queries(client: QdrantClient) -> list[dict]:
    results = []
    for q in AUDIT_QUERIES:
        vec = embed_query(q)
        hits = query_kb(client, COLLECTION, query_vector=vec, language=LANGUAGE, limit=1)
        if hits:
            hit = hits[0]
            results.append({
                "query": q,
                "function": hit.payload.get("function", "?"),
                "file_role": hit.payload.get("file_role", "?"),
                "score": hit.score,
                "code_preview": hit.payload.get("normalized_code", "")[:50],
            })
        else:
            results.append({"query": q, "function": "NO_RESULT", "file_role": "?", "score": 0.0, "code_preview": ""})
    return results


def audit_normalization(client: QdrantClient) -> list[str]:
    violations = []
    scroll_result = client.scroll(
        collection_name=COLLECTION,
        scroll_filter=Filter(must=[FieldCondition(key="_tag", match=MatchValue(value=TAG))]),
        limit=100,
    )
    for point in scroll_result[0]:
        code = point.payload.get("normalized_code", "")
        fn = point.payload.get("function", "?")
        v = check_charte_violations(code, fn, language=LANGUAGE)
        violations.extend(v)
    return violations


def cleanup(client: QdrantClient) -> None:
    client.delete(
        collection_name=COLLECTION,
        points_selector=FilterSelector(
            filter=Filter(must=[FieldCondition(key="_tag", match=MatchValue(value=TAG))])
        ),
    )


def main() -> None:
    print(f"\n{'='*60}")
    print(f"  INGESTION {REPO_NAME}")
    print(f"  Mode: {'DRY_RUN' if DRY_RUN else 'PRODUCTION'}")
    print(f"{'='*60}\n")

    client = QdrantClient(path=KB_PATH)
    count_initial = client.count(collection_name=COLLECTION).count
    print(f"  KB initial: {count_initial} points")

    clone_repo()

    payloads = build_payloads()
    print(f"  {len(PATTERNS)} patterns extraits")

    # Cleanup existing points for this tag
    cleanup(client)

    n_indexed = index_patterns(client, payloads)
    count_after = client.count(collection_name=COLLECTION).count
    print(f"  {n_indexed} patterns indexés — KB: {count_after} points")

    query_results = run_audit_queries(client)
    violations = audit_normalization(client)

    report = audit_report(
        repo_name=REPO_NAME,
        dry_run=DRY_RUN,
        count_before=count_initial,
        count_after=count_after,
        patterns_extracted=len(PATTERNS),
        patterns_indexed=n_indexed,
        query_results=query_results,
        violations=violations,
    )
    print(report)

    if DRY_RUN:
        cleanup(client)
        print("  DRY_RUN — données supprimées")


if __name__ == "__main__":
    main()
