"""SQLite demo storage and the atomic policy transaction for one built-in write."""

import copy
import hashlib
import json
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    func,
    select,
)
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from .models import AgentConfig, RunStep, ToolCall, ToolInvocation, ToolResult
from .redaction import redact, trace_summary
from .runtime import RunState, Status
from .tools import Permission, RuntimeFault


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


class Base(DeclarativeBase):
    pass


class AgentRow(Base):
    __tablename__ = "agents"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    config: Mapped[dict] = mapped_column(JSON)


class RunRow(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"))
    input: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    config_snapshot: Mapped[dict] = mapped_column(JSON)
    model_resume_state: Mapped[dict] = mapped_column(JSON)
    checkpoint_digest: Mapped[str] = mapped_column(String)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = mapped_column(String, default=utcnow)


class StepRow(Base):
    __tablename__ = "run_steps"
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    data: Mapped[dict] = mapped_column(JSON)


class EventRow(Base):
    __tablename__ = "run_events"
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), primary_key=True)
    event_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    data: Mapped[dict] = mapped_column(JSON)


class InvocationRow(Base):
    __tablename__ = "tool_invocations"
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), primary_key=True)
    call_id: Mapped[str] = mapped_column(String, primary_key=True)
    tool_name: Mapped[str] = mapped_column(String)
    validated_args: Mapped[dict] = mapped_column(JSON)
    permission: Mapped[str] = mapped_column(String)
    step_seq: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String)
    result: Mapped[dict | list | str | None] = mapped_column(JSON, nullable=True)
    approval_id: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(
        String, unique=True, nullable=True
    )


class ApprovalRow(Base):
    __tablename__ = "approvals"
    __table_args__ = (
        UniqueConstraint("run_id", "call_id"),
        CheckConstraint("status IN ('PENDING','APPROVED','REJECTED')"),
    )
    approval_id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    call_id: Mapped[str] = mapped_column(String)
    tool_name: Mapped[str] = mapped_column(String)
    request_payload: Mapped[dict] = mapped_column(JSON)
    args_digest: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="PENDING")
    created_at: Mapped[str] = mapped_column(String)
    decided_at: Mapped[str | None] = mapped_column(String, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String, nullable=True)


class PurchaseDraftRow(Base):
    __tablename__ = "purchase_drafts"
    __table_args__ = (
        UniqueConstraint("run_id", "call_id"),
        CheckConstraint(
            "quantity > 0 AND unit_price_cents > 0 AND total_cents <= budget_cents"
        ),
    )
    draft_id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    call_id: Mapped[str] = mapped_column(String)
    approval_id: Mapped[str] = mapped_column(
        ForeignKey("approvals.approval_id"), unique=True
    )
    idempotency_key: Mapped[str] = mapped_column(String, unique=True)
    supplier: Mapped[str] = mapped_column(String)
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price_cents: Mapped[int] = mapped_column(Integer)
    budget_cents: Mapped[int] = mapped_column(Integer)
    total_cents: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String)


@dataclass
class DecisionResult:
    run: RunState
    replayed: bool
    resume: bool


