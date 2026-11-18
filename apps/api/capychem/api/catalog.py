"""Catalog of the 23 PMO benchmark objectives, grouped in plain language.

Single source of truth for GET /catalog and the deterministic matcher behind
POST /intent/resolve (capychem.api.intent). Canonical names + membership come from
capychem.eval.tasks.PMO_TASKS. Descriptions and aliases provide plain-language
phrases the intent resolver keys on -- kept conservative (no invented pharmacology
beyond the PMO task's own published intent).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from capychem.eval.tasks import PMO_TASKS


@dataclass(frozen=True)
class TaskInfo:
    name: str
    group: str
    description: str
    aliases: tuple[str, ...] = ()


_DRUG_LIKENESS = "Drug-likeness"
_TARGET_ACTIVITY = "Target activity"
_REDISCOVERY = "Rediscovery & similarity"
_MULTI_PROPERTY = "Multi-property & composite (MPO)"

GROUP_ORDER: tuple[str, ...] = (
    _DRUG_LIKENESS,
    _TARGET_ACTIVITY,
    _REDISCOVERY,
    _MULTI_PROPERTY,
)

TASKS: tuple[TaskInfo, ...] = (
    TaskInfo(
        name="qed",
        group=_DRUG_LIKENESS,
        description="Overall drug-likeness — balances size, polarity, and complexity.",
        aliases=("drug-likeness", "drug like", "druglike", "qed", "lipinski"),
    ),
    TaskInfo(
        name="drd2",
        group=_TARGET_ACTIVITY,
        description="Predicted activity against the dopamine D2 receptor.",
        aliases=("dopamine d2", "d2 receptor", "drd2", "dopamine receptor"),
    ),
    TaskInfo(
        name="jnk3",
        group=_TARGET_ACTIVITY,
        description="Predicted activity against the JNK3 kinase.",
        aliases=("jnk3", "jnk-3", "jnk 3 kinase", "c-jun n-terminal kinase 3"),
    ),
    TaskInfo(
        name="gsk3b",
        group=_TARGET_ACTIVITY,
        description="Predicted activity against the GSK-3β kinase.",
        aliases=("gsk3b", "gsk-3b", "gsk3 beta", "gsk-3 beta", "glycogen synthase kinase"),
    ),
    TaskInfo(
        name="celecoxib_rediscovery",
        group=_REDISCOVERY,
        description="How closely a molecule recovers celecoxib.",
        aliases=("celecoxib", "rediscover celecoxib", "recover celecoxib"),
    ),
    TaskInfo(
        name="troglitazone_rediscovery",
        group=_REDISCOVERY,
        description="How closely a molecule recovers troglitazone.",
        aliases=("troglitazone", "rediscover troglitazone", "recover troglitazone"),
    ),
    TaskInfo(
        name="thiothixene_rediscovery",
        group=_REDISCOVERY,
        description="How closely a molecule recovers thiothixene.",
        aliases=("thiothixene", "rediscover thiothixene", "recover thiothixene"),
    ),
    TaskInfo(
        name="albuterol_similarity",
        group=_REDISCOVERY,
        description="Structural similarity to albuterol.",
        aliases=("albuterol", "salbutamol", "similar to albuterol"),
    ),
    TaskInfo(
        name="mestranol_similarity",
        group=_REDISCOVERY,
        description="Structural similarity to mestranol.",
        aliases=("mestranol", "similar to mestranol"),
    ),
    TaskInfo(
        name="deco_hop",
        group=_REDISCOVERY,
        description="Keep the core; vary the decorations (R-groups).",
        aliases=("decoration hop", "deco hop", "r-group hopping", "vary the decorations"),
    ),
    TaskInfo(
        name="scaffold_hop",
        group=_REDISCOVERY,
        description="Keep the decorations; swap the core scaffold.",
        aliases=("scaffold hop", "swap the scaffold", "core hopping", "bioisostere scaffold"),
    ),
    TaskInfo(
        name="zaleplon_mpo",
        group=_MULTI_PROPERTY,
        description="Zaleplon-like profile across several properties.",
        aliases=("zaleplon", "zaleplon-like", "sleep aid zaleplon"),
    ),
    TaskInfo(
        name="perindopril_mpo",
        group=_MULTI_PROPERTY,
        description="Perindopril-like profile across several properties.",
        aliases=("perindopril", "perindopril-like", "ace inhibitor perindopril"),
    ),
    TaskInfo(
        name="amlodipine_mpo",
        group=_MULTI_PROPERTY,
        description="Amlodipine-like profile across several properties.",
        aliases=("amlodipine", "amlodipine-like"),
    ),
    TaskInfo(
        name="fexofenadine_mpo",
        group=_MULTI_PROPERTY,
        description="Fexofenadine-like profile across several properties.",
        aliases=("fexofenadine", "fexofenadine-like", "allegra"),
    ),
    TaskInfo(
        name="osimertinib_mpo",
        group=_MULTI_PROPERTY,
        description="Osimertinib-like profile across several properties.",
        aliases=("osimertinib", "osimertinib-like", "tagrisso"),
    ),
    TaskInfo(
        name="ranolazine_mpo",
        group=_MULTI_PROPERTY,
        description="Ranolazine-like profile across several properties.",
        aliases=("ranolazine", "ranolazine-like", "ranexa"),
    ),
    TaskInfo(
        name="sitagliptin_mpo",
        group=_MULTI_PROPERTY,
        description="Sitagliptin-like profile across several properties.",
        aliases=("sitagliptin", "sitagliptin-like", "januvia"),
    ),
    TaskInfo(
        name="median1",
        group=_MULTI_PROPERTY,
        description="Be similar to two reference molecules at once.",
        aliases=("median1", "median 1", "similar to two reference molecules at once"),
    ),
    TaskInfo(
        name="median2",
        group=_MULTI_PROPERTY,
        description="Be similar to a different two references at once.",
        aliases=("median2", "median 2"),
    ),
    TaskInfo(
        name="isomers_c7h8n2o2",
        group=_MULTI_PROPERTY,
        description="Match the molecular formula C7H8N2O2.",
        aliases=("c7h8n2o2", "formula c7h8n2o2", "isomers c7h8n2o2"),
    ),
    TaskInfo(
        name="isomers_c9h10n2o2pf2cl",
        group=_MULTI_PROPERTY,
        description="Match the formula C9H10N2O2PF2Cl.",
        aliases=("c9h10n2o2pf2cl", "formula c9h10n2o2pf2cl", "isomers c9h10n2o2pf2cl"),
    ),
    TaskInfo(
        name="valsartan_smarts",
        group=_MULTI_PROPERTY,
        description="Hit a valsartan substructure plus target properties.",
        aliases=("valsartan", "valsartan smarts"),
    ),
)

assert {t.name for t in TASKS} == set(PMO_TASKS), (
    "catalog.TASKS has drifted from capychem.eval.tasks.PMO_TASKS"
)

_BY_NAME: dict[str, TaskInfo] = {t.name: t for t in TASKS}


def task_info(name: str) -> TaskInfo | None:
    return _BY_NAME.get(name)


def catalog_groups() -> list[dict[str, Any]]:
    """The 23 tasks grouped in plain language: [{group, tasks: [{name, description}]}]
    (GET /catalog contract), in GROUP_ORDER."""
    return [
        {
            "group": group,
            "tasks": [
                {"name": t.name, "description": t.description} for t in TASKS if t.group == group
            ],
        }
        for group in GROUP_ORDER
    ]
