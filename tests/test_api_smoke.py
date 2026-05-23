"""Tests for the repeatable real API smoke runner."""

from __future__ import annotations

import json
import os
import unittest

from marketing_sandbox.api_smoke import (
    API_KEY_ENV,
    BASE_URL_ENV,
    DEFAULT_GROQ_BASE_URL,
    DEFAULT_GROQ_MODEL,
    MODEL_ENV,
    SmokeConfig,
    SmokeReport,
    SmokeStep,
    build_minimal_live_payload,
    run_failure_scenarios,
    run_smoke_suite,
)


class ApiSmokeTests(unittest.TestCase):
    def setUp(self):
        self._saved_env = {
            key: os.environ.get(key)
            for key in (BASE_URL_ENV, MODEL_ENV, API_KEY_ENV)
        }
        for key in self._saved_env:
            os.environ.pop(key, None)

    def tearDown(self):
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_normal_env_config_defaults_to_recommended_low_cost_profile(self):
        config = SmokeConfig.from_env()

        self.assertEqual(config.base_url, DEFAULT_GROQ_BASE_URL)
        self.assertEqual(config.model, DEFAULT_GROQ_MODEL)
        self.assertFalse(config.has_real_credentials)

    def test_normal_minimal_live_payload_uses_one_round_one_persona_and_ucb(self):
        payload = build_minimal_live_payload(
            SmokeConfig(api_key="session-secret"),
            run_id="class-smoke",
        )

        self.assertEqual(payload["runId"], "class-smoke")
        self.assertEqual(payload["roundCount"], 1)
        self.assertEqual(payload["personaIds"], ["value-pragmatist"])
        self.assertEqual(payload["search"]["rounds"], 1)
        self.assertEqual(payload["search"]["candidatesPerRound"], 1)
        self.assertEqual(payload["search"]["useUcb"], True)
        self.assertNotIn("session-secret", json.dumps(SmokeConfig(api_key="session-secret").safe_summary()))

    def test_boundary_safe_summary_never_echoes_api_key(self):
        summary = SmokeConfig(api_key="secret-value", archive_root="tmp").safe_summary()

        self.assertEqual(summary["apiKeyPresent"], True)
        self.assertNotIn("secret-value", json.dumps(summary))

    def test_boundary_no_real_flag_runs_local_scenarios_and_skips_provider(self):
        report = run_smoke_suite(SmokeConfig(), run_real=False)
        skipped = [step for step in report.steps if step.name == "real_provider_smoke"]

        self.assertTrue(report.ok)
        self.assertEqual(skipped[0].status, "skipped")

    def test_special_failure_suite_covers_all_documented_failure_paths(self):
        steps = run_failure_scenarios()
        names = {step.name for step in steps}

        self.assertTrue(all(step.ok for step in steps), [step.public_payload() for step in steps])
        self.assertIn("failure_wrong_key", names)
        self.assertIn("failure_wrong_model", names)
        self.assertIn("failure_bad_base_url", names)
        self.assertIn("failure_runtime_provider_error", names)
        self.assertIn("failure_path_user_stop", names)
        self.assertIn("failure_path_archive_after_stop", names)
        self.assertIn("failure_path_resume_plan_after_archive", names)

    def test_special_env_overrides_route_but_not_key_output(self):
        os.environ[BASE_URL_ENV] = "https://provider.example/v1"
        os.environ[MODEL_ENV] = "tiny-model"
        os.environ[API_KEY_ENV] = "env-secret"

        config = SmokeConfig.from_env()

        self.assertTrue(config.has_real_credentials)
        self.assertEqual(config.base_url, "https://provider.example/v1")
        self.assertEqual(config.model, "tiny-model")
        self.assertNotIn("env-secret", json.dumps(config.safe_summary()))

    def test_counterexample_real_smoke_without_credentials_fails_openly(self):
        report = run_smoke_suite(SmokeConfig(api_key=""), run_real=True)
        final_step = report.steps[-1]

        self.assertFalse(report.ok)
        self.assertEqual(final_step.status, "missing_credentials")
        self.assertIn(API_KEY_ENV, final_step.message)

    def test_counterexample_failure_steps_keep_known_secret_redacted(self):
        steps = run_failure_scenarios()
        serialized = json.dumps([step.public_payload() for step in steps], ensure_ascii=False)

        self.assertNotIn("bad-secret", serialized)
        self.assertNotIn("runtime-secret", serialized)

    def test_limit_report_payload_is_json_serializable(self):
        report = SmokeReport(
            real_run_requested=False,
            provider={"apiKeyPresent": False},
            steps=[
                SmokeStep(
                    name="example",
                    ok=True,
                    status="ok",
                    message="done",
                    details={"eventCount": 3},
                )
            ],
        )

        payload = report.public_payload()
        self.assertEqual(json.loads(json.dumps(payload))["steps"][0]["details"]["eventCount"], 3)

    def test_limit_payload_does_not_expand_beyond_minimal_real_smoke_scope(self):
        payload = build_minimal_live_payload(SmokeConfig(api_key="session-secret"))

        self.assertLessEqual(len(payload["personaIds"]), 1)
        self.assertEqual(payload["search"]["rounds"], 1)
        self.assertEqual(payload["search"]["candidatesPerRound"], 1)


if __name__ == "__main__":
    unittest.main()
