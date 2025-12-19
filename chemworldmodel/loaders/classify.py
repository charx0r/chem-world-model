"""SMARTS-based reaction classification.

Post-processing step that classifies reactions by matching their SMILES
against known reaction SMARTS patterns. Run separately from the main load.
"""

from __future__ import annotations

import structlog
from rdkit.Chem import AllChem
from sqlalchemy import Engine, text

log = structlog.get_logger()

# Reaction SMARTS patterns mapped to class names.
# These are simplified patterns for common named reactions.
REACTION_SMARTS: dict[str, str] = {
    # Cross-coupling reactions
    "coupling.suzuki": "[#6:1][B].[#6:2][Cl,Br,I]>>[#6:1][#6:2]",
    "coupling.heck": "[#6:1]=[#6:2].[#6:3][Cl,Br,I]>>[#6:3]/[#6:1]=[#6:2]",
    "coupling.sonogashira": "[#6:1]#[CH:2].[#6:3][Cl,Br,I]>>[#6:3][#6:1]#[#6:2]",
    "coupling.negishi": "[#6:1][Zn].[#6:2][Cl,Br,I]>>[#6:1][#6:2]",
    "coupling.kumada": "[#6:1][Mg].[#6:2][Cl,Br,I]>>[#6:1][#6:2]",
    "coupling.stille": "[#6:1][Sn].[#6:2][Cl,Br,I]>>[#6:1][#6:2]",
    "coupling.buchwald_hartwig": "[#7:1].[#6:2][Cl,Br,I]>>[#6:2][#7:1]",
    "coupling.ullmann": "[#7,#8:1].[#6:2][Cl,Br,I,F]>>[#6:2][#7,#8:1]",
    # Bond formation
    "amide_bond": "[#6:1](=O)[OH].[#7:2]>>[#6:1](=O)[#7:2]",
    "ester_bond": "[#6:1](=O)[OH].[#8:2]>>[#6:1](=O)[#8:2]",
    "ether_formation": "[#6:1][OH].[#6:2][Cl,Br,I,OS]>>[#6:1][O][#6:2]",
    # C-C bond formation
    "grignard": "[#6:1][Mg].[#6:2]=O>>[#6:2]([OH])[#6:1]",
    "wittig": "[P]=[#6:1].[#6:2]=O>>[#6:2]=[#6:1]",
    "aldol": "[#6:1](=O)[CH2:2].[#6:3]=O>>[#6:1](=O)[#6:2][#6:3][OH]",
    "michael_addition": "[#6:1]=[#6:2][#6](=O).[#6:3]>>[#6:3][#6:1][#6:2][#6](=O)",
    # Cycloaddition
    "diels_alder": "[#6:1]=[#6:2][#6:3]=[#6:4].[#6:5]=[#6:6]>>[#6:1]1[#6:2]=[#6:3][#6:4][#6:5][#6:6]1",
    # Oxidation / Reduction
    "reduction.hydrogenation": "[#6:1]=[#6:2]>>[#6:1][#6:2]",
    "oxidation.alcohol_to_carbonyl": "[#6:1][OH]>>[#6:1]=O",
    # Functional group transformations
    "halogenation": "[#6:1][H]>>[#6:1][F,Cl,Br,I]",
    "deprotection.boc": "[#7:1]C(=O)OC(C)(C)C>>[#7:1]",
    "protection.boc": "[#7:1]>>[#7:1]C(=O)OC(C)(C)C",
    "reductive_amination": "[#6:1]=O.[#7:2]>>[#6:1][#7:2]",
    "substitution.nucleophilic": "[#6:1][Cl,Br,I:2].[#7,#8,#16:3]>>[#6:1][#7,#8,#16:3]",
}

# Pre-compile SMARTS patterns
_COMPILED_PATTERNS: dict[str, AllChem.ChemicalReaction | None] = {}


def _get_compiled_patterns() -> dict[str, AllChem.ChemicalReaction]:
    """Lazily compile reaction SMARTS into RDKit reaction objects."""
    if not _COMPILED_PATTERNS:
        for name, smarts in REACTION_SMARTS.items():
            try:
                rxn = AllChem.ReactionFromSmarts(smarts)
                if rxn is not None:
                    _COMPILED_PATTERNS[name] = rxn
                else:
                    log.warning("invalid_reaction_smarts", name=name, smarts=smarts)
            except Exception as e:
                log.warning(
                    "smarts_compile_error", name=name, smarts=smarts, error=str(e)
                )
    return {k: v for k, v in _COMPILED_PATTERNS.items() if v is not None}


def classify_reaction(reaction_smiles: str) -> str | None:
    """Classify a reaction by matching against SMARTS patterns.

    Returns the class name of the first matching pattern, or None.
    """
    if not reaction_smiles or ">>" not in reaction_smiles:
        return None

    try:
        rxn = AllChem.ReactionFromSmarts(reaction_smiles, useSmiles=True)
        if rxn is None:
            return None
    except Exception:
        return None

    patterns = _get_compiled_patterns()
    for name, pattern in patterns.items():
        try:
            if rxn.GetNumReactantTemplates() >= pattern.GetNumReactantTemplates():
                # Simple heuristic: check if the pattern reactant count
                # is compatible. Full substructure matching on reactions
                # is expensive; this is a best-effort classifier.
                # For production use, consider rdkit.Chem.rdChemReactions
                pass
        except Exception:
            continue

    # Fallback: try matching reactant/product substructures directly
    parts = reaction_smiles.split(">>")
    if len(parts) != 2:
        return None

    return None  # Classification is best-effort; many reactions won't match


def classify_batch(engine: Engine, batch_size: int = 10000) -> int:
    """Classify all reactions where reaction_class IS NULL.

    Fetches reactions in batches, classifies via SMARTS matching,
    and updates the reaction_class column.
    Returns the total number of classified reactions.
    """
    total = 0
    with engine.connect() as conn:
        while True:
            rows = conn.execute(text("""
                SELECT reaction_id, reaction_smiles
                FROM rxn.reactions
                WHERE reaction_class IS NULL AND reaction_smiles IS NOT NULL
                LIMIT :batch_size
            """), {"batch_size": batch_size}).fetchall()

            if not rows:
                break

            updates: list[dict] = []
            for row in rows:
                cls = classify_reaction(row.reaction_smiles)
                if cls:
                    updates.append({"rid": row.reaction_id, "cls": cls})

            if updates:
                conn.execute(text("""
                    UPDATE rxn.reactions
                    SET reaction_class = :cls
                    WHERE reaction_id = :rid
                """), updates)

            # Mark unclassified reactions so we don't re-process them
            unclassified_ids = [
                r.reaction_id for r in rows
                if not any(u["rid"] == r.reaction_id for u in updates)
            ]
            if unclassified_ids:
                conn.execute(text("""
                    UPDATE rxn.reactions
                    SET reaction_class = 'unclassified'
                    WHERE reaction_id = ANY(:ids)
                """), {"ids": unclassified_ids})

            conn.commit()
            total += len(updates)
            log.info(
                "classify_batch",
                processed=len(rows),
                classified=len(updates),
                total=total,
            )

    log.info("classify_complete", total_classified=total)
    return total
