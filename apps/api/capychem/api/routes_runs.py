"""REST routes for runs: create, snapshot, stop."""

from __future__ import annotations

import base64
import csv
import io
import json
from collections.abc import Mapping
from typing import Any

from capychem import cost
from capychem.api import config
from capychem.api.compare import build_compare_payload
from capychem.api.ga_baseline import graph_ga_baseline
from capychem.api.runner import RunRegistry
from capychem.api.schemas import (
    AnalyzerHypothesisOut,
    ComparePayload,
    CreateRunRequest,
    ObjectiveValidateRequest,
    ObjectiveValidateResponse,
    ObjectiveValidateResult,
    RunListItem,
    RunSnapshot,
)
from capychem.db.models import AnalyzerHypothesis, Candidate, Generation, Run, RunCost
from capychem.mode import derive_mode
from capychem.objective import Objective
from capychem.oracle import OracleResult, score_batch_async
from capychem.run import RunConfig, create_run
from fastapi import APIRouter, Header, HTTPException, Request, Response
from rdkit import Chem
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.requests import HTTPConnection

router = APIRouter()


def _gated_baseline(mode: str, task: str) -> float | None:
    """The G1-contamination gate: a Graph-GA baseline is presentable ONLY for a
    benchmark run. An exploratory run (custom seed/oracle/objective/constraint) has
    no comparable Graph-GA control, so its snapshot never carries one — the single
    rule both the live and DB snapshot paths apply."""
    return graph_ga_baseline(task) if mode == "benchmark" else None


def registry_of(conn: HTTPConnection) -> RunRegistry:
    """App-state accessor shared by the REST routes and the WS endpoint
    (HTTPConnection covers both Request and WebSocket)."""
    reg: RunRegistry = conn.app.state.registry
    return reg


def sessionmaker_of(conn: HTTPConnection) -> async_sessionmaker[AsyncSession]:
    sm: async_sessionmaker[AsyncSession] = conn.app.state.sessionmaker
    return sm


def _db_fields(row: Run) -> tuple[str, float | None, int]:
    """Derive (status, best_score, oracle_calls) for a DB-only run from its
    persisted row + summary_json. The single derivation the list and the
    run-detail endpoint share (the list == detail invariant)."""
    summary = row.summary_json or {}
    top = summary.get("top_k", [])
    best_score = top[0]["score"] if top else None
    return row.status, best_score, summary.get("oracle_calls", 0)


def run_list_item(row: Run, live: dict[str, Any] | None) -> RunListItem:
    """One list row: identity fields always come from the DB row (the live
    snapshot has no started_at); status/best_score/oracle_calls come from the
    registry snapshot when the run is live, else from summary_json."""
    if live is not None:
        status = live["status"]
        best_score = live["best_score"]
        oracle_calls = live["oracle_calls_used"]
    else:
        status, best_score, oracle_calls = _db_fields(row)
    return RunListItem(
        run_id=row.id,
        task=row.task,
        mutation_strategy=row.mutation_strategy,
        mode=row.mode,
        status=status,
        best_score=best_score,
        oracle_calls=oracle_calls,
        budget=row.budget,
        started_at=row.started_at,
    )


_SORT_KEYS = ("started_at", "best_score", "oracle_calls", "status")


def build_run_list(
    rows: list[Run],
    live_by_id: Mapping[int, dict[str, Any] | None],
    *,
    status: str | None,
    task: str | None,
    sort: str,
    order: str,
) -> list[RunListItem]:
    """Merge each row with its live overlay, filter, then sort — all in Python,
    because a live run's best_score/oracle_calls come from the registry, not the
    DB, so a SQL ORDER BY would mis-order live runs."""
    items = [run_list_item(r, live_by_id.get(r.id)) for r in rows]
    if status is not None:
        items = [i for i in items if i.status == status]
    if task is not None:
        items = [i for i in items if i.task == task]

    reverse = order != "asc"
    if sort == "best_score":  # nulls always last, regardless of order
        present = sorted(
            (i for i in items if i.best_score is not None),
            key=lambda i: i.best_score,  # type: ignore[arg-type,return-value]
            reverse=reverse,
        )
        absent = [i for i in items if i.best_score is None]
        return present + absent
    if sort == "oracle_calls":
        return sorted(items, key=lambda i: i.oracle_calls, reverse=reverse)
    if sort == "status":
        return sorted(items, key=lambda i: i.status, reverse=reverse)
    return sorted(items, key=lambda i: i.started_at, reverse=reverse)


