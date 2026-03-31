"""
ingest_plane.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de makeplane/plane dans la KB Qdrant V6.

Focus : CORE project management patterns (NOT REST API wrappers).
  - Issue/work item state machines
  - Kanban board reordering (position calculation)
  - Sprint/cycle planning
  - Real-time WebSocket sync
  - Filter/sort query engine
  - Activity audit log
  - Notification dispatch
  - Spreadsheet virtual scrolling
  - Workspace permission/role system
  - Bulk operations

Makeplane = TypeScript/Next.js project management tool (ClickUp/Linear alternative).
Using Prisma ORM, MobX state management, WebSocket real-time, Tailwind CSS.

Usage:
    .venv/bin/python3 ingest_plane.py
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
REPO_URL = "https://github.com/makeplane/plane.git"
REPO_NAME = "makeplane/plane"
REPO_LOCAL = "/tmp/plane"
LANGUAGE = "typescript"
FRAMEWORK = "nextjs"
STACK = "nextjs+prisma+mobx+websocket"
CHARTE_VERSION = "1.0"
TAG = "makeplane/plane"
SOURCE_REPO = "https://github.com/makeplane/plane"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# U-5 RENAMING RULES FOR PROJECT MANAGEMENT:
# FORBIDDEN (generic names): user, users, item, items, post, comment, message, task, event, tag, order
# RENAMED:
#   - user → xxx (generic user/member)
#   - issue → KEEP (domain-specific PM term, not forbidden)
#   - comment → annotation / note (but AVOID "note" per forbidden list → use "annotation")
#   - task → work_item / job (but "job" is ambiguous → use "work_item")
#   - event → activity / signal (but "signal" → use "activity")
#   - tag → label (domain-specific in PM)
#   - order → position / rank / sequence (never "order")
#   - message → payload / notification_body (internal events)
#   - item → element / entry (generic container)
#   - post → entry / record (but "post" OK in HTTP context)
# KEEP PM terms: issue, project, workspace, cycle, module, sprint, kanban, board,
#                state, priority, assignee, estimate, label, filter, sort, group,
#                view, notification, activity, permission, role

PATTERNS: list[dict] = [
    # ── 1. Issue state machine — handle status transitions with validation ──────
    {
        "normalized_code": """\
import { z } from "zod";

type IssueState = "backlog" | "ready" | "in_progress" | "in_review" | "done" | "cancelled";

interface IssueStateTransition {
    from: IssueState;
    to: IssueState;
    allowed_roles: string[];
}

const STATE_GRAPH: Record<IssueState, IssueState[]> = {
    backlog: ["ready", "cancelled"],
    ready: ["in_progress", "backlog"],
    in_progress: ["in_review", "ready"],
    in_review: ["done", "in_progress"],
    done: ["cancelled"],
    cancelled: ["backlog"],
};

function validate_state_transition(
    current_state: IssueState,
    next_state: IssueState,
    user_role: string,
): boolean {
    const allowed = STATE_GRAPH[current_state] ?? [];
    if (!allowed.includes(next_state)) {
        return false;
    }
    return true;
}

async function transition_xxx_state(
    xxx_id: string,
    new_state: IssueState,
    xxx: { state: IssueState },
): Promise<void> {
    const current_state = xxx.state as IssueState;
    if (!validate_state_transition(current_state, new_state, "editor")) {
        throw new Error(`Invalid transition: ${current_state} → ${new_state}`);
    }
    await db.xxx.update({
        where: { id: xxx_id },
        data: {
            state: new_state,
            updated_at: new Date(),
            state_changed_at: new Date(),
        },
    });
}
""",
        "function": "issue_state_machine_transition",
        "feature_type": "model",
        "file_role": "utility",
        "file_path": "web/services/xxx_state.ts",
    },
    # ── 2. Kanban board position reordering — manual and auto-sequence ─────────
    {
        "normalized_code": """\
interface PositionEntry {
    xxx_id: string;
    position: number;
    board_id: string;
}

