"""Scaffold identity includes aromatic protonation, not only connectivity."""

from rdkit import Chem


def scaffold_query(parent: Chem.Mol) -> Chem.Mol:
    """Preserve parent atom order while enforcing aromatic nitrogen H counts.

    Ordinary RDKit molecule substructure matching does not distinguish neutral
    aromatic n from [nH]. Explicit queries prevent accepting a different purine
    tautomer as the fixed state. Nonaromatic attachment atoms remain substitutable.
    """
    query = Chem.RWMol(parent)
    for atom in parent.GetAtoms():
        if atom.GetIsAromatic() and atom.GetAtomicNum() == 7:
            replacement = Chem.AtomFromSmarts(
                f"[nH{atom.GetTotalNumHs()}+{atom.GetFormalCharge()}]"
            )
            if replacement is None:
                raise ValueError("Could not construct the scaffold protonation query")
            query.ReplaceAtom(atom.GetIdx(), replacement, preserveProps=True)
    return query.GetMol()
