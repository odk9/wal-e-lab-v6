"""
ingest_bullmq.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de taskforcesh/bullmq dans la KB Qdrant V6.

Focus : CORE patterns job queue (Queue creation, Worker processor, Job lifecycle,
Flow DAGs, Scheduler/Repeat, Backoff, Events, Priority, Bulk ops, Stalled recovery).

Usage:
    .venv/bin/python3 ingest_bullmq.py
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
REPO_URL = "https://github.com/taskforcesh/bullmq.git"
REPO_NAME = "taskforcesh/bullmq"
REPO_LOCAL = "/tmp/bullmq"
LANGUAGE = "typescript"
FRAMEWORK = "generic"
STACK = "typescript+bullmq+redis+queue"
CHARTE_VERSION = "1.0"
TAG = "taskforcesh/bullmq"
SOURCE_REPO = "https://github.com/taskforcesh/bullmq"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# BullMQ = distributed job queue library (TypeScript + Redis).
# Patterns CORE : Queue creation, Worker processing, Job lifecycle, parent-child DAGs,
# recurring/cron scheduling, exponential backoff, event listeners, priority, bulk ops.
# U-5: job_def (not task/todo), work_unit, payload, queue_signal (not event, unless BullMQ event name),
# no user/item/comment/post/order/tag/note entities.

PATTERNS: list[dict] = [
    # ── 1. Queue creation with connection + default options ──────────────────
    {
        "normalized_code": """\
import { Queue } from 'bullmq';
import { createClient } from 'redis';

const connection = createClient({
  host: 'localhost',
  port: 6379,
});

const xxx = new Queue('xxx_queue', {
  connection,
  defaultJobOptions: {
    attempts: 3,
    backoff: {
      type: 'exponential',
      delay: 2000,
    },
    removeOnComplete: true,
    removeOnFail: false,
  },
});

await xxx.waitUntilReady();
""",
        "function": "queue_creation_with_options",
        "feature_type": "config",
        "file_role": "route",
        "file_path": "src/classes/queue.ts",
    },
    # ── 2. Worker processor function (core pattern) ───────────────────────────
    {
        "normalized_code": """\
import { Worker, Job } from 'bullmq';
import { createClient } from 'redis';

const connection = createClient({
  host: 'localhost',
  port: 6379,
});

const processor = async (job: Job<any>) => {
  const { payload } = job.data;

  try {
    job.progress(25);
    const result_1 = await process_step_1(payload);

    job.progress(50);
    const result_2 = await process_step_2(result_1);

    job.progress(75);
    const final_result = await process_step_3(result_2);

    job.progress(100);
    return final_result;
  } catch (err) {
    throw new Error(`processor failed: ${err.message}`);
  }
};

const xxx_worker = new Worker('xxx_queue', processor, {
  connection,
  concurrency: 5,
});

xxx_worker.on('completed', (job, result) => {
  logger.info(`Job ${job.id} completed with result: ${result}`);
});

xxx_worker.on('failed', (job, err) => {
  logger.error(`Job ${job.id} failed: ${err}`);
});
""",
        "function": "worker_processor_function",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "src/classes/worker.ts",
    },
    # ── 3. Add job to queue with options ──────────────────────────────────────
    {
        "normalized_code": """\
import { Queue } from 'bullmq';

const xxx = new Queue('xxx_queue', { connection });

const add_job = async (payload: Record<string, any>) => {
  const result = await xxx.add(
    'process_unit',
    { payload },
    {
      jobId: `job_${Date.now()}`,
      priority: 10,
      delay: 5000,
      attempts: 3,
      backoff: {
        type: 'exponential',
        delay: 2000,
      },
      removeOnComplete: true,
    }
  );

  return result;
};
""",
        "function": "add_single_job",
        "feature_type": "crud",
        "file_role": "route",
        "file_path": "src/classes/queue.ts",
    },
    # ── 4. Bulk job insertion ────────────────────────────────────────────────
    {
        "normalized_code": """\
import { Queue } from 'bullmq';

const xxx = new Queue('xxx_queue', { connection });

interface BulkElement extends Record<string, unknown> {
  priority?: number;
}

const add_bulk_jobs = async (xxxs: BulkElement[]) => {
  const jobs = xxxs.map((element: BulkElement) => ({
    name: 'process_unit',
    data: { payload: element },
    opts: {
      priority: element.priority || 0,
      attempts: 3,
      backoff: { type: 'fixed', delay: 1000 },
    },
  }));

  const result = await xxx.addBulk(jobs);
  return result;
};
""",
        "function": "bulk_job_insertion",
        "feature_type": "crud",
        "file_role": "route",
        "file_path": "src/classes/queue.ts",
    },
    # ── 5. Job priority queueing ──────────────────────────────────────────────
    {
        "normalized_code": """\
