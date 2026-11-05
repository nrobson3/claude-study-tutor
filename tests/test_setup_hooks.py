"""setup_hooks.py writes the four lesson-log hooks for this machine."""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("setup_hooks", ROOT / "scripts" / "setup_hooks.py")
setup_hooks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup_hooks)


class SetupHooksTests(unittest.TestCase):
    def test_every_event_runs_the_lesson_log(self):
        s = setup_hooks.settings(python="/usr/bin/python3", vault="/home/me/vault")["hooks"]
        self.assertEqual(set(s), {"UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"})
        for event, entries in s.items():
            hook = entries[0]["hooks"][0]
            self.assertEqual(hook["command"], "/usr/bin/python3")
            self.assertEqual(Path(hook["args"][0]), Path("/home/me/vault/scripts/lesson_log.py"))
            self.assertEqual(hook["args"][1], "hook")

    def test_matchers(self):
        s = setup_hooks.settings(python="py", vault="v")["hooks"]
        self.assertEqual(s["PreToolUse"][0]["matcher"], "AskUserQuestion")
        self.assertEqual(s["PostToolUse"][0]["matcher"], "AskUserQuestion|Bash|PowerShell")
        self.assertNotIn("matcher", s["Stop"][0])


if __name__ == "__main__":
    unittest.main()