# --- GET /runs pagination (m08-05) -------------------------------------------
#
# Keyset (seek), not offset: the cursor encodes the LAST item's run_id from the
# previous page and is resolved by IDENTITY (not array position) in the
# freshly sorted+filtered list. A run inserted anywhere else in the list
# before the next page is fetched never shifts, duplicates, or skips an
# already-issued page -- unlike an offset/limit scheme, which drifts under
# concurrent inserts. ``limit=None`` (the default) returns every item with no
# cursor, byte-identical to the pre-pagination response -- existing clients
# (apps/web) that never pass cursor/limit see unchanged behavior.


def _encode_cursor(run_id: int) -> str:
    return base64.urlsafe_b64encode(json.dumps({"last_id": run_id}).encode()).decode()


def _decode_cursor(raw: str) -> int:
    try:
        data = json.loads(base64.urlsafe_b64decode(raw.encode()).decode())
        return int(data["last_id"])
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Invalid cursor") from exc


def paginate_run_list(
    items: list[RunListItem], *, cursor: str | None, limit: int | None
) -> tuple[list[RunListItem], str | None]:
    """Slice an already sorted+filtered list into one page. Returns (page,
    next_cursor); next_cursor is None once the last page is reached (or
    pagination wasn't requested). If the cursor's run_id is no longer present
    (e.g. the run was deleted between pages), starts over from the top rather
    than erroring."""
    if limit is None:
        return items, None
    start = 0
    if cursor is not None:
        last_id = _decode_cursor(cursor)
        start = next((i + 1 for i, it in enumerate(items) if it.run_id == last_id), 0)
    page = items[start : start + limit]
    has_more = bool(page) and start + limit < len(items)
    return page, (_encode_cursor(page[-1].run_id) if has_more else None)


