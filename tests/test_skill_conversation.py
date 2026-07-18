import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1] / "skills" / "ampero-tone"
SKILL_PATH = SKILL_ROOT / "SKILL.md"
FLOW_PATH = SKILL_ROOT / "references" / "conversation-flow.md"
RESEARCH_PATH = SKILL_ROOT / "references" / "tone-research.md"
AGENT_PATH = SKILL_ROOT / "agents" / "openai.yaml"


class SkillConversationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill = SKILL_PATH.read_text(encoding="utf-8")
        cls.flow = FLOW_PATH.read_text(encoding="utf-8")
        cls.research = RESEARCH_PATH.read_text(encoding="utf-8")
        cls.agent = AGENT_PATH.read_text(encoding="utf-8")
        cls.skill_normalized = " ".join(cls.skill.split())
        cls.flow_normalized = " ".join(cls.flow.split())

    def test_skill_requires_conversation_flow(self):
        self.assertIn("references/conversation-flow.md", self.skill)

    def test_skill_agent_metadata_is_publication_ready(self):
        self.assertIn("Research and safely tune Ampero II tones", self.agent)
        self.assertNotIn("vibe_ampere", self.skill)

    def test_named_tones_require_structured_web_research(self):
        self.assertIn("references/tone-research.md", self.skill)
        self.assertIn("browse the web", self.skill.lower())
        self.assertIn("Source Hierarchy", self.research)
        self.assertIn("Separate Facts From Inferences", self.research)
        self.assertIn("installed official catalog", self.research)
        self.assertIn("research` object", self.flow)

    def test_required_stages_are_ordered(self):
        stages = [
            "## Stage 1 - Guitar Context",
            "## Stage 2 - Output Context",
            "## Stage 3 - Tone Research",
            "## Stage 4 - Detailed Proposal",
            "## Stage 5 - Tone Approval",
            "## Stage 6 - Write Destination",
            "## Stage 7 - Final Write Gate",
            "## Stage 8 - Write Result",
            "## Stage 9 - Save Decision",
        ]
        positions = [self.flow.index(stage) for stage in stages]
        self.assertEqual(positions, sorted(positions))

    def test_destination_is_not_write_approval(self):
        self.assertIn("A destination answer alone is not write approval", self.flow)
        self.assertIn("final explicit write confirmation", self.flow)

    def test_save_is_separate_irreversible_and_confirmed(self):
        self.assertIn("successful apply journal", self.flow_normalized)
        self.assertIn("SAVE:Axx-y", self.flow_normalized)
        self.assertIn("Saving cannot be", self.flow_normalized)
        self.assertIn("control layer", self.flow_normalized)
        self.assertIn("Never claim the preset is saved", self.flow_normalized)
        self.assertIn("official save response", self.flow_normalized)

    def test_apply_can_return_save_preview_without_extra_question(self):
        self.assertIn("save_preview_name", self.skill)
        self.assertIn(
            "without first asking a generic save question", self.skill_normalized
        )
        self.assertIn("Do not add an intermediate generic", self.flow)
        self.assertIn("save preview", self.flow)


if __name__ == "__main__":
    unittest.main()