class Storage:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.engine = create_engine(
            f"sqlite:///{self.path.as_posix()}",
            connect_args={"check_same_thread": False, "timeout": 5},
        )

        @event.listens_for(self.engine, "connect")
        def configure(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=5000")

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.engine.connect() as connection:
            version = connection.exec_driver_sql("PRAGMA user_version").scalar_one()
            if version not in {0, 1}:
                raise RuntimeFault("UNSUPPORTED_DB_SCHEMA")
            connection.exec_driver_sql("PRAGMA journal_mode=WAL")
            Base.metadata.create_all(connection)
            connection.exec_driver_sql("PRAGMA user_version=1")
            connection.commit()

    @contextmanager
    def transaction(self):
        with Session(self.engine) as session:
            try:
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
                yield session
                session.commit()
            except OperationalError:
                session.rollback()
                raise RuntimeFault("STORAGE_BUSY") from None

    def close(self):
        self.engine.dispose()

    def save_agent(self, config):
        with self.transaction() as session:
            if session.get(AgentRow, config.id) is None:
                session.add(
                    AgentRow(id=config.id, config=config.model_dump(mode="json"))
                )

    def agents(self):
        with Session(self.engine) as session:
            return [
                AgentConfig.model_validate_json(json.dumps(row.config))
                for row in session.scalars(select(AgentRow).order_by(AgentRow.id))
            ]

    def create_run(self, run, config, task):
        self.save_agent(config)
        run.config_snapshot = config.model_dump(mode="json")
        with self.transaction() as session:
            if session.get(RunRow, run.run_id) is not None:
                return
            session.add(
                RunRow(
                    id=run.run_id,
                    agent_id=config.id,
                    input=task,
                    status=run.status.value,
                    payload=self._payload(run),
                    config_snapshot=run.config_snapshot,
                    model_resume_state=run.model_resume_state,
                    checkpoint_digest=self._checkpoint_digest(run),
                    revision=run.revision,
                )
            )

    @staticmethod
    def _payload(run):
        return {
            key: value
            for key, value in asdict(run).items()
            if key
            not in {
                "steps",
                "events",
                "invocations",
                "model_resume_state",
                "config_snapshot",
                "revision",
                "status",
            }
        }

    @staticmethod
    def _checkpoint_digest(run):
        return digest({"config": run.config_snapshot, "resume": run.model_resume_state})

    def _save(self, session, run):
        row = session.get(RunRow, run.run_id)
        if row is None or row.revision != run.revision:
            raise RuntimeFault("STALE_RUN_STATE")
        row.status, row.payload = run.status.value, self._payload(run)
        row.config_snapshot = copy.deepcopy(run.config_snapshot)
        row.model_resume_state = copy.deepcopy(run.model_resume_state)
        row.checkpoint_digest = self._checkpoint_digest(run)
        row.revision += 1
        run.revision = row.revision
        for step in run.steps:
            item = session.get(StepRow, (run.run_id, step.seq))
            if item is None:
                session.add(
                    StepRow(run_id=run.run_id, seq=step.seq, data=redact(asdict(step)))
                )
            else:
                item.data = redact(asdict(step))
        for event_data in run.events:
            if session.get(EventRow, (run.run_id, event_data["event_id"])) is None:
                session.add(
                    EventRow(
                        run_id=run.run_id,
                        event_id=event_data["event_id"],
                        data=redact(event_data),
                    )
                )
        for invocation in run.invocations:
            values = asdict(invocation)
            row = session.get(InvocationRow, (run.run_id, invocation.call_id))
            if row is None:
                session.add(InvocationRow(run_id=run.run_id, **values))
            else:
                if row.validated_args != invocation.validated_args:
                    raise RuntimeFault("CHECKPOINT_INVALID")
                for key, value in values.items():
                    setattr(row, key, copy.deepcopy(value))
        session.flush()

    def save(self, run):
        with self.transaction() as session:
            self._save(session, run)

    def _load(self, session, run_id):
        row = session.get(RunRow, run_id)
        if row is None:
            raise RuntimeFault("RUN_NOT_FOUND")
        run = RunState(
            **copy.deepcopy(row.payload),
            status=Status(row.status),
            revision=row.revision,
            model_resume_state=copy.deepcopy(row.model_resume_state),
            config_snapshot=copy.deepcopy(row.config_snapshot),
        )
        run.steps = [
            RunStep(**item.data)
            for item in session.scalars(
                select(StepRow).where(StepRow.run_id == run_id).order_by(StepRow.seq)
            )
        ]
        run.events = [
            item.data
            for item in session.scalars(
                select(EventRow)
                .where(EventRow.run_id == run_id)
                .order_by(EventRow.event_id)
            )
        ]
        run.invocations = [
            ToolInvocation(
                **{
                    key: getattr(item, key)
                    for key in ToolInvocation.__dataclass_fields__
                }
            )
            for item in session.scalars(
                select(InvocationRow)
                .where(InvocationRow.run_id == run_id)
                .order_by(InvocationRow.step_seq)
            )
        ]
        return run

    def get_run(self, run_id):
        with Session(self.engine) as session:
            session.connection().exec_driver_sql("BEGIN")
            return self._load(session, run_id)

    def runs(self, offset=0, limit=20):
        with Session(self.engine) as session:
            ids = list(
                session.scalars(
                    select(RunRow.id)
                    .order_by(RunRow.created_at.desc(), RunRow.id.desc())
                    .offset(offset)
                    .limit(limit)
                )
            )
        return [self.get_run(run_id) for run_id in ids]

    def run_count(self):
        with Session(self.engine) as session:
            return session.scalar(select(func.count()).select_from(RunRow))

    def pause(self, run, invocation):
        approval_id = str(uuid4())
        bound = {
            "run_id": run.run_id,
            "call_id": invocation.call_id,
            "tool_name": invocation.tool_name,
            "arguments": invocation.validated_args,
        }
        invocation.status, invocation.approval_id = "PENDING", approval_id
        invocation.idempotency_key = digest(bound)
        run.transition(Status.WAITING_APPROVAL)
        run.stop_reason = "APPROVAL_REQUIRED"
        run.model_resume_state["safe_point"] = "WAITING_APPROVAL"
        run.steps[-1].status = "WAITING_APPROVAL"
        run.steps.append(
            RunStep(
                run.run_id,
                len(run.steps) + 1,
                "approval",
                utcnow(),
                status="WAITING_APPROVAL",
                tool_name=invocation.tool_name,
                call_id=invocation.call_id,
                arguments_summary=trace_summary(invocation.validated_args),
            )
        )
        run.emit(
            "approval.requested",
            approval_id=approval_id,
            call_id=invocation.call_id,
            tool_name=invocation.tool_name,
            args_digest=digest(bound),
            arguments_summary=trace_summary(invocation.validated_args),
            effect="Insert one local demo draft; no real order.",
        )
        run.emit(
            "run.checkpointed", safe_point="WAITING_APPROVAL", approval_id=approval_id
        )
        with self.transaction() as session:
            self._save(session, run)
            session.add(
                ApprovalRow(
                    approval_id=approval_id,
                    run_id=run.run_id,
                    call_id=invocation.call_id,
                    tool_name=invocation.tool_name,
                    request_payload=invocation.validated_args,
                    args_digest=digest(bound),
                    status="PENDING",
                    created_at=utcnow(),
                )
            )

    def approvals(self, run_id=None, *, pending_only=False):
        with Session(self.engine) as session:
            query = select(ApprovalRow).order_by(ApprovalRow.created_at)
            if run_id is not None:
                query = query.where(ApprovalRow.run_id == run_id)
            if pending_only:
                query = query.where(
                    ApprovalRow.status == "PENDING",
                    ApprovalRow.run_id.in_(
                        select(RunRow.id).where(RunRow.status == "WAITING_APPROVAL")
                    ),
                )
            return [
                {
                    "approval_id": row.approval_id,
                    "run_id": row.run_id,
                    "call_id": redact(row.call_id),
                    "tool_name": row.tool_name,
                    "request_payload": redact(row.request_payload),
                    "args_digest": row.args_digest,
                    "status": row.status,
                    "created_at": row.created_at,
                    "decided_at": row.decided_at,
                    "effect": "Insert one local demo draft; no real order.",
                }
                for row in session.scalars(query)
            ]

    def _verify_checkpoint(self, session, run):
        if session.get(RunRow, run.run_id).checkpoint_digest != self._checkpoint_digest(
            run
        ):
            raise RuntimeFault("CHECKPOINT_INVALID")

    def _verify_pending(self, session, run, approval):
        self._verify_checkpoint(session, run)
        invocation = next(
            (item for item in run.invocations if item.call_id == approval.call_id), None
        )
        if (
            invocation is None
            or invocation.approval_id != approval.approval_id
            or invocation.status != "PENDING"
        ):
            raise RuntimeFault("CHECKPOINT_INVALID")
        bound = {
            "run_id": run.run_id,
            "call_id": invocation.call_id,
            "tool_name": invocation.tool_name,
            "arguments": invocation.validated_args,
        }
        if (
            digest(bound) != approval.args_digest
            or invocation.validated_args != approval.request_payload
        ):
            raise RuntimeFault("CHECKPOINT_INVALID")
        pending = run.model_resume_state.get("pending_calls", [])
        if not pending or pending[0] != {
            "call_id": invocation.call_id,
            "tool_name": invocation.tool_name,
            "arguments": invocation.validated_args,
        }:
            raise RuntimeFault("CHECKPOINT_INVALID")
        return invocation

    def _insert_draft(self, session, run, invocation, approval):
        args = invocation.validated_args
        existing = session.scalar(
            select(PurchaseDraftRow).where(
                PurchaseDraftRow.idempotency_key == invocation.idempotency_key
            )
        )
        if existing is not None:
            if (
                existing.approval_id != approval.approval_id
                or existing.run_id != run.run_id
                or existing.call_id != invocation.call_id
            ):
                raise RuntimeFault("IDEMPOTENCY_CONFLICT")
            return {
                "draft_id": existing.draft_id,
                "total_cents": existing.total_cents,
                "status": "COMPLETED",
            }
        draft_id = str(uuid4())
        session.add(
            PurchaseDraftRow(
                draft_id=draft_id,
                run_id=run.run_id,
                call_id=invocation.call_id,
                approval_id=approval.approval_id,
                idempotency_key=invocation.idempotency_key,
                **args,
                total_cents=args["quantity"] * args["unit_price_cents"],
                created_at=utcnow(),
            )
        )
        session.flush()
        return {
            "draft_id": draft_id,
            "total_cents": args["quantity"] * args["unit_price_cents"],
            "status": "COMPLETED",
        }

    def decide(self, run_id, approval_id, decision, registry, *, request_id=None):
        if decision not in {"approve", "reject"}:
            raise RuntimeFault("INVALID_DECISION")
        with self.transaction() as session:
            approval = session.get(ApprovalRow, approval_id)
            if approval is None or approval.run_id != run_id:
                raise RuntimeFault("APPROVAL_NOT_FOUND")
            run = self._load(session, run_id)
            desired = "APPROVED" if decision == "approve" else "REJECTED"
            if approval.status != "PENDING":
                if approval.status != desired:
                    raise RuntimeFault("APPROVAL_CONFLICT")
                return DecisionResult(run, True, False)
            if run.status != Status.WAITING_APPROVAL:
                raise RuntimeFault("APPROVAL_CONFLICT")
            invocation = self._verify_pending(session, run, approval)
            pending = run.model_resume_state["pending_calls"]
            approval.status, approval.decided_at, approval.request_id = (
                desired,
                utcnow(),
                request_id,
            )
            wait = max(
                0,
                (
                    datetime.fromisoformat(approval.decided_at)
                    - datetime.fromisoformat(approval.created_at)
                ).total_seconds(),
            )
            run.approval_wait_seconds += wait
            approval_step = next(
                s
                for s in run.steps
                if s.kind == "approval" and s.call_id == invocation.call_id
            )
            approval_step.status, approval_step.duration_ms = "COMPLETED", wait * 1000
            step = run.steps[invocation.step_seq - 1]
            run.emit(
                "approval.approved" if decision == "approve" else "approval.rejected",
                approval_id=approval_id,
                args_digest=approval.args_digest,
                request_id=request_id,
            )
            if decision == "reject":
                invocation.status, step.status, step.error_code = (
                    "REJECTED",
                    "CANCELLED",
                    "APPROVAL_REJECTED",
                )
                run.transition(Status.CANCELLED)
                run.stop_reason, run.finished_at = "APPROVAL_REJECTED", utcnow()
                pending.clear()
                run.model_resume_state["safe_point"] = "REJECTED"
                run.emit("run.cancelled", code="APPROVAL_REJECTED")
            else:
                call = ToolCall(
                    call_id=invocation.call_id,
                    tool_name=invocation.tool_name,
                    arguments=invocation.validated_args,
                )
                tool, validated = registry.validate(
                    call,
                    frozenset(run.config_snapshot["allowed_tools"]),
                    for_approval=True,
                )
                if (
                    tool.name != "create_purchase_draft"
                    or tool.permission != Permission.REQUIRES_APPROVAL
                    or validated.model_dump(mode="json") != invocation.validated_args
                ):
                    raise RuntimeFault("TOOL_FORBIDDEN")
                if (
                    run.tool_call_count
                    >= run.config_snapshot["limits"]["max_tool_calls"]
                ):
                    raise RuntimeFault("MAX_TOOL_CALLS")
                if run.active_seconds >= run.config_snapshot["limits"]["wall_seconds"]:
                    raise RuntimeFault("WALL_TIME_LIMIT")
                clock = time.monotonic()
                step.started_at = utcnow()
                run.emit(
                    "tool.started",
                    step_id=invocation.step_seq,
                    call_id=invocation.call_id,
                    tool_name=invocation.tool_name,
                )
                invocation.result = self._insert_draft(
                    session, run, invocation, approval
                )
                invocation.status, step.status = "COMPLETED", "COMPLETED"
                step.duration_ms = (time.monotonic() - clock) * 1000
                step.result_summary = trace_summary(invocation.result)
                run.active_seconds += step.duration_ms / 1000
                run.tool_call_count += 1
                run.model_resume_state["context"].append(
                    ToolResult(
                        call_id=invocation.call_id, result=invocation.result
                    ).model_dump(mode="json")
                )
                pending.pop(0)
                run.model_resume_state["safe_point"] = "AFTER_APPROVED_TOOL"
                run.transition(Status.RUNNING)
                run.stop_reason = None
                run.emit(
                    "tool.completed",
                    step_id=invocation.step_seq,
                    call_id=invocation.call_id,
                    duration_ms=step.duration_ms,
                    result_summary=step.result_summary,
                )
                run.emit("run.checkpointed", safe_point="AFTER_APPROVED_TOOL")
            self._save(session, run)
        return DecisionResult(run, False, decision == "approve")

    def recover(self):
        with self.transaction() as session:
            ids = list(
                session.scalars(
                    select(RunRow.id).where(
                        RunRow.status.in_(["CREATED", "RUNNING", "WAITING_APPROVAL"])
                    )
                )
            )
            for run_id in ids:
                run = self._load(session, run_id)
                if run.status == Status.WAITING_APPROVAL:
                    try:
                        approvals = list(
                            session.scalars(
                                select(ApprovalRow).where(
                                    ApprovalRow.run_id == run_id,
                                    ApprovalRow.status == "PENDING",
                                )
                            )
                        )
                        if len(approvals) != 1:
                            raise RuntimeFault("CHECKPOINT_INVALID")
                        self._verify_pending(session, run, approvals[0])
                        run.emit(
                            "run.checkpoint_restored", safe_point="WAITING_APPROVAL"
                        )
                    except RuntimeFault:
                        run.transition(Status.FAILED)
                        run.stop_reason, run.finished_at = (
                            "CHECKPOINT_INVALID",
                            utcnow(),
                        )
                        run.emit("run.failed", code=run.stop_reason)
                elif run.status == Status.CREATED:
                    run.transition(Status.FAILED)
                    run.stop_reason, run.finished_at = "PROCESS_NOT_STARTED", utcnow()
                    run.emit("run.failed", code=run.stop_reason)
                else:
                    uncertain = any(
                        i.status == "RUNNING"
                        and i.permission == Permission.REQUIRES_APPROVAL.value
                        for i in run.invocations
                    )
                    run.transition(
                        Status.RECONCILIATION_REQUIRED
                        if uncertain
                        else Status.INTERRUPTED
                    )
                    run.stop_reason = (
                        "WRITE_OUTCOME_UNKNOWN" if uncertain else "PROCESS_INTERRUPTED"
                    )
                    for step in run.steps:
                        if step.status == "RUNNING":
                            step.status, step.error_code = "FAILED", run.stop_reason
                    run.emit(
                        "run.reconciliation_required"
                        if uncertain
                        else "run.interrupted",
                        code=run.stop_reason,
                    )
                self._save(session, run)

    def claim_resume(self, run_id):
        with self.transaction() as session:
            run = self._load(session, run_id)
            if (
                run.status != Status.INTERRUPTED
                or run.model_resume_state.get("safe_point") != "AFTER_APPROVED_TOOL"
            ):
                raise RuntimeFault("UNSAFE_RESUME_POINT")
            self._verify_checkpoint(session, run)
            if any(i.status == "RUNNING" for i in run.invocations):
                raise RuntimeFault("UNSAFE_RESUME_POINT")
            invocation = run.invocations[-1] if run.invocations else None
            if (
                invocation is None
                or invocation.permission != Permission.REQUIRES_APPROVAL.value
                or invocation.status != "COMPLETED"
                or not isinstance(invocation.result, dict)
            ):
                raise RuntimeFault("UNSAFE_RESUME_POINT")
            approval = session.get(ApprovalRow, invocation.approval_id)
            receipt = session.scalar(
                select(PurchaseDraftRow).where(
                    PurchaseDraftRow.idempotency_key == invocation.idempotency_key
                )
            )
            context = run.model_resume_state.get("context", [])
            if (
                approval is None
                or approval.status != "APPROVED"
                or receipt is None
                or not context
                or context[-1].get("call_id") != invocation.call_id
                or context[-1].get("result") != invocation.result
                or invocation.result.get("draft_id") != receipt.draft_id
            ):
                raise RuntimeFault("UNSAFE_RESUME_POINT")
            run.transition(Status.RUNNING)
            run.stop_reason = None
            self._save(session, run)
        return run
