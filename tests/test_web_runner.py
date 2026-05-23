"""Tests for the minimal web runner that assembles live sandbox objects."""

from __future__ import annotations

import copy
import unittest

from marketing_sandbox import (
    DEFAULT_CONSUMER_PERSONA_BY_ID,
    MarketingSandbox,
    Persona,
    Scenario,
    WebRunnerError,
    WebRunSession,
    WebSandboxRunner,
)


SESSION_KEY = "runner-session-secret"


class RecordingBackend:
    """Fixed fake LLM backend that records prompts from one role."""

    def __init__(self, response):
        self.response = response
        self.prompts: list[str] = []

    def generate(self, prompt: str):
        self.prompts.append(prompt)
        return copy.deepcopy(self.response)


class RecordingBackendFactory:
    """Build fixed role backends and retain role/model assembly calls."""

    def __init__(self):
        self.calls: list[dict[str, object]] = []
        self.backends: list[RecordingBackend] = []

    def __call__(self, *, role, model, session, persona):
        self.calls.append(
            {
                "role": role,
                "model": model,
                "credential_source": session.credential_source,
                "persona": getattr(persona, "name", None),
                "session_snapshot": session.public_snapshot(),
            }
        )
        backend = RecordingBackend(role_payload(role))
        self.backends.append(backend)
        return backend


def role_payload(role):
    if role == "decision":
        return {
            "decision_note": "Start with one clear non-numeric marketing move.",
            "candidates": [
                {
                    "name": "Clarity launch",
                    "hypothesis": "A simple launch story keeps the first test legible.",
                    "target_consumers": ["Selected web personas"],
                    "expected_tradeoffs": ["The first round keeps price detail out."],
                    "actions": [
                        {
                            "category": "product",
                            "summary": "Keep the product proof bounded to supplied facts.",
                            "reason": "The runner test opens the Product action category.",
                            "parameters": {"proof_focus": "supplied-facts"},
                            "product_claims": [],
                        },
                        {
                            "category": "promotion",
                            "summary": "Use a concise proof-led launch message.",
                            "reason": "The runner test needs an allowed marketing action.",
                            "parameters": {"content_focus": "proof-led"},
                            "product_claims": [],
                        }
                    ],
                }
            ],
            "next_validation_question": "Does the message stay clear under pressure?",
        }
    if role == "consumers":
        return {
            "first_impression": "The offer is easier to parse than a noisy launch.",
            "understood_offer": "A proof-led first look at the product.",
            "perceived_positioning": "Careful and trying to be understandable.",
            "strongest_pull": "The message asks for attention without too much hassle.",
            "strongest_rejection": "Repeat value is not visible yet.",
            "current_attitude": "Interested but still waiting for experience.",
            "behavior_diagnosis": {
                "first_signal": "The simple launch message.",
                "reference_point": "The familiar alternative already in mind.",
                "perceived_risk": "The product fit is not proven yet.",
                "action_friction": "Switching attention during comparison.",
                "dominant_driver": "Clarity under uncertainty.",
            },
            "repeat_purchase": {
                "feeling": "Repeat choice is still conditional.",
                "condition": "First use confirms the message and repeat access is easy.",
                "habit_or_inertia": "Existing habits still hold an advantage.",
            },
            "competitor_reaction": {
                "likely_shift": "A familiar competitor can still pull attention back.",
                "reason": "Familiarity lowers comparison effort.",
                "retention_condition": "A clear first experience and repeat reason.",
            },
            "advocacy": {
                "recommendation_feeling": "Recommendation waits for experience.",
                "sharing_feeling": "The message alone is not a sharing trigger.",
                "friend_description": "A careful product launch worth checking.",
            },
            "behavior_notes": [
                "Reference point and attention limits mattered.",
                "Social proof did not dominate this first reaction.",
            ],
        }
    if role == "synthesizer":
        return {
            "overall_feel": "This feels like a clarity-first opening move.",
            "who_was_moved": ["Selected personas noticed the lower message friction."],
            "who_was_not_moved": ["Repeat-minded comparison still lacks proof."],
            "strongest_evidence": ["Consumers could restate the opening offer."],
            "weakest_points": ["Repeat logic is still conditional."],
            "repeat_purchase_feel": "Repeat depends on product experience and access.",
            "competitor_pressure_feel": "Competitor familiarity still presses on the offer.",
            "next_round_focus": ["Test a repeat reason without bloating the message."],
            "missing_evidence": ["Synthetic reactions do not prove real demand."],
            "qualitative_tags": ["clarity-first", "repeat still open"],
        }
    if role == "critic":
        return {
            "main_loopholes": ["Message clarity does not prove product fit."],
            "unrealistic_assumptions": ["Attention may not become action on its own."],
            "product_boundary_risks": ["Stay inside supplied product facts."],
            "brand_risks": ["Do not make the brand generic while simplifying."],
            "execution_risks": ["The message still needs a consistent touchpoint."],
            "self_deception_checks": ["Readable feedback can flatter a weak offer."],
            "must_validate_next": ["Validate repeat reason with outside evidence."],
            "unresolved_questions": ["The round cannot settle real demand."],
            "evidence_used": ["Consumers kept repeat value conditional."],
        }
    raise AssertionError(f"Unexpected role: {role}")