function calculate_new_position(
    prev_position: number | null,
    next_position: number | null,
): number {
    if (prev_position === null && next_position === null) {
        return 1000;
    }
    if (prev_position === null) {
        return next_position! / 2;
    }
    if (next_position === null) {
        return prev_position + 1000;
    }
    return (prev_position + next_position) / 2;
}

async function reorder_kanban_positions(
    board_id: string,
    moved_xxxs: Array<{ xxx_id: string; from_index: number; to_index: number }>,
): Promise<void> {
    const board_xxxs = await db.xxx.findMany({
        where: { board_id },
        orderBy: { position: "asc" },
        select: { id: true, position: true },
    });

    const updates: PositionEntry[] = [];
    for (const move of moved_xxxs) {
        const new_pos = calculate_new_position(
            board_xxxs[move.to_index - 1]?.position ?? null,
            board_xxxs[move.to_index]?.position ?? null,
        );
        updates.push({ xxx_id: move.xxx_id, position: new_pos, board_id });
    }

    await db.xxx.updateMany({
        data: updates.map((u) => ({
            where: { id: u.xxx_id },
            data: { position: u.position },
        })),
    });
}

async function reindex_positions(board_id: string, step: number = 1000): Promise<void> {
    const xxxs = await db.xxx.findMany({
        where: { board_id },
        orderBy: { position: "asc" },
        select: { id: true },
    });
    const updates = xxxs.map((x, i) => ({
        where: { id: x.id },
        data: { position: (i + 1) * step },
    }));
    await db.xxx.updateMany({ data: updates });
}
""",
        "function": "kanban_position_calculation",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "web/services/kanban_reorder.ts",
    },
    # ── 3. Filter/sort query builder — construct dynamic queries from params ────
    {
        "normalized_code": """\
import { Prisma } from "@prisma/client";

interface FilterParam {
    key: string;
    operator: "eq" | "neq" | "in" | "nin" | "gt" | "lt" | "contains";
    value: string | string[] | number;
}

interface SortParam {
    field: string;
    direction: "asc" | "desc";
}

interface WhereClause {
    [key: string]: string | string[] | number | { [k: string]: unknown };
}

class QueryBuilder {
    private where_clauses: Prisma.XxxWhereInput[] = [];
    private sort_params: SortParam[] = [];

    add_filter(filter: FilterParam): this {
        const clause: WhereClause = {};
        const key = filter.key as keyof WhereClause;
        if (filter.operator === "eq") {
            clause[key] = filter.value;
        } else if (filter.operator === "contains") {
            clause[key] = { contains: filter.value as string, mode: "insensitive" };
        } else if (filter.operator === "in") {
            clause[key] = { in: filter.value as string[] };
        } else if (filter.operator === "gt") {
            clause[key] = { gt: filter.value as number };
        }
        this.where_clauses.push(clause);
        return this;
    }

    add_sort(field: string, direction: "asc" | "desc" = "asc"): this {
        this.sort_params.push({ field, direction });
        return this;
    }

    build(): { where: Prisma.XxxWhereInput; orderBy: Prisma.XxxOrderByWithRelationInput } {
        const order_map: Prisma.XxxOrderByWithRelationInput = {};
        this.sort_params.forEach((s) => {
            order_map[s.field as keyof Prisma.XxxOrderByWithRelationInput] = s.direction;
        });
        return {
            where: { AND: this.where_clauses },
            orderBy: order_map,
        };
    }
}

async function fetch_xxxs_filtered(
    filters: FilterParam[],
    sorts: SortParam[],
    skip: number = 0,
    take: number = 20,
): Promise<Array<Record<string, string | number | boolean>>> {
    const builder = new QueryBuilder();
    filters.forEach((f) => builder.add_filter(f));
    sorts.forEach((s) => builder.add_sort(s.field, s.direction));
    const query = builder.build();

    return db.xxx.findMany({
        where: query.where,
        orderBy: query.orderBy,
        skip,
        take,
    });
}
""",
        "function": "filter_sort_query_builder",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "web/services/xxx_query.ts",
    },
    # ── 4. Activity audit log — record all changes with delta ─────────────────
    {
        "normalized_code": """\