@router.post("/runs", status_code=201)
async def create_run_endpoint(
    body: CreateRunRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    cfg = RunConfig(
        task=body.task,
        budget=body.budget,
        seed=body.seed,
        pop_size=body.pop_size,
        offspring=body.offspring,
        mutation_rate=body.mutation_rate,
        plateau_window=body.plateau_window,
        max_generations=body.max_generations,
        mutation_strategy=body.mutation_strategy,
        # Operator bring-your-own compounds (07-02). The schema validator already
        # RDKit-checked them and collapsed an empty list to None.
        seed_smiles=body.seed_smiles,
        seed_source="custom" if body.seed_smiles else "default",
        # Composed objective (07-04) + hard constraints (07-04b); the schema validators
        # already checked both are well-formed. Scoring routes through the objective;
        # constraint-failing molecules are dropped at the validity gate.
        objective_json=body.objective_json,
        constraints_json=body.constraints_json,
        # Server-derived, never client-set: a custom seed (07-02), objective (07-04), or
        # constraints (07-04b) forces exploratory; a plain run stays benchmark.
        mode=derive_mode(
            seed_smiles=body.seed_smiles,
            objective_json=body.objective_json,
            constraints_json=body.constraints_json,
        ),
    )
    sm = sessionmaker_of(request)
    # Idempotency-Key (m08-05, SPEC §6.3): a retried POST carrying the SAME key
    # returns the existing run instead of minting a second one. No header ->
    # idempotency_key stays None -> unchanged prior always-enqueue behavior.
    if idempotency_key is not None:
        async with sm() as session:
            existing = await session.scalar(
                select(Run).where(Run.idempotency_key == idempotency_key)
            )
            if existing is not None:
                return {"run_id": existing.id, "status": existing.status}
    # Enqueue only (milestone 08 slice 02): the request handler does not drive
    # the loop itself — a worker's claim_next_run does, out of band. When the
    # inline dev/test worker is enabled, register a pending handle + wake it so
    # a WS/GET that arrives before the claim still finds a live handle (closing
    # the async gap) and the claim happens promptly rather than on the next
    # poll tick.
    async with sm() as session:
        try:
            run_id = await create_run(
                session, cfg, status="queued", idempotency_key=idempotency_key
            )
        except IntegrityError:
            # Lost a race with a concurrent request carrying the SAME key (both
            # passed the pre-check above before either committed): roll back
            # this insert and return the winner's row rather than erroring or
            # minting a second run.
            await session.rollback()
            async with sm() as session2:
                winner = await session2.scalar(
                    select(Run).where(Run.idempotency_key == idempotency_key)
                )
            assert winner is not None, "IntegrityError on idempotency_key implies a winner row"
            return {"run_id": winner.id, "status": winner.status}
    registry = registry_of(request)
    if request.app.state.inline_worker_enabled:
        registry.register_pending(run_id, cfg)
        registry.wake()
    return {"run_id": run_id, "status": "queued"}


@router.post("/objective/validate", response_model=ObjectiveValidateResponse)
async def validate_objective_endpoint(body: ObjectiveValidateRequest) -> ObjectiveValidateResponse:
    """Preview a composed objective (07-04): the single composite [0,1] score per
    probe molecule (None = the objective couldn't score it — invalid or penalized).
    A malformed spec is a 422. PMO terms score via the harness (keep the probe small)."""
    try:
        objective = Objective.from_json(body.spec)
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid objective spec: {exc}") from exc

    async def _pmo_scorer(smis: list[str], task: str) -> list[OracleResult]:
        return await score_batch_async(smis, task)

    results = await objective.evaluate_async(body.smiles, pmo_scorer=_pmo_scorer)
    return ObjectiveValidateResponse(
        aggregator=objective.spec.aggregator,
        n_terms=len(objective.spec.terms),
        results=[
            ObjectiveValidateResult(smiles=s, score=r.score)
            for s, r in zip(body.smiles, results, strict=True)
        ],
    )


@router.get("/runs", response_model=list[RunListItem])
async def list_runs_endpoint(
    request: Request,
    response: Response,
    status: str | None = None,
    task: str | None = None,
    sort: str = "started_at",
    order: str = "desc",
    cursor: str | None = None,
    limit: int | None = None,
) -> list[RunListItem]:
    if sort not in _SORT_KEYS:
        raise HTTPException(status_code=422, detail=f"sort must be one of {_SORT_KEYS}")
    if order not in ("asc", "desc"):
        raise HTTPException(status_code=422, detail="order must be 'asc' or 'desc'")
    if limit is not None and limit <= 0:
        raise HTTPException(status_code=422, detail="limit must be positive")
    sm = sessionmaker_of(request)
    registry = registry_of(request)
    async with sm() as session:
        rows = list((await session.execute(select(Run))).scalars().all())
    live_by_id = {row.id: registry.snapshot(row.id) for row in rows}
    items = build_run_list(rows, live_by_id, status=status, task=task, sort=sort, order=order)
    # Pagination is opt-in (m08-05): no cursor/limit -> the full list, no header,
    # byte-identical to the pre-pagination response (apps/web never sends these).
    page, next_cursor = paginate_run_list(items, cursor=cursor, limit=limit)
    if next_cursor is not None:
        response.headers["X-Next-Cursor"] = next_cursor
    return page


async def _hypotheses_for(session: AsyncSession, run_id: int) -> list[AnalyzerHypothesisOut]:
    rows = (
        (
            await session.execute(
                select(AnalyzerHypothesis)
                .where(AnalyzerHypothesis.run_id == run_id)
                .order_by(AnalyzerHypothesis.after_generation_index)
            )
        )
        .scalars()
        .all()
    )
    return [
        AnalyzerHypothesisOut(
            after_generation_index=r.after_generation_index,
            text=r.text,
            structured_json=r.structured_json,
        )
        for r in rows
    ]


async def _run_cost_breakdown(
    session: AsyncSession, run_id: int
) -> tuple[float | None, float | None]:
    """(llm_cost_usd, oracle_cost_usd) from the run's RunCost row, or (None, None)
    if it has none yet — the read counterpart to cost.record_oracle_cost, kept
    local to the API layer (packages/core.cost only exposes the summed total)."""
    row = await session.scalar(select(RunCost).where(RunCost.run_id == run_id))
    if row is None:
        return None, None
    return row.llm_cost_usd, row.oracle_cost_usd


async def _run_snapshot(
    session: AsyncSession, registry: RunRegistry, run_id: int
) -> RunSnapshot | None:
    """Build a run's snapshot the single way detail and compare share: the live
    registry snapshot when present, else the persisted DB row (None if unknown —
    the 404 source for both endpoints).

    The DB path covers runs not in the registry (e.g. after a restart) AND a live
    run before its first generation boundary (snapshot stays None until the first
    generation.complete). summary_json comes from build_summary: top_k is
    [{smiles, score}] and auc_curve is [{oracle_calls, top10_mean}] — both match
    the schema dicts. It reads RunCost so completed runs surface real cost
    (FR-013), not the 0.0 default; the live snapshot already carries cost.

    graph_ga_baseline and the llm/oracle cost breakdown are read the same way for
    both the live and DB paths (they don't come from the in-memory snapshot dict);
    valid_smiles_rate only ever comes from a persisted summary_json, so it stays
    null on the live path (matches RunSnapshot's default)."""
    hyps = await _hypotheses_for(session, run_id)
    llm_cost_usd, oracle_cost_usd = await _run_cost_breakdown(session, run_id)
    live = registry.snapshot(run_id)
    if live is not None:
        return RunSnapshot(
            **live,
            hypotheses=hyps,
            # G1-contamination guard (07-01): an exploratory run never presents a
            # Graph-GA baseline, so its snapshot can never render a "beat". mode is
            # carried in the live dict (**live) itself.
            graph_ga_baseline=_gated_baseline(live["mode"], live["task"]),
            llm_cost_usd=llm_cost_usd,
            oracle_cost_usd=oracle_cost_usd,
        )
    row = await session.get(Run, run_id)
    if row is None:
        return None
    summary = row.summary_json or {}
    status, best_score, oracle_calls = _db_fields(row)  # shared with the list view
    return RunSnapshot(
        run_id=row.id,
        task=row.task,
        mode=row.mode,
        status=status,
        budget=row.budget,
        plateau_window=row.plateau_window,
        generation_index=summary.get("generations", 0),
        oracle_calls_used=oracle_calls,
        best_score=best_score,
        top_k=summary.get("top_k", []),
        auc_curve=summary.get("auc_curve", []),
        cost_so_far_usd=await cost.run_cost_total(session, run_id),
        hypotheses=hyps,
        trace_url=config.trace_url(summary.get("trace_id")),
        valid_smiles_rate=(summary.get("valid_smiles") or {}).get("rate"),
        graph_ga_baseline=_gated_baseline(row.mode, row.task),
        llm_cost_usd=llm_cost_usd,
        oracle_cost_usd=oracle_cost_usd,
        diversity=summary.get("diversity"),  # 07-08 trust metrics from summary_json
        novelty=summary.get("novelty"),
    )


@router.get("/runs/{run_id}", response_model=RunSnapshot)
async def get_run_endpoint(run_id: int, request: Request) -> RunSnapshot:
    sm = sessionmaker_of(request)
    registry = registry_of(request)
    async with sm() as session:
        snap = await _run_snapshot(session, registry, run_id)
    if snap is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return snap


@router.get("/runs/{run_id}/manifest")
async def get_manifest_endpoint(run_id: int, request: Request) -> dict[str, Any]:
    """The run's reproducibility manifest (07-06, OD-5): git SHA + model id + PyTDC pin
    + config + trace URL. 404 if the run is unknown; an empty object while the run is
    still live (the manifest is written at finalize)."""
    sm = sessionmaker_of(request)
    async with sm() as session:
        row = await session.get(Run, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return row.manifest_json or {}


# Lineage export (07-07). Column order: identity/lineage first, then the 07-05 quality
# fields flattened out of quality_json.
_QUALITY_COLS = (
    "valid",
    "sa_score",
    "qed",
    "mw",
    "logp",
    "hbd",
    "hba",
    "rotatable_bonds",
    "tpsa",
    "lipinski_pass",
    "veber_pass",
    "pains",
    "brenk",
)
_LINEAGE_COLS = (
    "candidate_id",
    "generation",
    "parent_candidate_id",
    "proposer",
    "smiles",
    "score",
    "hypothesis_at_birth",
    *_QUALITY_COLS,
)


async def _lineage_rows(session: AsyncSession, run_id: int) -> list[dict[str, Any]]:
    """Full per-candidate lineage for a run: gen index + parent + proposer + score +
    the hypothesis that conditioned its generation + the flattened quality report."""
    result = await session.execute(
        select(Candidate, Generation.index)
        .join(Generation, Candidate.generation_id == Generation.id)
        .where(Generation.run_id == run_id)
        .order_by(Generation.index, Candidate.id)
    )
    hyps = {
        h.after_generation_index: h.text
        for h in (
            await session.execute(
                select(AnalyzerHypothesis).where(AnalyzerHypothesis.run_id == run_id)
            )
        )
        .scalars()
        .all()
    }
    rows: list[dict[str, Any]] = []
    for cand, gen_index in result.all():
        quality = cand.quality_json or {}
        row: dict[str, Any] = {
            "candidate_id": cand.id,
            "generation": gen_index,
            "parent_candidate_id": cand.parent_candidate_id,
            "proposer": cand.proposer,
            "smiles": cand.smiles,
            "score": cand.score,
            # The analyzer hypothesis after gen N conditions gen N+1's proposals, so a
            # candidate in generation g was born under the hypothesis after gen g-1.
            "hypothesis_at_birth": hyps.get(gen_index - 1),
        }
        for col in _QUALITY_COLS:
            row[col] = quality.get(col)
        rows.append(row)
    return rows


async def _run_or_404(session: AsyncSession, run_id: int) -> Run:
    row = await session.get(Run, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return row


@router.get("/runs/{run_id}/export.csv")
async def export_csv_endpoint(run_id: int, request: Request) -> Response:
    """Full lineage as CSV (07-07): one row per candidate, lineage + quality columns."""
    sm = sessionmaker_of(request)
    async with sm() as session:
        await _run_or_404(session, run_id)
        rows = await _lineage_rows(session, run_id)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(_LINEAGE_COLS))
    writer.writeheader()
    writer.writerows(rows)
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="run-{run_id}-lineage.csv"'},
    )


@router.get("/runs/{run_id}/export.sdf")
async def export_sdf_endpoint(run_id: int, request: Request) -> Response:
    """Full lineage as an SDF (07-07): one record per candidate with the lineage +
    quality attached as properties. RDKit round-trips it (SDMolSupplier re-reads it)."""
    sm = sessionmaker_of(request)
    async with sm() as session:
        row = await _run_or_404(session, run_id)
        rows = await _lineage_rows(session, run_id)
    buf = io.StringIO()
    writer = Chem.SDWriter(buf)
    # First-record provenance so the file is self-describing (manifest pin, if finalized).
    manifest = row.manifest_json or {}
    for r in rows:
        mol = Chem.MolFromSmiles(r["smiles"])
        if mol is None:  # a persisted candidate is RDKit-valid, but stay defensive
            continue
        mol.SetProp("_Name", f"cand-{r['candidate_id']}")
        for key, value in r.items():
            if value is not None:
                mol.SetProp(key, str(value))
        if manifest.get("pytdc_version"):
            mol.SetProp("pytdc_version", str(manifest["pytdc_version"]))
        if manifest.get("git_sha"):
            mol.SetProp("git_sha", str(manifest["git_sha"]))
        writer.write(mol)
    writer.flush()  # emit the trailing $$$$ WITHOUT closing (close() would close buf)
    return Response(
        content=buf.getvalue(),
        media_type="chemical/x-mdl-sdfile",
        headers={"Content-Disposition": f'attachment; filename="run-{run_id}-lineage.sdf"'},
    )


@router.get("/trace/{run_id}")
async def get_trace_endpoint(run_id: int, request: Request) -> dict[str, str | None]:
    """Langfuse deep link for a run (FR-014 / SPEC §6.3). 404 if the run is
    unknown; ``trace_url`` is null when the run has no persisted trace id or
    LANGFUSE_PROJECT_ID is unconfigured (the UI hides the link, never shows a
    broken one)."""
    sm = sessionmaker_of(request)
    async with sm() as session:
        row = await session.get(Run, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    summary = row.summary_json or {}
    return {"trace_url": config.trace_url(summary.get("trace_id"))}


@router.get("/compare", response_model=ComparePayload)
async def compare_runs_endpoint(request: Request, a: int, b: int) -> ComparePayload:
    """Read-only aggregation of two existing runs (FR-012/013). 404 if either is
    unknown. The two AUC curves are resampled onto a common oracle-call x-axis so
    they overlay-compare (SPEC §6.4d)."""
    sm = sessionmaker_of(request)
    registry = registry_of(request)
    async with sm() as session:
        snap_a = await _run_snapshot(session, registry, a)
        snap_b = await _run_snapshot(session, registry, b)
    if snap_a is None:
        raise HTTPException(status_code=404, detail=f"Run {a} not found")
    if snap_b is None:
        raise HTTPException(status_code=404, detail=f"Run {b} not found")
    return build_compare_payload(snap_a, snap_b)


@router.post("/runs/{run_id}/resume")
async def resume_run_endpoint(run_id: int, request: Request) -> dict[str, Any]:
    """Continue a paused run from its persisted progress (06-07). 404 if the run
    is unknown, 409 if it isn't paused (nothing to resume — the caller should
    check status first, e.g. via GET /runs/{id})."""
    sm = sessionmaker_of(request)
    async with sm() as session:
        row = await session.get(Run, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    if row.status != "paused":
        raise HTTPException(
            status_code=409, detail=f"Run {run_id} is not paused (status={row.status!r})"
        )
    try:
        status = await registry_of(request).resume_run(run_id)
    except ValueError as exc:
        # A concurrent resume already claimed this run (TOCTOU past the check above),
        # or its status changed. Refuse rather than spawn a second driver.
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    # `status` is "running" for a normal resume, or a terminal reason when the run
    # had already finished before it was interrupted (finalized without driving).
    return {"run_id": run_id, "status": status}


@router.post("/runs/{run_id}/stop")
async def stop_run_endpoint(run_id: int, request: Request) -> dict[str, Any]:
    ok = await registry_of(request).stop_run(run_id)
    if not ok:
        # Unknown run or already terminal — idempotent no-op if the row exists;
        # report the row's real status rather than claiming "stopping".
        sm = sessionmaker_of(request)
        async with sm() as session:
            row = await session.get(Run, run_id)
            if row is None:
                raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
            return {"run_id": run_id, "status": row.status}
    return {"run_id": run_id, "status": "stopping"}