def make_payload(**changes):
    payload = {
        "source": "live",
        "provider": {
            "id": "openai-compatible",
            "baseUrl": "https://provider.example/v1",
            "apiKey": SESSION_KEY,
            "useBackendDefaults": False,
            "defaultModel": "default-web-model",
        },
        "models": {
            "decision": "",
            "consumers": "",
            "synthesizer": "",
            "critic": "",
        },
        "product": {
            "name": "Web classroom product",
            "brand": "Do not overclaim the brand voice.",
            "facts": "Known product facts and product boundaries come from the website.",
            "goal": "Search marketing directions that can be explained.",
        },
        "personaIds": ["value-pragmatist", "trust-first"],
        "scenarioId": "competitor-pressure",
        "actionCategories": ["Promotion", "Product"],
        "search": {
            "useUcb": False,
            "rounds": 2,
            "candidatesPerRound": 1,
            "familyIds": [],
        },
    }
    payload.update(changes)
    return payload


def make_session(payload=None):
    return WebRunSession.from_frontend_payload(
        "runner-session",
        payload or make_payload(),
    )


class WebSandboxRunnerTests(unittest.TestCase):
    def test_normal_live_runner_builds_and_runs_one_fake_backend_round(self):
        factory = RecordingBackendFactory()
        runner = WebSandboxRunner(factory)

        result = runner.run(make_session(), round_count=1)

        self.assertEqual(len(result.rounds), 1)
        self.assertEqual(result.recommended_strategy_directions, ("Clarity launch",))
        self.assertEqual(len(result.rounds[0].consumer_feedbacks), 2)
        self.assertEqual({call["role"] for call in factory.calls}, {
            "decision",
            "consumers",
            "synthesizer",
            "critic",
        })

    def test_boundary_one_persona_and_one_action_category_still_assemble(self):
        payload = make_payload(
            personaIds=["value-pragmatist"],
            actionCategories=["Promotion"],
            scenarioId="normal",
        )
        runner = WebSandboxRunner(RecordingBackendFactory())

        sandbox = runner.build_sandbox(make_session(payload))

        self.assertIsInstance(sandbox, MarketingSandbox)
        self.assertEqual(len(sandbox.consumer_agents), 1)
        self.assertEqual(sandbox.action_space.allowed_categories, frozenset({"promotion"}))

    def test_boundary_web_action_space_adds_default_numeric_limits_for_selected_categories(self):
        payload = make_payload(actionCategories=["Price", "Promotion"])
        runner = WebSandboxRunner(RecordingBackendFactory())

        sandbox = runner.build_sandbox(make_session(payload))

        self.assertEqual(
            sandbox.action_space.parameter_limits["price"]["duration_weeks"],
            (1, 52),
        )
        self.assertEqual(
            sandbox.action_space.parameter_limits["price"]["price_USD"],
            (0, 10000),
        )
        self.assertEqual(
            sandbox.action_space.parameter_limits["promotion"]["content_budget"],
            (0, 1000000),
        )
        self.assertNotIn("retention", sandbox.action_space.parameter_limits)

    def test_boundary_backend_default_session_builds_without_browser_key(self):
        payload = make_payload(
            provider={
                "id": "openai-compatible",
                "baseUrl": "",
                "apiKey": "",
                "useBackendDefaults": True,
                "defaultModel": "backend-routed-model",
            }
        )
        factory = RecordingBackendFactory()
        runner = WebSandboxRunner(factory)

        runner.build_sandbox(make_session(payload))

        self.assertTrue(factory.calls)
        self.assertTrue(
            all(call["credential_source"] == "backend_defaults" for call in factory.calls)
        )

    def test_boundary_role_routes_work_when_default_model_is_empty(self):
        payload = make_payload(
            provider={
                "id": "openai-compatible",
                "baseUrl": "https://provider.example/v1",
                "apiKey": SESSION_KEY,
                "useBackendDefaults": False,
                "defaultModel": "",
            },
            models={
                "decision": "planner-model",
                "consumers": "persona-model",
                "synthesizer": "summary-model",
                "critic": "critic-model",
            },
        )
        factory = RecordingBackendFactory()
        runner = WebSandboxRunner(factory)

        runner.build_sandbox(make_session(payload))

        routes = {(call["role"], call["model"]) for call in factory.calls}
        self.assertIn(("decision", "planner-model"), routes)
        self.assertIn(("consumers", "persona-model"), routes)
        self.assertIn(("critic", "critic-model"), routes)

    def test_special_ucb_config_assembles_controller_and_reward_mapper(self):
        payload = make_payload(
            search={
                "useUcb": True,
                "rounds": 3,
                "candidatesPerRound": 1,
                "familyIds": ["trial_value_entry", "trust_risk_reduction"],
            }
        )
        runner = WebSandboxRunner(RecordingBackendFactory())

        sandbox = runner.build_sandbox(make_session(payload))

        self.assertIsNotNone(sandbox.search_controller)
        self.assertIsNotNone(sandbox.reward_mapper)
        self.assertEqual(
            tuple(item.family_id for item in sandbox.search_controller.families),
            ("trial_value_entry", "trust_risk_reduction"),
        )

    def test_special_custom_persona_and_scenario_catalogs_extend_web_runner(self):
        custom_persona = DEFAULT_CONSUMER_PERSONA_BY_ID["value-pragmatist"]
        custom_scenario = Scenario("Campus pressure", "Classmates compare the offer.")
        payload = make_payload(
            personaIds=["campus-value"],
            scenarioId="campus-pressure",
        )
        runner = WebSandboxRunner(
            RecordingBackendFactory(),
            persona_catalog={"campus-value": custom_persona},
            scenario_catalog={"campus-pressure": custom_scenario},
        )

        sandbox = runner.build_sandbox(make_session(payload))

        self.assertEqual(sandbox.consumer_agents[0].persona.name, custom_persona.name)
        self.assertEqual(sandbox.scenarios, (custom_scenario,))

    def test_special_consumer_backend_factory_receives_persona_and_safe_snapshot(self):
        factory = RecordingBackendFactory()
        runner = WebSandboxRunner(factory)

        runner.build_sandbox(make_session())

        consumer_calls = [call for call in factory.calls if call["role"] == "consumers"]
        self.assertEqual(len(consumer_calls), 2)
        self.assertTrue(all(call["persona"] for call in consumer_calls))
        self.assertNotIn(SESSION_KEY, repr(factory.calls))

    def test_counterexample_fixture_playback_session_does_not_use_live_runner(self):
        payload = make_payload(source="fixture")
        runner = WebSandboxRunner(RecordingBackendFactory())

        with self.assertRaisesRegex(WebRunnerError, "Fixture playback"):
            runner.build_sandbox(make_session(payload))

    def test_counterexample_unknown_persona_id_stops_assembly(self):
        payload = make_payload(personaIds=["unknown-persona"])
        runner = WebSandboxRunner(RecordingBackendFactory())

        with self.assertRaisesRegex(WebRunnerError, "Unknown persona"):
            runner.build_sandbox(make_session(payload))

    def test_counterexample_unknown_strategy_family_stops_ucb_assembly(self):
        payload = make_payload(
            search={
                "useUcb": True,
                "rounds": 2,
                "candidatesPerRound": 1,
                "familyIds": ["unknown_family"],
            }
        )
        runner = WebSandboxRunner(RecordingBackendFactory())

        with self.assertRaisesRegex(WebRunnerError, "Unknown strategy family"):
            runner.build_sandbox(make_session(payload))

    def test_limit_many_catalog_personas_keep_runner_assembly_bounded(self):
        persona = DEFAULT_CONSUMER_PERSONA_BY_ID["trust-first"]
        persona_ids = [f"coverage-{index}" for index in range(70)]
        payload = make_payload(personaIds=persona_ids)
        factory = RecordingBackendFactory()
        runner = WebSandboxRunner(
            factory,
            persona_catalog={persona_id: persona for persona_id in persona_ids},
        )

        sandbox = runner.build_sandbox(make_session(payload))

        self.assertEqual(len(sandbox.consumer_agents), 70)
        self.assertEqual(
            len([call for call in factory.calls if call["role"] == "consumers"]),
            70,
        )
        self.assertNotIn(SESSION_KEY, repr(factory.calls))


if __name__ == "__main__":
    unittest.main()