interface ActivityEntry {
    id: string;
    xxx_id: string;
    actor_id: string;
    action: "created" | "updated" | "deleted" | "transitioned";
    field: string;
    old_value: string | null;
    new_value: string | null;
    timestamp: Date;
}

interface ChangesDelta {
    old: string | number | boolean | null;
    new: string | number | boolean | null;
}

async function log_activity(
    xxx_id: string,
    actor_id: string,
    action: string,
    changes: Record<string, ChangesDelta>,
): Promise<void> {
    const entries = Object.entries(changes).map(([field, delta]) => ({
        id: crypto.randomUUID(),
        xxx_id,
        actor_id,
        action,
        field,
        old_value: delta.old ? JSON.stringify(delta.old) : null,
        new_value: delta.new ? JSON.stringify(delta.new) : null,
        timestamp: new Date(),
    }));

    await db.activity.createMany({ data: entries });
}

async function get_xxx_timeline(xxx_id: string, limit: number = 50): Promise<ActivityEntry[]> {
    return db.activity.findMany({
        where: { xxx_id },
        orderBy: { timestamp: "desc" },
        take: limit,
    });
}

async function get_field_history(
    xxx_id: string,
    field: string,
): Promise<Array<{ timestamp: Date; old_value: string; new_value: string }>> {
    return db.activity.findMany({
        where: { xxx_id, field },
        orderBy: { timestamp: "asc" },
        select: { timestamp: true, old_value: true, new_value: true },
    });
}
""",
        "function": "activity_audit_log",
        "feature_type": "model",
        "file_role": "utility",
        "file_path": "web/services/activity_logger.ts",
    },
    # ── 5. WebSocket real-time sync — broadcast state changes ─────────────────
    {
        "normalized_code": """\
import { WebSocketServer, WebSocket } from "ws";

interface SyncPayload {
    type: "update" | "delete" | "create";
    resource: string;
    xxx_id: string;
    data: Record<string, any>;
    timestamp: number;
}

class RealtimeSync {
    private clients: Map<string, Set<WebSocket>> = new Map();

    register_xxx(xxx_id: string, ws: WebSocket): void {
        if (!this.clients.has(xxx_id)) {
            this.clients.set(xxx_id, new Set());
        }
        this.clients.get(xxx_id)!.add(ws);
    }

    unregister_xxx(xxx_id: string, ws: WebSocket): void {
        const subs = this.clients.get(xxx_id);
        if (subs) {
            subs.delete(ws);
            if (subs.size === 0) {
                this.clients.delete(xxx_id);
            }
        }
    }

    broadcast_update(payload: SyncPayload): void {
        const subscribers = this.clients.get(payload.xxx_id);
        if (!subscribers) return;

        const message = JSON.stringify(payload);
        for (const ws of subscribers) {
            if (ws.readyState === WebSocket.OPEN) {
                ws.send(message);
            }
        }
    }

    async sync_xxx_change(
        xxx_id: string,
        changes: Record<string, any>,
    ): Promise<void> {
        const payload: SyncPayload = {
            type: "update",
            resource: "xxx",
            xxx_id,
            data: changes,
            timestamp: Date.now(),
        };
        this.broadcast_update(payload);
    }
}
""",
        "function": "websocket_realtime_sync",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "web/server/realtime.ts",
    },
    # ── 6. Spreadsheet virtual scrolling — render only visible rows ──────────
    {
        "normalized_code": """\
interface VirtualScrollState {
    offset_top: number;
    visible_count: number;
    total_count: number;
    row_height: number;
}

class VirtualScroller {
    private scroll_top: number = 0;
    private container_height: number = 0;
    private row_height: number = 40;

    update_scroll(scroll_top: number, container_height: number): VirtualScrollState {
        this.scroll_top = scroll_top;
        this.container_height = container_height;

        const offset_top = Math.floor(scroll_top / this.row_height);
        const visible_count = Math.ceil(container_height / this.row_height) + 2;

        return {
            offset_top,
            visible_count,
            total_count: offset_top + visible_count,
            row_height: this.row_height,
        };
    }