import { Queue, Job } from 'bullmq';

const xxx = new Queue('xxx_queue', { connection });

const process_with_priority = async (
  payload: Record<string, any>,
  priority_level: number
) => {
  const xxx_job = await xxx.add(
    'process_unit',
    { payload },
    {
      priority: priority_level,
      attempts: 5,
      backoff: { type: 'exponential', delay: 1000 },
      removeOnComplete: false,
    }
  );

  return xxx_job;
};

const get_highest_priority = async () => {
  const active = await xxx.getActiveCount();
  const paused = await xxx.getPausedCount();

  return { active, paused };
};
""",
        "function": "job_priority_system",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "src/classes/queue.ts",
    },
    # ── 6. FlowProducer: parent-child job DAGs ───────────────────────────────
    {
        "normalized_code": """\
import { FlowProducer, Queue } from 'bullmq';
import { createClient } from 'redis';

const connection = createClient({
  host: 'localhost',
  port: 6379,
});

const flow = new FlowProducer({ connection });

const create_job_flow = async () => {
  const flow_structure = {
    name: 'parent_job',
    data: { payload: 'root_data' },
    children: [
      {
        name: 'child_job_1',
        data: { payload: 'child_1_data' },
        queue: 'child_queue_1',
      },
      {
        name: 'child_job_2',
        data: { payload: 'child_2_data' },
        queue: 'child_queue_2',
        children: [
          {
            name: 'grandchild_job',
            data: { payload: 'grandchild_data' },
            queue: 'grandchild_queue',
          },
        ],
      },
    ],
  };

  const result = await flow.add(flow_structure);
  return result;
};
""",
        "function": "flow_producer_parent_child_dags",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "src/classes/flow-producer.ts",
    },
    # ── 7. Job scheduler: cron and repeat patterns ───────────────────────────
    {
        "normalized_code": """\
import { Queue } from 'bullmq';

const xxx = new Queue('xxx_queue', { connection });

const schedule_cron_job = async () => {
  const cron_job = await xxx.add(
    'periodic_work_unit',
    { payload: 'scheduled_data' },
    {
      repeat: {
        pattern: '0 9 * * *',
        tz: 'America/New_York',
        limit: 100,
        endDate: new Date('2026-12-31'),
      },
    }
  );

  return cron_job;
};

const schedule_interval_job = async () => {
  const interval_job = await xxx.add(
    'repeating_work_unit',
    { payload: 'interval_data' },
    {
      repeat: {
        every: 30000,
        immediately: true,
        count: 50,
      },
    }
  );

  return interval_job;
};
""",
        "function": "job_scheduler_cron_repeat",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "src/classes/repeat.ts",
    },
    # ── 8. Backoff strategies: exponential, fixed, custom ──────────────────────
    {
        "normalized_code": """\
import { BackoffStrategy } from 'bullmq';

type BackoffOptions = {
  type: 'fixed' | 'exponential';
  delay: number;
  jitter?: number;
};

const exponential_backoff: BackoffOptions = {
  type: 'exponential',
  delay: 1000,
  jitter: 0.2,
};

const fixed_backoff: BackoffOptions = {
  type: 'fixed',
  delay: 5000,
  jitter: 0.1,
};

interface QueueJobContext {
  id: string;
  data: Record<string, any>;
}

const custom_backoff_fn: BackoffStrategy = (
  attempts_made: number,
  backoff_type: string,
  err: Error,
  xxx_job: QueueJobContext
) => {
  if (attempts_made < 3) {
    return 1000;
  } else if (attempts_made < 5) {
    return 5000;
  } else {
    return 30000;
  }
};

const xxx = new Queue('xxx_queue', {
  connection,
  settings: {
    backoffStrategies: {
      'custom': custom_backoff_fn,
    },
  },
});
""",
        "function": "backoff_strategies",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "src/classes/backoffs.ts",
    },
    # ── 9. Queue event listeners ──────────────────────────────────────────────
    {
        "normalized_code": """\
import { Queue, Worker } from 'bullmq';

const xxx = new Queue('xxx_queue', { connection });
const xxx_worker = new Worker('xxx_queue', processor, { connection });

xxx.on('waiting', (job) => {
  logger.info(`Job ${job.id} is waiting to be processed`);
});

xxx.on('progress', (job_id, progress) => {
  logger.info(`Job ${job_id} progress: ${progress}%`);
});

xxx.on('completed', (job) => {
  logger.info(`Job ${job.id} completed`);
});

xxx.on('failed', (job, err) => {
  logger.error(`Job ${job.id} failed: ${err.message}`);
});

