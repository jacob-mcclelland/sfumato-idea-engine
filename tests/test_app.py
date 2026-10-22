"""Tests for the Gradio wrapper. Skipped unless gradio is installed (the CI app
job installs requirements.txt); no Space is launched and no provider is called."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    import gradio as gr
except ImportError:  # the core job runs without third-party packages
    gr = None


@unittest.skipIf(gr is None, "gradio is not installed")
class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app

        cls.app = app

    def test_endpoint_is_named(self):
        config = self.app.demo.get_config_file()
        names = [dep.get("api_name") for dep in config["dependencies"]]
        self.assertIn("generate_seed_packet", names)

    def test_inputs_are_passed_through_as_integers(self):
        with mock.patch.object(self.app, "generate_seed_packet", return_value={"ok": True}) as run:
            result = self.app.run_pipeline("brief", 33.0, 2.0, 8.0, [100, 180], "", progress=mock.Mock())
        self.assertEqual(result, {"ok": True})
        _, kwargs = run.call_args
        self.assertEqual((kwargs["candidate_count"], kwargs["max_selected_seeds"], kwargs["trials_per_pass"]), (33, 2, 8))
        self.assertIsNone(kwargs["client_run_id"])

    def test_pipeline_errors_become_gradio_errors(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(gr.Error) as caught:
                self.app.run_pipeline("brief", 33, 5, 8, [100, 180], "", progress=mock.Mock())
        self.assertIn("MERCURY_API_KEY", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