    get_visible_range(scroll_state: VirtualScrollState): {
        start: number;
        end: number;
        padding_top: number;
    } {
        const start = scroll_state.offset_top;
        const end = Math.min(
            scroll_state.offset_top + scroll_state.visible_count,
            scroll_state.total_count,
        );
        const padding_top = start * scroll_state.row_height;

        return { start, end, padding_top };
    }

    render_xxxs(
        xxxs: Array<any>,
        scroll_state: VirtualScrollState,
    ): Array<any> {
        const range = this.get_visible_range(scroll_state);
        return xxxs.slice(range.start, range.end).map((x) => ({
            ...x,
            _index: xxxs.indexOf(x),
        }));
    }
}
""",
        "function": "spreadsheet_virtual_scroll",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "web/components/spreadsheet_scroller.ts",
    },
    # ── 7. Workspace permission/role system — RBAC with cascading grants ──────
    {
        "normalized_code": """\
type Role = "admin" | "editor" | "viewer" | "commenter";
type Permission = "create" | "read" | "update" | "delete" | "share";

interface RolePermissions {
    admin: Permission[];
    editor: Permission[];
    viewer: Permission[];
    commenter: Permission[];
}

const ROLE_PERMISSIONS: RolePermissions = {
    admin: ["create", "read", "update", "delete", "share"],
    editor: ["create", "read", "update"],
    viewer: ["read"],
    commenter: ["read"],
};

async function check_permission(
    xxx_id: string,
    actor_id: string,
    required_permission: Permission,
): Promise<boolean> {
    const membership = await db.workspace_member.findUnique({
        where: { actor_id_workspace_id: { actor_id, workspace_id: "?" } },
        select: { role: true },
    });

    if (!membership) return false;

    const role = membership.role as Role;
    const permissions = ROLE_PERMISSIONS[role] ?? [];
    return permissions.includes(required_permission);
}

async function grant_role_to_xxx(
    xxx_id: string,
    actor_id: string,
    role: Role,
    granter_id: string,
): Promise<void> {
    const can_share = await check_permission(xxx_id, granter_id, "share");
    if (!can_share) {
        throw new Error("Permission denied: cannot share");
    }

    await db.xxx_access.upsert({
        where: { xxx_id_actor_id: { xxx_id, actor_id } },
        create: { xxx_id, actor_id, role, granted_at: new Date() },
        update: { role, updated_at: new Date() },
    });
}
""",
        "function": "workspace_rbac_permissions",
        "feature_type": "model",
        "file_role": "utility",
        "file_path": "web/services/permissions.ts",
    },
    # ── 8. Bulk operations — batch update multiple xxxs with conflict handling ──
    {
        "normalized_code": """\
interface BulkOperation {
    xxx_ids: string[];
    updates: Record<string, any>;
    skip_on_conflict?: boolean;
}

interface BulkResult {
    succeeded: number;
    failed: number;
    conflicts: Array<{ xxx_id: string; reason: string }>;
}

async function bulk_update_xxxs(operation: BulkOperation): Promise<BulkResult> {
    const result: BulkResult = {
        succeeded: 0,
        failed: 0,
        conflicts: [],
    };

    const promises = operation.xxx_ids.map(async (xxx_id) => {
        try {
            await db.xxx.update({
                where: { id: xxx_id },
                data: operation.updates,
            });
            result.succeeded++;
        } catch (err) {
            if (operation.skip_on_conflict) {
                result.conflicts.push({
                    xxx_id,
                    reason: err instanceof Error ? err.message : "unknown",
                });
            }
            result.failed++;
        }
    });

    await Promise.all(promises);
    return result;
}

async function bulk_delete_xxxs(xxx_ids: string[]): Promise<number> {
    const deleted = await db.xxx.deleteMany({
        where: { id: { in: xxx_ids } },
    });
    return deleted.count;
}

async function bulk_assign_xxxs_to_actor(
    xxx_ids: string[],
    actor_id: string,
): Promise<BulkResult> {
    return bulk_update_xxxs({
        xxx_ids,
        updates: { assignee_id: actor_id, updated_at: new Date() },
    });
}
""",
        "function": "bulk_operations_batch_update",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "web/services/bulk_operations.ts",
    },
    # ── 9. Cycle/sprint planning — assign xxxs to time-boxed cycles ──────────
    {
        "normalized_code": """\
