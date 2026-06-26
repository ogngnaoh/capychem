"""LangGraph runtime: propose -> validate -> score -> persist -> stop_check.

Nodes are async. State is LoopState (TypedDict); each node returns a partial dict
that LangGraph merges. Every node opens a Langfuse span as a child of the current
generation span (ids threaded through state). The harness is reached only via
oracle.py (subprocess); this module never imports harness code.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from capychem import proposer
from capychem.db.models import Candidate, Generation, OracleCall
from capychem.loop import strategy, trace
from capychem.loop.logic import (
    build_summary,
    merge_and_truncate,
    stop_reason,
)
from capychem.loop.seeds import load_starting_pop as _load_starting_pop
from capychem.loop.state import LoopState, Scored
from capychem.oracle import score_batch_async
from capychem.validate import validate_batch_with_stats
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


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
        if state["gen_index"] == 0:
            raw = [(smi, None) for smi in _load_starting_pop(state["pop_size"])]
            proposer_label = "starting"
        else:
            pop = [(m.smiles, m.score) for m in state["population"]]
            seed = state["seed"] + state["gen_index"]  # per-gen derived seed (G6)
            if state.get("mutation_strategy", "graph_ga") == "llm":
                results = await strategy.propose_llm_async(
                    state["task"], pop, n=state["offspring"], seed=seed
                )
                with trace.span(
                    "llm:propose",
                    trace_id=state.get("run_trace_id"),
                    parent_observation_id=gen_span_id,
                    model=proposer.llm_model(),
                    n=state["offspring"],
                    temperature=strategy.LLM_TEMPERATURE,
                    seed=seed,
                ):
                    pass
                raw = [(r.smiles, None) for r in results]
                proposer_label = "llm"
            else:
                raw = strategy.ga_fill(
                    pop, state["offspring"], mutation_rate=state["mutation_rate"], seed=seed
                )
                proposer_label = "graph_ga"
        return {"proposed": raw, "_proposer": proposer_label, "gen_span_id": gen_span_id}


async def validate(state: LoopState) -> dict[str, Any]:
    with trace.span(
        "node:validate",
        trace_id=state.get("run_trace_id"),
        parent_observation_id=state.get("gen_span_id"),
    ):
        validated, stats = validate_batch_with_stats(state["proposed"])
        proposer_label = state.get("_proposer", "graph_ga")
        validated = [replace(vc, proposer=proposer_label) for vc in validated]
        prev = state.get("_validation_stats", {"proposed": 0, "valid": 0})
        return {
            "validated": validated,
            "_validation_stats": {
                "proposed": prev["proposed"] + stats.proposed,
                "valid": prev["valid"] + stats.valid,
            },
        }


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
        fillers = strategy.fallback_fill(
            validated,
            pop,
            target=state["offspring"],
            mutation_rate=state["mutation_rate"],
            seed=state["seed"] + state["gen_index"],
        )
        if not fillers:
            return {"_fallback_validated": []}
        return {"_fallback_validated": fillers, "_proposer": "mixed"}


async def score(state: LoopState) -> dict[str, Any]:
    with trace.span(
        "node:score",
        trace_id=state.get("run_trace_id"),
        parent_observation_id=state.get("gen_span_id"),
    ):
        candidates = [*state["validated"], *state.get("_fallback_validated", [])]
        buffer = state.get("mol_buffer", set())
        # Cross-generation memoization (slice 05): a molecule a prior generation
        # already scored is a cache hit — not re-scored, not counted, not persisted.
        # The budget counts UNIQUE oracle calls (FR-002), unifying with eval/runner.py.
        unseen = [c for c in candidates if c.smiles not in buffer]
        room = max(state["budget"] - len(buffer), 0)  # remaining unique headroom
        batch = unseen[:room]
        if not batch:
            return {"_scored": [], "calls_used": len(buffer), "mol_buffer": buffer}
        results = await score_batch_async([c.smiles for c in batch], task=state["task"])
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
        }


async def stop_check(state: LoopState) -> dict[str, Any]:
    with trace.span(
        "node:stop_check",
        trace_id=state.get("run_trace_id"),
        parent_observation_id=state.get("gen_span_id"),
    ):
        reason = stop_reason(
            calls_used=state["calls_used"],
            budget=state["budget"],
            gen_index=state["gen_index"] + 1,
            max_generations=state["max_generations"],
            made_progress=state["_made_progress"],
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
            result = {"done": False, "gen_index": state["gen_index"] + 1}
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

    builder: StateGraph[Any, Any, Any, Any] = StateGraph(LoopState)
    builder.add_node("propose", propose)
    builder.add_node("validate", validate)
    builder.add_node("fallback", fallback)
    builder.add_node("score", score)
    builder.add_node("persist", persist)
    builder.add_node("stop_check", stop_check)
    builder.set_entry_point("propose")
    builder.add_edge("propose", "validate")
    builder.add_edge("validate", "fallback")
    builder.add_edge("fallback", "score")
    builder.add_edge("score", "persist")
    builder.add_edge("persist", "stop_check")
    builder.add_conditional_edges("stop_check", _route, {"continue": "propose", "stop": END})
    return builder.compile()
