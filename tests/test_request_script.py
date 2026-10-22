"""Offline tests for the skill's client script. A fake gradio_client stands in
for the hosted Space, so nothing is installed or called over the network."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "sfumato-skill" / "scripts" / "request_seed_packet.py"
spec = importlib.util.spec_from_file_location("request_seed_packet", SCRIPT)
script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(script)


def fake_gradio_client(result=None, error=None):
    calls = []

    class Client:
        def __init__(self, space, hf_token=None, verbose=True):
            calls.append(("init", space, hf_token))

        def predict(self, *args, api_name=None):
            calls.append(("predict", args, api_name))
            if error:
                raise error
            return result

    return types.SimpleNamespace(Client=Client), calls


class UnwrapTests(unittest.TestCase):
    def test_unwrap(self):
        self.assertEqual(script.unwrap_result(['{"a": 1}']), {"a": 1})
        self.assertEqual(script.unwrap_result(({"a": 1},)), {"a": 1})
        self.assertEqual(script.unwrap_result("not json"), "not json")
        self.assertEqual(script.unwrap_result([1, 2]), [1, 2])


class MainTests(unittest.TestCase):
    def run_main(self, argv, module=None, env=None):
        out, err = io.StringIO(), io.StringIO()
        modules = {"gradio_client": module} if module else {}
        with mock.patch.object(sys, "argv", ["request_seed_packet.py", *argv]), \
                mock.patch.dict(sys.modules, modules), \
                mock.patch.dict("os.environ", env or {}, clear=True), \
                redirect_stdout(out), redirect_stderr(err):
            try:
                code = script.main()
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue(), err.getvalue()

    def brief_file(self, text):
        handle = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8")
        handle.write(text)
        handle.close()
        self.addCleanup(Path(handle.name).unlink)
        return handle.name

    def test_space_is_required(self):
        code, _, err = self.run_main(["--brief-file", self.brief_file("brief")])
        self.assertEqual(code, 2)
        self.assertIn("SFUMATO_SPACE", err)

    def test_missing_or_empty_brief(self):
        code, _, err = self.run_main(["--space", "me/space", "--brief-file", "no-such-file.txt"])
        self.assertEqual((code, err.strip()), (2, "Could not read the brief file."))
        code, _, err = self.run_main(["--space", "me/space", "--brief-file", self.brief_file("  \n")])
        self.assertEqual((code, err.strip()), (2, "The brief file is empty."))

    def test_success_prints_the_packet(self):
        module, calls = fake_gradio_client(result=(json.dumps({"schema": "sfumato-seed-packet-1"}),))
        code, out, _ = self.run_main(
            ["--brief-file", self.brief_file("  A brief.  "), "--max-selected-seeds", "3",
             "--word-range", "60", "90", "--client-run-id", "r1"],
            module=module, env={"SFUMATO_SPACE": "me/space", "HF_TOKEN": "hf-test"},
        )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {"schema": "sfumato-seed-packet-1"})
        self.assertEqual(calls[0], ("init", "me/space", "hf-test"))
        self.assertEqual(calls[1], ("predict", ("A brief.", 33, 3, 8, [60, 90], "r1"), "/generate_seed_packet"))

    def test_failure_names_the_error_type_only(self):
        module, _ = fake_gradio_client(error=RuntimeError("token hf-secret rejected"))
        code, out, err = self.run_main(
            ["--space", "me/space", "--brief-file", self.brief_file("brief")],
            module=module, env={"HF_TOKEN": "hf-secret"},
        )
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertEqual(err.strip(), "Sfumato request failed (RuntimeError).")


if __name__ == "__main__":
    unittest.main()
