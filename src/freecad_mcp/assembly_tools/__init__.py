from .assembly3_manager import (
    create_assembly3,
    add_part_to_assembly3,
    add_assembly3_constraint,
    solve_assembly3,
)
from .assembly4_manager import (
    create_assembly4,
    create_lcs_assembly4,
    insert_part_assembly4,
    attach_lcs_to_geometry,
)
from .assembly_common import (
    list_assembly_parts,
    export_assembly,
    calculate_assembly_mass,
)
# Phase 2 - Advanced (2025-10-08)
from .assembly3_advanced import (
    list_assembly3_constraints,
    delete_assembly3_constraint,
    modify_assembly3_constraint,
)
from .assembly4_advanced import (
    list_assembly4_lcs,
    delete_lcs_assembly4,
    modify_lcs_assembly4,
)
from .bom_manager import (
    generate_bom,
    get_assembly_properties,
)

__all__ = [
    # Assembly3 - Phase 1
    "create_assembly3",
    "add_part_to_assembly3",
    "add_assembly3_constraint",
    "solve_assembly3",
    # Assembly4 - Phase 1
    "create_assembly4",
    "create_lcs_assembly4",
    "insert_part_assembly4",
    "attach_lcs_to_geometry",
    # Common - Phase 1
    "list_assembly_parts",
    "export_assembly",
    "calculate_assembly_mass",
    # Assembly3 - Phase 2
    "list_assembly3_constraints",
    "delete_assembly3_constraint",
    "modify_assembly3_constraint",
    # Assembly4 - Phase 2
    "list_assembly4_lcs",
    "delete_lcs_assembly4",
    "modify_lcs_assembly4",
    # BOM - Phase 2
    "generate_bom",
    "get_assembly_properties",
]