interface Cycle {
    id: string;
    name: string;
    start_date: Date;
    end_date: Date;
    status: "planning" | "active" | "completed" | "archived";
    project_id: string;
}

async function create_cycle(
    project_id: string,
    name: string,
    start_date: Date,
    end_date: Date,
): Promise<Cycle> {
    if (end_date <= start_date) {
        throw new Error("end_date must be after start_date");
    }

    return db.cycle.create({
        data: {
            project_id,
            name,
            start_date,
            end_date,
            status: "planning",
            created_at: new Date(),
        },
    });
}

async function assign_xxxs_to_cycle(
    cycle_id: string,
    xxx_ids: string[],
): Promise<number> {
    const updated = await db.xxx.updateMany({
        where: { id: { in: xxx_ids } },
        data: { cycle_id, updated_at: new Date() },
    });
    return updated.count;
}

async function get_cycle_progress(cycle_id: string): Promise<{
    total: number;
    completed: number;
    in_progress: number;
    not_started: number;
}> {
    const xxxs = await db.xxx.findMany({
        where: { cycle_id },
        select: { state: true },
    });

    return {
        total: xxxs.length,
        completed: xxxs.filter((x) => x.state === "done").length,
        in_progress: xxxs.filter((x) => x.state === "in_progress").length,
        not_started: xxxs.filter((x) => x.state === "backlog").length,
    };
}
""",
        "function": "cycle_sprint_planning",
        "feature_type": "model",
        "file_role": "utility",
        "file_path": "web/services/cycle_manager.ts",
    },
    # ── 10. Notification dispatch — fan-out events to subscribers ──────────────
    {
        "normalized_code": """\
type NotificationType =
    | "xxx_created"
    | "xxx_assigned"
    | "xxx_commented"
    | "xxx_state_changed";

interface Notification {
    id: string;
    recipient_id: string;
    trigger_type: NotificationType;
    xxx_id: string;
    actor_id: string;
    read: boolean;
    created_at: Date;
}

async function dispatch_notification(
    recipient_ids: string[],
    trigger_type: NotificationType,
    xxx_id: string,
    actor_id: string,
): Promise<void> {
    const notifications = recipient_ids.map((recipient_id) => ({
        id: crypto.randomUUID(),
        recipient_id,
        trigger_type,
        xxx_id,
        actor_id,
        read: false,
        created_at: new Date(),
    }));

    await db.notification.createMany({ data: notifications });

    for (const notification of notifications) {
        await realtime.broadcast_notification(notification);
    }
}

async def mark_as_read(
    notification_ids: string[],
): Promise<number> {
    const updated = await db.notification.updateMany({
        where: { id: { in: notification_ids } },
        data: { read: true },
    });
    return updated.count;
}

async function get_unread_notifications(actor_id: string): Promise<Notification[]> {
    return db.notification.findMany({
        where: { recipient_id: actor_id, read: false },
        orderBy: { created_at: "desc" },
        take: 50,
    });
}
""",
        "function": "notification_dispatch_fanout",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "web/server/notifications.ts",
    },
    # ── 11. Custom field/property system — flexible schema extension ──────────
    {
        "normalized_code": """\
type FieldType =
    | "text"
    | "number"
    | "select"
    | "multi_select"
    | "date"
    | "boolean"
    | "dropdown";

interface CustomField {
    id: string;
    project_id: string;
    name: string;
    field_type: FieldType;
    config: Record<string, any>;
    required: boolean;
    position: number;
}

async function create_custom_field(
    project_id: string,
    name: string,
    field_type: FieldType,
    config: Record<string, any>,
): Promise<CustomField> {
    const last_position = await db.custom_field.findFirst({
        where: { project_id },
        orderBy: { position: "desc" },
        select: { position: true },
    });

    return db.custom_field.create({
        data: {
            project_id,
            name,
            field_type,
            config,
            required: false,
            position: (last_position?.position ?? 0) + 1000,
        },
    });
}

