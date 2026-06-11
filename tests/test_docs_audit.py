import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACTIVE_DOCS = [
    ROOT / "FDM_Reference.md",
    ROOT / "Workflows_Cookbook.md",
    ROOT / "SystemPrompt_FreeCAD_Agent_v3.md",
    ROOT / "ProjectMemory_FreeCAD_Agent.md",
]


class DocumentationAuditTests(unittest.TestCase):
    def test_no_deprecated_reference_files_in_active_guides(self):
        banned = [
            "Bambu_A1_FDM_Design_Rules.txt",
            "Bambu_A1_FDM_Design_Guide.pdf",
            "FreeCAD_Python_Scripting_Reference.md",
        ]
        offenders = []
        for path in ACTIVE_DOCS:
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if path.name == "FDM_Reference.md" and "Replaces:" in line:
                    continue
                for token in banned:
                    if token in line:
                        offenders.append(f"{path.name}:{lineno}:{token}")
        self.assertEqual([], offenders)

    def test_mesh_to_shape_mentions_only_in_fdm_pitfalls(self):
        offenders = []
        for path in ACTIVE_DOCS:
            in_pitfalls = False
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if path.name == "FDM_Reference.md" and "§13 PITFALLS" in line:
                    in_pitfalls = True
                if path.name == "FDM_Reference.md" and "§14 NAMING" in line:
                    in_pitfalls = False
                if "MeshPart.meshToShape" in line and not in_pitfalls:
                    offenders.append(f"{path.name}:{lineno}")
        self.assertEqual([], offenders)

    def test_mutating_python_snippets_recompute_before_they_end(self):
        offenders = []
        for path in [ROOT / "FDM_Reference.md", ROOT / "Workflows_Cookbook.md"]:
            text = path.read_text(encoding="utf-8")
            lines = text.splitlines()
            in_fence = False
            fence_start = 0
            lang = ""
            block = []
            for lineno, line in enumerate(lines, 1):
                if line.startswith("```"):
                    if not in_fence:
                        in_fence = True
                        fence_start = lineno
                        lang = line[3:].strip()
                        block = []
                    else:
                        snippet = "\n".join(block)
                        is_python = lang == "python"
                        mutates_doc = any(
                            token in snippet
                            for token in [
                                "doc.addObject",
                                "doc.getObject(\"Final\")",
                                "Mesh.export(",
                                ".Placement",
                                ".Base =",
                                ".Tool =",
                                ".Visibility =",
                            ]
                        )
                        if is_python and mutates_doc and "doc.recompute()" not in snippet:
                            offenders.append(f"{path.name}:{fence_start}-{lineno}")
                        in_fence = False
                elif in_fence:
                    block.append(line)
        self.assertEqual([], offenders)

    def test_every_cookbook_recipe_has_verified_session_reference(self):
        text = (ROOT / "Workflows_Cookbook.md").read_text(encoding="utf-8")
        sections = re.split(r"(?=^## Recipe \d+)", text, flags=re.MULTILINE)
        offenders = []
        for section in sections:
            match = re.match(r"## Recipe \d+.*", section)
            if match and "Verified session:" not in section:
                offenders.append(match.group(0))
        self.assertEqual([], offenders)

    def test_short_tolerance_summaries_include_full_standard_set(self):
        checks = {
            "Workflows_Cookbook.md": (ROOT / "Workflows_Cookbook.md").read_text(encoding="utf-8"),
            "SystemPrompt_FreeCAD_Agent_v3.md": (ROOT / "SystemPrompt_FreeCAD_Agent_v3.md").read_text(encoding="utf-8"),
        }
        offenders = []
        for name, text in checks.items():
            for token in ["+0.2", "+0.4", "+0.3"]:
                if token not in text:
                    offenders.append(f"{name}:{token}")
        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
