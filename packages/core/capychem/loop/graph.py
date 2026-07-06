"""LangGraph runtime: propose -> validate -> score -> persist -> stop_check.

Nodes are async. State is LoopState (TypedDict); each node returns a partial dict
that LangGraph merges. Every node opens a Langfuse span as a child of the current
generation span (ids threaded through state). The harness is reached only via
oracle.py (subprocess); this module never imports harness code.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from dataclasses import replace
from typing import Any, cast

from capychem import proposer
from capychem.constraints import Constraints
from capychem.db.models import AnalyzerHypothesis, Candidate, Generation, OracleCall
from capychem.loop import strategy, trace
from capychem.loop.logic import (
    build_analyzer_summary,
    build_summary,
    merge_and_truncate,
    stop_reason,
)
from capychem.loop.seeds import build_seed_population
from capychem.loop.seeds import load_starting_pop as _load_starting_pop
from capychem.loop.state import HypothesisRecord, LoopState, Scored
from capychem.objective import Objective
from capychem.oracle import HarnessError, OracleResult, score_batch_async
from capychem.quality import molecule_quality
from capychem.validate import validate_batch_with_stats
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# Bounded retry for a transient harness-subprocess blip (a timeout, a flaky spawn).
# Absorbs the blip without pausing the run; a sustained outage still exhausts the
# retry budget and re-raises, which apps/api/capychem/api/runner.py `_drive` catches
# to pause the run in a recoverable state (PRD edge case 2). Covers BOTH harness
# subprocess paths — scoring (score_batch_async) AND Graph-GA offspring/fallback
# (propose_offspring via strategy.ga_fill/fallback_fill) — all raise HarnessError.
_HARNESS_RETRY_ATTEMPTS = 3
_HARNESS_RETRY_BACKOFF_S = (0.5, 1.0)


async def propose(state: LoopState) -> dict[str, Any]:
    # Open the generation-level span first (the generation boundary's start), then
    # nest this node's span under it. gen_span_id is threaded forward in the return.
    gen_span_id = trace.gen_span(
        state.get("run_trace_id"),
        state["run_id"],
        state["gen_index"],
        calls_used=state["calls_used"],
    )
    with trace.span(
        "node:propose",
        trace_id=state.get("run_trace_id"),
        parent_observation_id=gen_span_id,
    ):
        raw: list[tuple[str, tuple[int, int] | None]]
        gen_llm_cost = 0.0
        if state["gen_index"] == 0:
            # Operator bring-your-own compounds (07-02) override the shipped pool;
            # build_seed_population canonicalizes + tops up/truncates to pop_size.
            operator_seeds = state.get("seed_smiles")
            if operator_seeds:
                pop_smis = build_seed_population(operator_seeds, state["pop_size"])
            else:
                pop_smis = _load_starting_pop(state["pop_size"])
            raw = [(smi, None) for smi in pop_smis]
            proposer_label = "starting"
        else:
            pop = [(m.smiles, m.score) for m in state["population"]]
            seed = state["seed"] + state["gen_index"]  # per-gen derived seed (G6)
            if state.get("mutation_strategy", "graph_ga") == "llm":
                with trace.span(
                    "llm:propose",
                    trace_id=state.get("run_trace_id"),
                    parent_observation_id=gen_span_id,
                    model=proposer.llm_model(),
                    n=state["offspring"],
                    temperature=strategy.LLM_TEMPERATURE,
                    seed=seed,
                ) as llm_span_id:
                    results = await strategy.propose_llm_async(
                        state["task"],
                        pop,
                        n=state["offspring"],
                        seed=seed,
                        hypothesis=state.get("analyzer_hypothesis"),
                    )
                    gen_llm_cost = sum(r.cost_usd for r in results)
                    trace.update_span(
                        llm_span_id,
                        tokens_in=sum(r.tokens_in for r in results),
                        tokens_out=sum(r.tokens_out for r in results),
                        cost_usd=gen_llm_cost,
                    )
                raw = [(r.smiles, None) for r in results]
                proposer_label = "llm"
            else:
                raw = await _with_harness_retry(
                    lambda: strategy.ga_fill(
                        pop, state["offspring"], mutation_rate=state["mutation_rate"], seed=seed
                    )
                )
                proposer_label = "graph_ga"
        result: dict[str, Any] = {
            "proposed": raw,
            "_proposer": proposer_label,
            "gen_span_id": gen_span_id,
        }
        if proposer_label == "llm":
            result["llm_cost_usd"] = state.get("llm_cost_usd", 0.0) + gen_llm_cost
        return result


async def validate(state: LoopState) -> dict[str, Any]:
    with trace.span(
        "node:validate",
        trace_id=state.get("run_trace_id"),
        parent_observation_id=state.get("gen_span_id"),
    ):
        validated, stats = validate_batch_with_stats(state["proposed"])
        proposer_label = state.get("_proposer", "graph_ga")
        validated = [replace(vc, proposer=proposer_label) for vc in validated]
        out: dict[str, Any] = {"validated": validated}
        # Gate purity (slice 06): the >80% valid-SMILES gate measures the LLM
        # proposer only. Gen-0 "starting" seeds and graph_ga batches are excluded;
        # graph_ga fallback fills never reach this node (they enter via `fallback`).
        if proposer_label == "llm":
            prev = state.get("_validation_stats", {"proposed": 0, "valid": 0})
            out["_validation_stats"] = {
                "proposed": prev["proposed"] + stats.proposed,
                "valid": prev["valid"] + stats.valid,
            }
        return out


async def fallback(state: LoopState) -> dict[str, Any]:
    with trace.span(
        "node:fallback",
        trace_id=state.get("run_trace_id"),
        parent_observation_id=state.get("gen_span_id"),
    ):
        if state.get("_proposer") != "llm":
            return {"_fallback_validated": []}
        validated = state["validated"]
        pop = [(m.smiles, m.score) for m in state["population"]]
        fillers = await _with_harness_retry(
            lambda: strategy.fallback_fill(
                validated,
                pop,
                target=state["offspring"],
                mutation_rate=state["mutation_rate"],
                seed=state["seed"] + state["gen_index"],
            )
        )
        if not fillers:
            return {"_fallback_validated": []}
        return {"_fallback_validated": fillers, "_proposer": "mixed"}


async def _with_harness_retry(call: Callable[[], Any]) -> Any:
    """Run a harness-subprocess call, retrying a transient HarnessError up to
    _HARNESS_RETRY_ATTEMPTS times with a short backoff between attempts, then
    re-raising the last HarnessError once the budget is exhausted (a sustained
    outage still surfaces, so the caller doesn't spin without progress).

    ``call`` is a zero-arg thunk. It may be synchronous (strategy.ga_fill /
    fallback_fill run the Graph-GA subprocess inline) or return an awaitable
    (score_batch_async); either way the HarnessError is caught and retried. The
    inline backoff is async so it never blocks the event loop."""
    last_exc: HarnessError | None = None
    for attempt in range(_HARNESS_RETRY_ATTEMPTS):
        try:
            result = call()
            if inspect.isawaitable(result):
                result = await result
            return result
        except HarnessError as exc:
            last_exc = exc
            if attempt < _HARNESS_RETRY_ATTEMPTS - 1:
                await asyncio.sleep(_HARNESS_RETRY_BACKOFF_S[attempt])
    assert last_exc is not None
    raise last_exc


async def score(state: LoopState) -> dict[str, Any]:
    with trace.span(
        "node:score",
        trace_id=state.get("run_trace_id"),
        parent_observation_id=state.get("gen_span_id"),
    ):
        candidates = [*state["validated"], *state.get("_fallback_validated", [])]
        # Hard constraints (07-04b): a constraint-failing candidate is treated like an
        # invalid one — dropped before scoring, so no budget is spent on it. A generation
        # whose candidates ALL fail the constraints is "starved" (a signal distinct from
        # plateau/no_progress; stop_check accumulates it). No constraints -> byte-identical.
        starved = False
        constraints_json = state.get("constraints_json")
        if constraints_json:
            constraints = Constraints.from_json(constraints_json)
            passing = [c for c in candidates if constraints.passes(c.smiles)]
            starved = bool(candidates) and not passing
            candidates = passing
        buffer = state.get("mol_buffer", set())
        # Cross-generation memoization (slice 05): a molecule a prior generation
        # already scored is a cache hit — not re-scored, not counted, not persisted.
        # The budget counts UNIQUE oracle calls (FR-002), unifying with eval/runner.py.
        unseen = [c for c in candidates if c.smiles not in buffer]
        room = max(state["budget"] - len(buffer), 0)  # remaining unique headroom
        batch = unseen[:room]
        if not batch:
            return {
                "_scored": [],
                "calls_used": len(buffer),
                "mol_buffer": buffer,
                "_constraint_starved": starved,
            }
        smis = [c.smiles for c in batch]
        obj_json = state.get("objective_json")
        scored: list[tuple[Any, float, float]]
        if obj_json:
            # Composed exploratory objective (07-04): PMO terms reuse the SAME
            # retry-wrapped harness path below, so cost/backend are preserved; the
            # budget still counts one call per unique candidate (OD-2), not per term.
            async def _pmo_scorer(s: list[str], task: str) -> list[OracleResult]:
                return cast(
                    "list[OracleResult]",
                    await _with_harness_retry(lambda: score_batch_async(s, task=task)),
                )

            obj_results = await Objective.from_json(obj_json).evaluate_async(
                smis, pmo_scorer=_pmo_scorer
            )
            scored = [
                (c, r.score, r.cost_usd)
                for c, r in zip(batch, obj_results, strict=True)
                if r.score is not None
            ]
        else:
            # Benchmark path — unchanged, byte-identical.
            results = await _with_harness_retry(lambda: score_batch_async(smis, task=state["task"]))
            scored = [
                (c, r.score, r.cost_usd)
                for c, r in zip(batch, results, strict=True)
                if r.valid and r.score is not None
            ]
        new_buffer = buffer | {c.smiles for c, _, _ in scored}
        return {
            "_scored": scored,
            "calls_used": len(new_buffer),
            "mol_buffer": new_buffer,
            "_constraint_starved": starved,
        }


async def _persist(
    state: LoopState, sessionmaker: async_sessionmaker[AsyncSession]
) -> dict[str, Any]:
    with trace.span(
        "node:persist",
        trace_id=state.get("run_trace_id"),
        parent_observation_id=state.get("gen_span_id"),
    ):
        scored = state["_scored"]
        async with sessionmaker() as session:
            gen = Generation(
                run_id=state["run_id"],
                index=state["gen_index"],
                proposer_used=state["_proposer"],
            )
            session.add(gen)
            await session.flush()  # gen.id

            pop = state["population"]
            new_scored: list[Scored] = []
            for vc, sc, cost in scored:
                parent_cid = None
                if vc.parents is not None and pop:
                    parent_idx = vc.parents[0]
                    if 0 <= parent_idx < len(pop):
                        parent_cid = pop[parent_idx].candidate_id
                cand = Candidate(
                    generation_id=gen.id,
                    smiles=vc.smiles,
                    parent_candidate_id=parent_cid,
                    proposer=vc.proposer,
                    valid=True,
                    score=sc,
                    quality_json=molecule_quality(vc.smiles),  # annotate-only (07-05)
                )
                session.add(cand)
                await session.flush()  # cand.id
                session.add(
                    OracleCall(
                        run_id=state["run_id"],
                        candidate_id=cand.id,
                        task=state["task"],
                        score=sc,
                        wall_ms=0,
                        compute_cost_usd=cost,
                    )
                )
                new_scored.append(Scored(smiles=vc.smiles, score=sc, candidate_id=cand.id))
            await session.commit()

        survivors = merge_and_truncate(pop, new_scored, pop_size=state["pop_size"])
        top10 = sorted(survivors, key=lambda m: (-m.score, m.smiles))[:10]
        top10_mean = sum(m.score for m in top10) / len(top10) if top10 else 0.0
        curve = [*state.get("auc_curve", []), (state["calls_used"], top10_mean)]
        return {
            "population": survivors,
            "auc_curve": curve,
            "_made_progress": bool(new_scored),
            "gen_db_id": gen.id,
        }


async def _analyze(
    state: LoopState, sessionmaker: async_sessionmaker[AsyncSession]
) -> dict[str, Any]:
    # The differentiator (SPEC §6.4b). Runs only for an LLM run after gen >=1
    # (gen 0 is the seed population; graph_ga has no hypothesis consumer). No-op
    # otherwise — mirrors how `fallback` no-ops for non-llm strategies.
    if state.get("mutation_strategy") != "llm" or state["gen_index"] < 1:
        return {}
    with trace.span(
        "node:analyze",
        trace_id=state.get("run_trace_id"),
        parent_observation_id=state.get("gen_span_id"),
    ):
        prior = state.get("analyzer_hypothesis")
        score_history = [v for _, v in state.get("auc_curve", [])]
        summary = build_analyzer_summary(state["population"], score_history, prior)
        seed = state["seed"] + state["gen_index"]
        with trace.span(
            "llm:analyze",
            trace_id=state.get("run_trace_id"),
            parent_observation_id=state.get("gen_span_id"),
            model=proposer.llm_model(),
            seed=seed,
        ) as llm_span_id:
            result = await strategy.run_analyzer_async(summary, seed=seed)
            trace.update_span(
                llm_span_id,
                tokens_in=result.tokens_in,
                tokens_out=result.tokens_out,
                cost_usd=result.cost_usd,
            )
        # Effective hypothesis: the new one, else last-good, else neutral — the loop
        # never stalls on malformed/empty/off-topic output (FR-007, edge case 3).
        effective = strategy.resolve_effective_hypothesis(result, prior)
        async with sessionmaker() as session:
            hyp = AnalyzerHypothesis(
                run_id=state["run_id"],
                after_generation_index=state["gen_index"],
                text=effective.text,
                structured_json=effective.structured,
                tokens_in=result.tokens_in,
                tokens_out=result.tokens_out,
                compute_cost_usd=result.cost_usd,
            )
            session.add(hyp)
            await session.flush()  # hyp.id
            gen = await session.get(Generation, state["gen_db_id"])
            if gen is not None:
                gen.analyzer_hypothesis_id = hyp.id
            await session.commit()
        record: HypothesisRecord = {
            "after_generation_index": state["gen_index"],
            "text": effective.text,
            "structured_json": effective.structured,
        }
        return {
            "analyzer_hypothesis": effective,
            "analyzer_hypotheses": [*state.get("analyzer_hypotheses", []), record],
            "llm_cost_usd": state.get("llm_cost_usd", 0.0) + result.cost_usd,
        }


async def stop_check(state: LoopState) -> dict[str, Any]:
    with trace.span(
        "node:stop_check",
        trace_id=state.get("run_trace_id"),
        parent_observation_id=state.get("gen_span_id"),
    ):
        # Constraint-starvation streak (07-04b): +1 for a starved generation, reset to
        # 0 otherwise. A sustained streak terminates as constraint_starved; a single
        # starved gen never fires no_progress (stop_reason handles the distinction).
        starved_streak = (
            state.get("constraint_starved_streak", 0) + 1 if state.get("_constraint_starved") else 0
        )
        reason = stop_reason(
            calls_used=state["calls_used"],
            budget=state["budget"],
            gen_index=state["gen_index"] + 1,
            max_generations=state["max_generations"],
            made_progress=state["_made_progress"],
            top10_history=[v for _, v in state.get("auc_curve", [])],
            plateau_window=state["plateau_window"],
            constraint_starved_streak=starved_streak,
        )
        result: dict[str, Any]
        if reason is not None:
            summary = build_summary(
                state["population"],
                state.get("auc_curve", []),
                generations=state["gen_index"] + 1,
                oracle_calls=state["calls_used"],
                validation_stats=state.get("_validation_stats"),
            )
            result = {"done": True, "stop_reason": reason, "summary": summary}
        else:
            result = {
                "done": False,
                "gen_index": state["gen_index"] + 1,
                "constraint_starved_streak": starved_streak,
            }
    # End this generation's span at the generation boundary (after the node span
    # closes, before the next generation's propose opens a new gen span).
    trace.end_gen_span(state["run_id"], state["gen_index"])
    return result


def _route(state: LoopState) -> str:
    return "stop" if state.get("done") else "continue"


def build_graph(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> CompiledStateGraph[Any, Any, Any, Any]:
    """Compile the loop graph. ``sessionmaker`` is captured by the persist node."""

    async def persist(state: LoopState) -> dict[str, Any]:
        return await _persist(state, sessionmaker)

    async def analyze(state: LoopState) -> dict[str, Any]:
        return await _analyze(state, sessionmaker)

    builder: StateGraph[Any, Any, Any, Any] = StateGraph(LoopState)
    builder.add_node("propose", propose)
    builder.add_node("validate", validate)
    builder.add_node("fallback", fallback)
    builder.add_node("score", score)
    builder.add_node("persist", persist)
    builder.add_node("analyze", analyze)
    builder.add_node("stop_check", stop_check)
    builder.set_entry_point("propose")
    builder.add_edge("propose", "validate")
    builder.add_edge("validate", "fallback")
    builder.add_edge("fallback", "score")
    builder.add_edge("score", "persist")
    builder.add_edge("persist", "analyze")
    builder.add_edge("analyze", "stop_check")
    builder.add_conditional_edges("stop_check", _route, {"continue": "propose", "stop": END})
    return builder.compile()