xxx_worker.on('completed', (job, result) => {
  logger.info(`Worker: Job ${job.id} returned ${result}`);
});

xxx_worker.on('failed', (job, err) => {
  logger.error(`Worker: Job ${job.id} errored: ${err.message}`);
});

xxx_worker.on('active', (job, prev) => {
  logger.info(`Worker: Job ${job.id} is now active (prev: ${prev})`);
});
""",
        "function": "queue_event_listeners",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "src/classes/queue.ts",
    },
    # ── 10. Stalled job recovery and cleanup ──────────────────────────────────
    {
        "normalized_code": """\
import { Queue, Worker } from 'bullmq';

const xxx = new Queue('xxx_queue', { connection });

const recover_stalled_jobs = async () => {
  const stalled_count = await xxx.count('stalled');
  logger.info(`Found ${stalled_count} stalled jobs`);

  const stalled_xxxs = await xxx.getStalled();
  for (const xxx_job of stalled_xxxs) {
    try {
      await xxx_job.retry();
      logger.info(`Retried job ${xxx_job.id}`);
    } catch (err) {
      logger.error(`Failed to retry ${xxx_job.id}: ${err.message}`);
    }
  }
};

const cleanup_queue = async (max_age_ms: number = 3600000) => {
  const cleaned = await xxx.clean(max_age_ms, 1000, 'completed');
  logger.info(`Cleaned ${cleaned.length} completed jobs`);

  const failed_cleaned = await xxx.clean(max_age_ms, 1000, 'failed');
  logger.info(`Cleaned ${failed_cleaned.length} failed jobs`);
};

const obliterate_queue = async () => {
  await xxx.obliterate({ force: true, count: 1000 });
  logger.info('Queue obliterated');
};
""",
        "function": "stalled_recovery_cleanup",
        "feature_type": "route",
        "file_role": "utility",
        "file_path": "src/classes/queue.ts",
    },
    # ── 11. Job getters and filtering ────────────────────────────────────────
    {
        "normalized_code": """\
import { Queue } from 'bullmq';

const xxx = new Queue('xxx_queue', { connection });

const get_jobs_by_state = async () => {
  const waiting = await xxx.getWaiting(0, 100);
  const active = await xxx.getActive(0, 100);
  const completed = await xxx.getCompleted(0, 100);
  const failed = await xxx.getFailed(0, 100);
  const delayed = await xxx.getDelayed(0, 100);

  return {
    waiting,
    active,
    completed,
    failed,
    delayed,
  };
};

const get_xxx_by_id = async (xxx_id: string) => {
  const xxx_job = await xxx.getJob(xxx_id);

  if (!xxx_job) {
    throw new Error(`Job ${xxx_id} not found`);
  }

  const state = await xxx_job.getState();
  const progress = xxx_job.progress();
  const is_active = await xxx_job.isActive();

  return {
    xxx_job,
    state,
    progress,
    is_active,
  };
};
""",
        "function": "job_getters_filtering",
        "feature_type": "route",
        "file_role": "utility",
        "file_path": "src/classes/queue.ts",
    },
    # ── 12. Worker with concurrency and rate limiting ──────────────────────────
    {
        "normalized_code": """\
import { Worker, Queue } from 'bullmq';

const xxx = new Queue('xxx_queue', { connection });

interface ProcessorJob {
  id: string;
  data: { payload: Record<string, any> };
  progress(percentage: number): void;
}

const processor = async (job: ProcessorJob) => {
  const work_unit_data = job.data.payload;

  job.progress(10);
  await process_step_1(work_unit_data);

  job.progress(50);
  const result = await process_step_2(work_unit_data);

  job.progress(100);
  return result;
};

const xxx_worker = new Worker('xxx_queue', processor, {
  connection,
  concurrency: 10,
  maxStalledCount: 3,
  stalledInterval: 5000,
  lockDuration: 30000,
  lockRenewTime: 15000,
});

xxx_worker.on('drained', () => {
  logger.info('Queue drained: no more jobs to process');
});

xxx_worker.on('error', (err: Error) => {
  logger.error('Worker error:', err);
});

await xxx_worker.waitUntilReady();
""",
        "function": "worker_concurrency_rate_limiting",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "src/classes/worker.ts",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "create queue with connection and default options",
    "worker processor function for job execution",
    "add single job to queue with priority and backoff",
    "bulk insert jobs in queue",
    "parent child job dependencies flow producer DAG",
    "cron schedule and repeat job patterns",
    "exponential backoff retry strategy",
    "queue and worker event listeners",
    "stalled job recovery and cleanup queue",
    "get jobs by state waiting active completed failed",
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
