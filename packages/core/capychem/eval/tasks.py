"""Canonical PMO task registry — the single source of truth for the 23-task surface.

Names are the exact PyTDC oracle names (``Oracle(name=task)``), in NeurIPS 2022 PMO
Table 2 row order. Order is cosmetic (UI dropdown + sweep-row order only). Source:
agent_docs/pmo-auc-and-baselines.md. Every score these tasks produce is an in-silico
oracle score (PRD N6).
"""

from __future__ import annotations

PMO_TASKS: tuple[str, ...] = (
    "qed",
    "zaleplon_mpo",
    "perindopril_mpo",
    "celecoxib_rediscovery",
    "troglitazone_rediscovery",
    "drd2",
    "jnk3",
    "gsk3b",
    "albuterol_similarity",
    "amlodipine_mpo",
    "deco_hop",
    "fexofenadine_mpo",
    "isomers_c7h8n2o2",
    "isomers_c9h10n2o2pf2cl",
    "median1",
    "median2",
    "mestranol_similarity",
    "osimertinib_mpo",
    "ranolazine_mpo",
    "scaffold_hop",
    "sitagliptin_mpo",
    "thiothixene_rediscovery",
    "valsartan_smarts",
)
