"""Hard structural constraints (07-04b) applied at the validity gate.

A molecule passes iff it trips NO exclude pattern / catalog alarm AND matches EVERY
required include SMARTS. Constraint-failing molecules are treated like invalid ones —
dropped before scoring, so no oracle budget is spent on them (FR-005 fallback keeps
throughput). Soft property bands (MW/logP/TPSA) are NOT here — a band is an objective
term (a descriptor oracle + a ``double_sigmoid`` transform, 07-04).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rdkit import Chem
from rdkit.Chem import FilterCatalog
from rdkit.Chem.FilterCatalog import FilterCatalogParams

# The bundled RDKit alarm catalogs we expose by name.
_CATALOGS = {
    "PAINS": FilterCatalogParams.FilterCatalogs.PAINS,
    "BRENK": FilterCatalogParams.FilterCatalogs.BRENK,
    "NIH": FilterCatalogParams.FilterCatalogs.NIH,
}


def _compile_smarts(patterns: list[str]) -> list[Any]:
    compiled: list[Any] = []
    for s in patterns:
        patt = Chem.MolFromSmarts(s)
        if patt is None:
            raise ValueError(f"Invalid SMARTS pattern {s!r}; RDKit could not parse it.")
        compiled.append(patt)
    return compiled


@dataclass(frozen=True)
class Constraints:
    """Compiled hard constraints. Build via :meth:`from_json`."""

    catalog: Any  # rdkit FilterCatalog or None
    exclude: list[Any]  # compiled exclude SMARTS
    include: list[Any]  # compiled required-include SMARTS

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> Constraints:
        cat_names = d.get("catalogs", [])
        catalog = None
        if cat_names:
            params = FilterCatalogParams()
            for name in cat_names:
                if name not in _CATALOGS:
                    raise ValueError(f"Unknown catalog {name!r}; choose from {sorted(_CATALOGS)}.")
                params.AddCatalog(_CATALOGS[name])
            catalog = FilterCatalog.FilterCatalog(params)
        return cls(
            catalog=catalog,
            exclude=_compile_smarts(d.get("smarts_exclude", [])),
            include=_compile_smarts(d.get("smarts_include", [])),
        )

    def is_empty(self) -> bool:
        return self.catalog is None and not self.exclude and not self.include

    def passes(self, smiles: str) -> bool:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return False  # invalid SMILES never passes
        if self.catalog is not None and self.catalog.HasMatch(mol):
            return False
        if any(mol.HasSubstructMatch(patt) for patt in self.exclude):
            return False
        return all(mol.HasSubstructMatch(patt) for patt in self.include)
