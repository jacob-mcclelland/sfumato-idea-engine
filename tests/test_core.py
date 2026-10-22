"""Offline tests for sfumato_core.

No provider keys and no network: every provider call goes through a fake that
answers from a script, and any real HTTP request fails the test.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sfumato_core as core  # noqa: E402

KEYS = {"MERCURY_API_KEY": "test-mercury-key", "TYPESAFE_API_KEY": "test-typesafe-key"}


def candidate_ids(criteria: dict[str, str]) -> dict[str, int]:
    """Map each option label to the candidate number written in its text."""
    return {
        label: int(text.split()[1].rstrip(":"))
        for label, text in criteria.items()
        if label != "none_other"
    }


class FakeProviders:
    """Stands in for _post_json. Mercury returns numbered candidates; Jev answers
    through a judge(criteria, call_number) -> (choice, probabilities) script."""

    def __init__(self, judge, *, usage: bool = True, jev_tokens: int = 1000):
        self.judge = judge
        self.usage = usage
        self.jev_tokens = jev_tokens
        self.mercury_payloads: list[dict] = []
        self.jev_payloads: list[dict] = []

    def __call__(self, url, api_key, payload, **kwargs):
        if url == core.MERCURY_ENDPOINT:
            assert api_key == KEYS["MERCURY_API_KEY"]
            self.mercury_payloads.append(payload)
            n = len(self.mercury_payloads)
            reply = {"choices": [{"message": {"content": f"  Seed {n}: mechanism number {n}.  "}}]}
            if self.usage:
                reply["usage"] = {"prompt_tokens": 100, "completion_tokens": 150}
            return reply
        if url == core.JEV_ENDPOINT:
            assert api_key == KEYS["TYPESAFE_API_KEY"]
            self.jev_payloads.append(payload)
            criteria = payload["questions"]["selection"]["criteria"]
            choice, probabilities = self.judge(criteria, len(self.jev_payloads))
            return {
                "answers": {"selection": {"choice": choice, "probabilities": probabilities}},
                "usage": {"input_tokens": self.jev_tokens},
            }
        raise AssertionError(f"unexpected provider URL {url}")


def prefer_lowest(stop_above: int | None = None, mass: float = 0.9):
    """Always pick the lowest-numbered candidate offered, or 'none of these' once
    every remaining candidate is numbered above stop_above."""

    def judge(criteria, call_number):
        ids = candidate_ids(criteria)
        best = min(ids, key=ids.get)
        if stop_above is not None and ids[best] > stop_above:
            return "none_other", {"none_other": mass, best: 1 - mass}
        return best, {best: mass, "none_other": 1 - mass}

    return judge


def split_votes(favorite_wins: int, *, flip_second_order: bool = False):
    """One pass: the lowest-numbered candidate always carries the most mass, but
    wins only the first `favorite_wins` trials; other trials go to a different
    candidate each time. Calls alternate first order, reversed order."""

    def judge(criteria, call_number):
        ids = candidate_ids(criteria)
        ordered = sorted(ids, key=ids.get)
        favorite = ordered[0]
        trial = (call_number - 1) // 2
        first_order = call_number % 2 == 1
        pick = favorite if trial < favorite_wins else ordered[1 + trial]
        if flip_second_order and not first_order:
            pick = "none_other"
        probabilities = {label: 0.01 for label in ids}
        probabilities[favorite] = 0.5
        probabilities["none_other"] = 0.02
        return pick, probabilities

    return judge


class NoNetwork(unittest.TestCase):
    """Fails any test that reaches the real network."""

    def setUp(self):
        guard = mock.patch(
            "urllib.request.urlopen",
            side_effect=AssertionError("a test tried to reach the network"),
        )
        guard.start()
        self.addCleanup(guard.stop)


class ValidateRequestTests(unittest.TestCase):
    def test_defaults_and_trimming(self):
        brief, words = core.validate_request("  A concrete brief.  \n", 33, 5, 8, None)
        self.assertEqual(brief, "A concrete brief.")
        self.assertEqual(words, (100, 180))

    def test_accepted_values(self):
        for count in (33, 100):
            core.validate_request("brief", count, 1, 8, [50, 250])
        for seeds in range(1, 6):
            core.validate_request("brief", 33, seeds, 8, (50, 51))
        core.validate_request("x" * core.MAX_BRIEF_CHARS, 33, 5, 8, None)

    def test_rejected_values(self):
        bad = [
            (("", 33, 5, 8, None), "concrete problem brief"),
            (("   \n", 33, 5, 8, None), "concrete problem brief"),
            ((123, 33, 5, 8, None), "plain text"),
            (("x" * (core.MAX_BRIEF_CHARS + 1), 33, 5, 8, None), "characters or fewer"),
            (("brief", 34, 5, 8, None), "33 or 100"),
            (("brief", 33.0, 5, 8, None), "33 or 100"),
            (("brief", True, 5, 8, None), "33 or 100"),
            (("brief", 33, 0, 8, None), "between 1 and 5"),
            (("brief", 33, 6, 8, None), "between 1 and 5"),
            (("brief", 33, 5, 7, None), "fixed at 8"),
            (("brief", 33, 5, 8, [100]), "minimum_words, maximum_words"),
            (("brief", 33, 5, 8, "100-180"), "minimum_words, maximum_words"),
            (("brief", 33, 5, 8, [100.0, 180]), "minimum_words, maximum_words"),
            (("brief", 33, 5, 8, [49, 100]), "50 <= minimum"),
            (("brief", 33, 5, 8, [100, 251]), "50 <= minimum"),
            (("brief", 33, 5, 8, [180, 100]), "50 <= minimum"),
            (("brief", 33, 5, 8, [100, 100]), "50 <= minimum"),
        ]
        for args, message in bad:
            with self.subTest(args=args[1:], brief=str(args[0])[:12]):
                with self.assertRaisesRegex(core.SfumatoError, message):
                    core.validate_request(*args)


class KeyTests(NoNetwork):
    def test_missing_or_blank_key_is_reported_by_name(self):
        with mock.patch.dict(os.environ, {"MERCURY_API_KEY": "   "}, clear=True):
            with self.assertRaisesRegex(core.SfumatoError, "MERCURY_API_KEY"):
                core._require_key("MERCURY_API_KEY")

    def test_packet_without_keys_fails_before_any_provider_call(self):
        post = mock.Mock(side_effect=AssertionError("provider called"))
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(core, "_post_json", post):
            with self.assertRaisesRegex(core.SfumatoError, "MERCURY_API_KEY"):
                core.generate_seed_packet("A concrete brief.")
            with mock.patch.dict(os.environ, {"MERCURY_API_KEY": "k"}):
                with self.assertRaisesRegex(core.SfumatoError, "TYPESAFE_API_KEY"):
                    core.generate_seed_packet("A concrete brief.")
        post.assert_not_called()

    def test_request_is_validated_before_keys(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(core.SfumatoError, "33 or 100"):
                core.generate_seed_packet("brief", candidate_count=50)

    def test_client_run_id_limits(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            for bad in ("x" * 129, 42):
                with self.subTest(bad=bad):
                    with self.assertRaisesRegex(core.SfumatoError, "client_run_id"):
                        core.generate_seed_packet("brief", client_run_id=bad)


class FakeResponse:
    def __init__(self, body):
        self.body = body if isinstance(body, bytes) else json.dumps(body).encode()

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class PostJsonTests(unittest.TestCase):
    def setUp(self):
        sleep = mock.patch.object(core.time, "sleep")
        self.sleep = sleep.start()
        self.addCleanup(sleep.stop)

    def http_error(self, code):
        error = urllib.error.HTTPError("https://provider.test", code, "error", {}, io.BytesIO(b""))
        self.addCleanup(error.close)
        return error

    def post(self, *responses):
        urlopen = mock.Mock(side_effect=list(responses))
        with mock.patch("urllib.request.urlopen", urlopen):
            try:
                return core._post_json("https://provider.test/v1", "secret-key", {"a": 1}), urlopen
            except core.SfumatoError as exc:
                return exc, urlopen

    def test_success_sends_a_json_post_with_bearer_key(self):
        result, urlopen = self.post(FakeResponse({"ok": True}))
        self.assertEqual(result, {"ok": True})
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Authorization"), "Bearer secret-key")
        self.assertEqual(json.loads(request.data), {"a": 1})

    def test_rate_limit_retries_with_backoff(self):
        result, urlopen = self.post(self.http_error(429), self.http_error(529), FakeResponse({"ok": 1}))
        self.assertEqual(result, {"ok": 1})
        self.assertEqual(urlopen.call_count, 3)
        self.assertEqual([c.args[0] for c in self.sleep.call_args_list], [1.0, 2.0])

    def test_rate_limit_that_never_clears(self):
        result, urlopen = self.post(self.http_error(429), self.http_error(429), self.http_error(429))
        self.assertIsInstance(result, core.SfumatoError)
        self.assertIn("busy or rate limited", str(result))
        self.assertEqual(urlopen.call_count, 3)

    def test_rejected_key_is_not_retried(self):
        result, urlopen = self.post(self.http_error(401))
        self.assertIn("rejected its configured API key", str(result))
        self.assertEqual(urlopen.call_count, 1)

    def test_other_http_errors_are_not_retried(self):
        result, urlopen = self.post(self.http_error(500))
        self.assertIn("HTTP 500", str(result))
        self.assertEqual(urlopen.call_count, 1)

    def test_network_failure_retries_then_fails(self):
        failure = urllib.error.URLError("unreachable")
        result, urlopen = self.post(failure, failure, failure)
        self.assertIn("Please retry later", str(result))
        self.assertEqual(urlopen.call_count, 3)

    def test_non_object_json_is_rejected(self):
        result, _ = self.post(FakeResponse([1, 2, 3]))
        self.assertIn("invalid response shape", str(result))

    def test_errors_never_echo_the_key(self):
        for responses in ([self.http_error(401)], [self.http_error(500)], [urllib.error.URLError("x")] * 3):
            result, _ = self.post(*responses)
            self.assertNotIn("secret-key", str(result))


class ProviderParsingTests(NoNetwork):
    def test_candidate_is_trimmed_hashed_and_counted(self):
        reply = {
            "choices": [{"message": {"content": "  An idea.  "}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 34},
            "warning": "slow",
        }
        with mock.patch.object(core, "_post_json", return_value=reply) as post:
            row = core._generate_one("brief", 7, "k", (60, 90))
        self.assertEqual(row["text"], "An idea.")
        self.assertEqual(row["sha256"], hashlib.sha256(b"An idea.").hexdigest())
        self.assertEqual((row["candidate_id"], row["input_tokens"], row["output_tokens"]), (7, 12, 34))
        self.assertEqual(row["warning"], "slow")
        payload = post.call_args.args[2]
        self.assertEqual(payload["max_tokens"], 256)
        self.assertIn("about 60-90", payload["messages"][0]["content"])
        self.assertTrue(payload["messages"][0]["content"].endswith("Problem:\nbrief"))

    def test_empty_or_malformed_candidate_is_an_error(self):
        for reply in ({"choices": [{"message": {"content": "  "}}]}, {"choices": []}, {}):
            with self.subTest(reply=reply):
                with mock.patch.object(core, "_post_json", return_value=reply):
                    with self.assertRaisesRegex(core.SfumatoError, "position 4"):
                        core._generate_one("brief", 4, "k", (100, 180))

    def test_missing_usage_is_unknown_not_zero(self):
        reply = {"choices": [{"message": {"content": "idea"}}], "usage": "n/a"}
        with mock.patch.object(core, "_post_json", return_value=reply):
            row = core._generate_one("brief", 1, "k", (100, 180))
        self.assertIsNone(row["input_tokens"])
        self.assertIsNone(row["output_tokens"])

    def test_choice_call_parsing(self):
        criteria = {"candidate_001": "a", "none_other": core.NONE_OTHER}
        reply = {"answers": {"selection": {"choice": 5, "probabilities": {"candidate_001": "0.75"}}},
                 "usage": {"input_tokens": "lots"}}
        with mock.patch.object(core, "_post_json", return_value=reply):
            mass, picked, tokens = core._choice_call("k", {}, criteria, "q")
        self.assertEqual(mass, {"candidate_001": 0.75, "none_other": 0.0})
        self.assertIsNone(picked)
        self.assertEqual(tokens, 0)

    def test_choice_call_rejects_a_reply_without_answers(self):
        with mock.patch.object(core, "_post_json", return_value={"usage": {}}):
            with self.assertRaisesRegex(core.SfumatoError, "invalid selection response"):
                core._choice_call("k", {}, {"none_other": core.NONE_OTHER}, "q")


def make_candidates(n: int) -> list[dict]:
    rows = []
    for i in range(1, n + 1):
        text = f"Seed {i}: mechanism number {i}."
        rows.append({"candidate_id": i, "text": text, "sha256": hashlib.sha256(text.encode()).hexdigest()})
    return rows


class SelectionTests(NoNetwork):
    def select(self, judge, *, count=33, max_seeds=1):
        fake = FakeProviders(judge)
        with mock.patch.object(core, "_post_json", fake):
            selected, stop, tokens = core._select(
                make_candidates(count), problem_brief="brief", api_key=KEYS["TYPESAFE_API_KEY"],
                max_selected_seeds=max_seeds, trials=8, seed=11,
            )
        return selected, stop, tokens, fake

    def test_win_counts_set_core_optional_or_skip(self):
        expected = {8: "core", 6: "core", 5: "optional", 4: "optional", 3: "unresolved", 2: "unresolved"}
        for wins, status in expected.items():
            with self.subTest(wins=wins):
                selected, stop, _, _ = self.select(split_votes(wins))
                decision = stop["decisions"][0]
                self.assertEqual(decision["winner_count"], wins)
                self.assertEqual(decision["candidate_id"], 1)
                if status == "unresolved":
                    self.assertEqual(selected, [])
                    self.assertEqual(decision["decision"], "skip_unresolved")
                else:
                    self.assertEqual([s["status"] for s in selected], [status])
                    self.assertEqual(decision["decision"], "selected")

    def test_fewer_than_three_wins_is_skipped_and_selection_continues(self):
        def judge(criteria, call_number):
            if call_number <= 16:  # first pass: favourite wins only 2 of 8
                return split_votes(2)(criteria, call_number)
            return prefer_lowest()(criteria, call_number)

        selected, stop, _, fake = self.select(judge, max_seeds=2)
        self.assertEqual(stop["decisions"][0]["reason"], "best_candidate_won_fewer_than_three_trials")
        self.assertEqual([s["candidate_id"] for s in selected], [2])
        offered_in_pass_two = candidate_ids(fake.jev_payloads[16]["questions"]["selection"]["criteria"])
        self.assertNotIn(1, offered_in_pass_two.values())

    def test_none_of_these_winning_half_the_trials_stops(self):
        selected, stop, _, _ = self.select(prefer_lowest(stop_above=2), max_seeds=5)
        self.assertEqual([s["candidate_id"] for s in selected], [1, 2])
        self.assertEqual([s["rank"] for s in selected], [1, 2])
        self.assertEqual((stop["reason"], stop["pass"]), ("none_other_won_at_least_half", 3))
        self.assertEqual(stop["decisions"][-1]["decision"], "stop")

    def test_none_of_these_winning_exactly_half_stops(self):
        def judge(criteria, call_number):
            ids = candidate_ids(criteria)
            favorite = min(ids, key=ids.get)
            pick = "none_other" if (call_number - 1) // 2 < 4 else favorite
            return pick, {favorite: 0.5, "none_other": 0.02}

        selected, stop, _, _ = self.select(judge, max_seeds=3)
        self.assertEqual(selected, [])
        self.assertEqual(stop["decisions"][0]["none_other_wins"], 4)
        self.assertEqual((stop["reason"], stop["pass"]), ("none_other_won_at_least_half", 1))

    def test_none_of_these_mass_at_least_the_best_stops(self):
        def judge(criteria, call_number):
            ids = candidate_ids(criteria)
            best = min(ids, key=ids.get)
            return best, {best: 0.4, "none_other": 0.4}

        selected, stop, _, _ = self.select(judge, max_seeds=3)
        self.assertEqual(selected, [])
        self.assertEqual((stop["reason"], stop["pass"]), ("none_other_mass_at_least_best_candidate", 1))

    def test_pass_limit_and_token_count(self):
        selected, stop, tokens, fake = self.select(prefer_lowest(), max_seeds=2)
        self.assertEqual(len(selected), 2)
        self.assertEqual((stop["reason"], stop["pass"]), ("maximum_selection_passes_reached", 2))
        self.assertEqual(len(fake.jev_payloads), 2 * 8 * 2)
        self.assertEqual(tokens, 2 * 8 * 2 * 1000)

    def test_each_trial_asks_both_orders_with_a_none_option(self):
        _, _, _, fake = self.select(prefer_lowest())
        for first, second in zip(fake.jev_payloads[0::2], fake.jev_payloads[1::2]):
            a = list(first["questions"]["selection"]["criteria"].items())
            b = list(second["questions"]["selection"]["criteria"].items())
            self.assertEqual(b, a[::-1])
            self.assertEqual(dict(a)["none_other"], core.NONE_OTHER)
            self.assertEqual(len(a), 33 + 1)

    def test_win_counts_use_the_first_order_and_flips_are_counted(self):
        selected, stop, _, _ = self.select(split_votes(8, flip_second_order=True))
        self.assertEqual(selected[0]["winner_count"], 8)
        self.assertEqual(stop["decisions"][0]["order_flips"], 8)

    def test_later_passes_name_what_was_selected(self):
        _, _, _, fake = self.select(prefer_lowest(), max_seeds=2)
        first, later = fake.jev_payloads[0], fake.jev_payloads[16]
        self.assertEqual(first["questions"]["selection"]["instructions"], core.FIRST_QUESTION)
        self.assertNotIn("already been selected", first["state"]["selection_purpose"])
        self.assertIn("Selected branch 1: Seed 1:", later["state"]["selection_purpose"])
        self.assertIn("32 remaining proposals", later["state"]["selection_purpose"])

    def test_same_seed_gives_the_same_trial_orders(self):
        orders = []
        for _ in range(2):
            fake = FakeProviders(prefer_lowest())
            with mock.patch.object(core, "_post_json", fake):
                core._rank_pass(candidates=make_candidates(10), selected=[], problem_brief="b",
                                api_key=KEYS["TYPESAFE_API_KEY"], trials=8, seed=3)
            orders.append([list(p["questions"]["selection"]["criteria"].values()) for p in fake.jev_payloads])
        self.assertEqual(orders[0], orders[1])


class PacketTests(NoNetwork):
    def packet(self, judge, *, usage=True, **kwargs):
        fake = FakeProviders(judge, usage=usage)
        with mock.patch.dict(os.environ, KEYS), mock.patch.object(core, "_post_json", fake):
            return core.generate_seed_packet("  A concrete brief.  ", **kwargs), fake

    def test_packet_fields_and_costs(self):
        packet, fake = self.packet(prefer_lowest(stop_above=2), client_run_id="run-1")
        self.assertEqual(packet["schema"], "sfumato-seed-packet-1")
        self.assertEqual(packet["problem_brief"], "A concrete brief.")
        self.assertEqual(packet["client_run_id"], "run-1")
        self.assertEqual(len(fake.mercury_payloads), 33)
        self.assertEqual(packet["generator"]["candidate_count_returned"], 33)
        self.assertEqual(packet["generator"]["word_range"], [100, 180])
        self.assertEqual(packet["ranker"]["trials_per_pass"], 8)

        hashes = packet["provenance"]["candidate_hashes"]
        self.assertEqual(len(hashes), 33)
        self.assertEqual(hashes[0], hashlib.sha256(b"Seed 1: mechanism number 1.").hexdigest())
        self.assertEqual([s["candidate_sha256"] for s in packet["selected_seeds"]], hashes[:2])
        self.assertEqual([s["status"] for s in packet["selected_seeds"]], ["core", "core"])
        self.assertEqual(packet["stop"]["reason"], "none_other_won_at_least_half")

        usage = packet["usage"]
        self.assertEqual((usage["mercury_input_tokens"], usage["mercury_output_tokens"]), (3300, 4950))
        self.assertEqual(usage["jev_input_tokens"], 3 * 16 * 1000)
        mercury = (3300 * core.MERCURY_INPUT_USD_PER_M + 4950 * core.MERCURY_OUTPUT_USD_PER_M) / 1e6
        jev = 3 * 16 * 1000 * core.JEV_INPUT_USD_PER_M / 1e6
        self.assertAlmostEqual(usage["mercury_estimated_cost_usd"], mercury)
        self.assertAlmostEqual(usage["jev_estimated_cost_usd"], jev)
        self.assertAlmostEqual(usage["estimated_cost_usd"], mercury + jev)
        self.assertEqual(packet["warnings"], [])
        json.dumps(packet)  # the packet must serialise as the API returns it

    def test_unknown_mercury_usage_makes_cost_unknown(self):
        packet, _ = self.packet(prefer_lowest(stop_above=1), usage=False)
        self.assertIsNone(packet["usage"]["mercury_input_tokens"])
        self.assertIsNone(packet["usage"]["estimated_cost_usd"])
        self.assertIn("Mercury did not return complete token usage; its cost is unknown.", packet["warnings"])

    def test_weak_or_skipped_selections_are_warned(self):
        packet, _ = self.packet(split_votes(5), max_selected_seeds=1)
        self.assertEqual(packet["selected_seeds"][0]["status"], "optional")
        self.assertIn("Optional seeds have weaker selection support than core seeds.", packet["warnings"])

        packet, _ = self.packet(split_votes(2), max_selected_seeds=1)
        self.assertEqual(packet["selected_seeds"], [])
        self.assertIn("At least one unstable candidate was skipped; selection continued.", packet["warnings"])

    def test_progress_reports_stay_in_range(self):
        seen = []
        self.packet(prefer_lowest(stop_above=1), max_selected_seeds=2,
                    progress=lambda value, text: seen.append(value))
        self.assertTrue(seen)
        self.assertTrue(all(0.0 <= v <= 1.0 for v in seen))
        self.assertEqual(seen, sorted(seen))


if __name__ == "__main__":
    unittest.main()