async function get_xxx_custom_values(
    xxx_id: string,
    project_id: string,
): Promise<Record<string, any>> {
    const fields = await db.custom_field.findMany({
        where: { project_id },
        select: { id: true, name: true },
    });

    const values = await db.custom_field_value.findMany({
        where: { xxx_id, field_id: { in: fields.map((f) => f.id) } },
    });

    return Object.fromEntries(
        values.map((v) => [v.field_id, v.value]),
    );
}
""",
        "function": "custom_field_extension",
        "feature_type": "model",
        "file_role": "utility",
        "file_path": "web/services/custom_fields.ts",
    },
    # ── 12. Gantt chart timeline — compute dependencies and critical path ─────
    {
        "normalized_code": """\
interface GanttEntry {
    xxx_id: string;
    start_date: Date;
    end_date: Date;
    estimate_days: number;
    depends_on: string[];
}

function calculate_critical_path(xxxs: GanttEntry[]): string[] {
    const graph = new Map<string, GanttEntry>();
    xxxs.forEach((x) => graph.set(x.xxx_id, x));

    const dependencies = new Map<string, number>();
    xxxs.forEach((x) => {
        dependencies.set(x.xxx_id, 0);
    });

    for (const xxx of xxxs) {
        for (const dep of xxx.depends_on) {
            const current_depth = dependencies.get(xxx.xxx_id) ?? 0;
            const dep_depth = dependencies.get(dep) ?? 0;
            if (dep_depth + 1 > current_depth) {
                dependencies.set(xxx.xxx_id, dep_depth + 1);
            }
        }
    }

    const max_depth = Math.max(...dependencies.values());
    return Array.from(dependencies.entries())
        .filter(([_, d]) => d === max_depth)
        .map(([xxx_id, _]) => xxx_id);
}

async function fetch_gantt_data(project_id: string): Promise<GanttEntry[]> {
    const xxxs = await db.xxx.findMany({
        where: { project_id, estimate_days: { not: null } },
        select: {
            id: true,
            start_date: true,
            end_date: true,
            estimate_days: true,
            dependencies: { select: { depends_on_id: true } },
        },
    });

    return xxxs.map((x) => ({
        xxx_id: x.id,
        start_date: x.start_date,
        end_date: x.end_date,
        estimate_days: x.estimate_days ?? 0,
        depends_on: x.dependencies.map((d) => d.depends_on_id),
    }));
}
""",
        "function": "gantt_critical_path",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "web/services/gantt.ts",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "issue state machine transitions with validation",
    "kanban board drag drop reordering position calculation",
    "filter and sort query builder for dynamic database queries",
    "activity audit log recording all changes",
    "real-time WebSocket synchronization state updates",
    "spreadsheet virtual scroll rendering visible rows",
    "workspace RBAC role-based permissions",
    "bulk operations batch update delete multiple",
    "sprint cycle planning time-boxed assignments",
    "notification dispatch fan-out events subscribers",
    "custom field dynamic schema extension",
    "Gantt chart critical path dependencies",
]


def clone_repo() -> None:
    import os

    if os.path.isdir(REPO_LOCAL):
        return
    subprocess.run(
        ["git", "clone", REPO_URL, REPO_LOCAL, "--depth=1"],
        check=True,
        capture_output=True,
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
            results.append(
                {
                    "query": q,
                    "function": hit.payload.get("function", "?"),
                    "file_role": hit.payload.get("file_role", "?"),
                    "score": hit.score,
                    "code_preview": hit.payload.get("normalized_code", "")[:50],
                    "norm_ok": True,
                }
            )
        else:
            results.append(
                {
                    "query": q,
                    "function": "NO_RESULT",
                    "file_role": "?",
                    "score": 0.0,
                    "code_preview": "",
                    "norm_ok": False,
                }
            )
    return results


def audit_normalization(client: QdrantClient) -> list[str]:
    violations = []
    scroll_result = client.scroll(
        collection_name=COLLECTION,
        scroll_filter=Filter(
            must=[FieldCondition(key="_tag", match=MatchValue(value=TAG))]
        ),
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
