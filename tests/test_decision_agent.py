"""Contract tests for DecisionAgent.

The test names mirror PROJECT_RULES.md:
- one normal sample
- three boundary samples
- three special samples
- counterexamples
- one limit sample
"""

from __future__ import annotations

import copy
import unittest

from marketing_sandbox import (
    ActionSpaceSpec,
    DecisionAgent,
    DecisionContext,
    DecisionInputError,
    DecisionOutputError,
    RoundEvidence,
    SearchBrief,
    StrategyFamily,
)


class RecordingBackend:
    """Stable test backend that records every DecisionAgent prompt."""

    def __init__(self, response):
        self.response = response
        self.prompts: list[str] = []

    def generate(self, prompt: str):
        self.prompts.append(prompt)
        return copy.deepcopy(self.response)


class QueueBackend:
    """Test backend that returns one response per DecisionAgent call."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts: list[str] = []

    def generate(self, prompt: str):
        self.prompts.append(prompt)
        if not self.responses:
            raise AssertionError("QueueBackend received too many calls.")
        return copy.deepcopy(self.responses.pop(0))


def make_context(**changes) -> DecisionContext:
    base = {
        "product_facts": (
            "Cold-brew tea exists as a ready-to-drink bottle.",
            "The current product supports trial packs and return guarantees.",
        ),
        "marketing_objectives": (
            "Find a defendable first-round acquisition strategy.",
        ),
        "brand_boundaries": ("Do not promise medical outcomes.",),
        "market_facts": ("Target users compare convenience and trust.",),
        "competitor_facts": ("Competitors already use social proof heavily.",),
        "target_personas": ("Trust-sensitive commuters", "Price-aware explorers"),
        "scenarios": ("Normal launch", "Competitor trust pressure"),
        "tested_strategies": (),
    }
    base.update(changes)
    return DecisionContext(**base)


def make_action_space(**changes) -> ActionSpaceSpec:
    default_limits = {
        "price": {
            "list_price": (0, 100),
            "discount_rate": (0, 0.3),
            "coupon_value": (0, 30),
        },
        "promotion": {"content_budget": (0, 5000)},
    }
    base = {
        "allowed_categories": frozenset({"price"}),
        "allowed_product_claims": frozenset(
            {"trial_pack", "return_guarantee", "portable_bottle"}
        ),
    }
    base.update(changes)
    if "parameter_limits" not in changes:
        base["parameter_limits"] = {
            category: limits
            for category, limits in default_limits.items()
            if category in base["allowed_categories"]
        }
    return ActionSpaceSpec(**base)


def make_action(category="price", **changes):
    base = {
        "category": category,
        "summary": "Lower first-trial friction with an explicit launch offer.",
        "reason": "The strategy needs a concrete action to test.",
        "parameters": {"list_price": 49, "discount_rate": 0.1}
        if category == "price"
        else {},
        "product_claims": [],
    }
    base.update(changes)
    return base


def make_candidate(name="Trust-first trial", **changes):
    base = {
        "name": name,
        "hypothesis": "Lower risk while keeping a trustworthy product story.",
        "target_consumers": ["Trust-sensitive commuters"],
        "expected_tradeoffs": ["The offer may attract fewer bargain-only users."],
        "actions": [make_action()],
    }
    base.update(changes)
    return base


def make_payload(**changes):
    base = {
        "decision_note": "Test a concrete offer before widening the channel mix.",
        "candidates": [make_candidate()],
        "next_validation_question": "Does the offer reduce hesitation without weakening trust?",
    }
    base.update(changes)
    return base


def make_family(family_id="trust_risk_reduction"):
    return StrategyFamily(
        family_id=family_id,
        name="Trust risk reduction",
        core_barrier="Cautious buyers fear the first mistake.",
        win_mechanism="Reduce felt risk before widening the offer.",
        generation_guidance="Use bounded trust and trial actions.",
        expected_action_patterns=("product reassurance",),
        failure_signals=("trust becomes discount-only",),
    )


def make_search_brief(*families):
    chosen = families or (make_family(),)
    return SearchBrief(
        selected_families=tuple(chosen),
        generation_intents={item.family_id: "cold_start" for item in chosen},
    )


class DecisionAgentTests(unittest.TestCase):
    def test_normal_initial_proposal_keeps_numeric_price_action(self):
        backend = RecordingBackend(make_payload())
        agent = DecisionAgent(backend, make_action_space())

        proposal = agent.propose_initial_strategies(make_context())

        action = proposal.candidates[0].actions[0]
        self.assertEqual(action.category, "price")
        self.assertEqual(action.parameters["list_price"], 49)
        self.assertEqual(action.parameters["discount_rate"], 0.1)
        self.assertIn("numeric marketing actions", backend.prompts[0])

    def test_boundary_minimum_context_accepts_single_strategy(self):
        payload = make_payload(
            candidates=[
                make_candidate(
                    actions=[
                        make_action(
                            summary="Keep one bounded launch price action.",
                            parameters={"list_price": 20},
                        )
                    ]
                )
            ]
        )
        agent = DecisionAgent(RecordingBackend(payload), make_action_space())
        context = DecisionContext(
            product_facts=("A product fact.",),
            marketing_objectives=("One objective.",),
        )

        proposal = agent.propose_initial_strategies(context)

        self.assertEqual(len(proposal.candidates), 1)
        self.assertEqual(proposal.candidates[0].actions[0].parameters["list_price"], 20)

    def test_boundary_accepts_candidate_count_at_configured_maximum(self):
        payload = make_payload(
            candidates=[
                make_candidate("Trust"),
                make_candidate("Convenience"),
                make_candidate("Retention"),
            ]
        )
        agent = DecisionAgent(RecordingBackend(payload), make_action_space())

        proposal = agent.propose_initial_strategies(make_context())

        self.assertEqual([item.name for item in proposal.candidates], ["Trust", "Convenience", "Retention"])

    def test_boundary_accepts_numeric_parameters_on_action_limits(self):
        payload = make_payload(
            candidates=[
                make_candidate(
                    actions=[
                        make_action(
                            parameters={"list_price": 100, "discount_rate": 0.3}
                        )
                    ]
                )
            ]
        )
        agent = DecisionAgent(RecordingBackend(payload), make_action_space())

        proposal = agent.propose_initial_strategies(make_context())

        self.assertEqual(proposal.candidates[0].actions[0].parameters["list_price"], 100)
        self.assertEqual(proposal.candidates[0].actions[0].parameters["discount_rate"], 0.3)

    def test_special_revision_prompt_uses_feedback_synthesis_and_critique(self):
        backend = RecordingBackend(make_payload())
        agent = DecisionAgent(backend, make_action_space())
        evidence = RoundEvidence(
            consumer_feedback_summary="Explorers liked trial access; cautious buyers still hesitated.",
            feedback_synthesis="The strategy feels like a launch offer with weak repeat reasons.",
            critique="Do not solve trust only by increasing discounts.",
        )

        agent.revise_strategies(make_context(), evidence)

        prompt = backend.prompts[0]
        self.assertIn("Explorers liked trial access", prompt)
        self.assertIn("weak repeat reasons", prompt)
        self.assertIn("increasing discounts", prompt)

    def test_special_approved_product_claims_can_shape_product_actions(self):
        product_action = make_action(
            "product",
            summary="Offer a trial pack with an explicit return guarantee.",
            reason="Trial and reassurance target different hesitation points.",
            product_claims=["trial_pack", "return_guarantee"],
        )
        payload = make_payload(candidates=[make_candidate(actions=[product_action])])
        agent = DecisionAgent(
            RecordingBackend(payload),
            make_action_space(allowed_categories=frozenset({"product"})),
        )

        proposal = agent.propose_initial_strategies(make_context())

        self.assertEqual(
            proposal.candidates[0].actions[0].product_claims,
            ("trial_pack", "return_guarantee"),
        )

    def test_special_complex_candidate_can_mix_all_allowed_action_categories(self):
        actions = [
            make_action(
                "positioning",
                summary="Lead with everyday trust.",
                reason="The launch needs a clear role.",
            ),
            make_action(
                "product",
                summary="Use the portable bottle plus trial pack.",
                reason="The product shape supports commuting.",
                product_claims=["portable_bottle", "trial_pack"],
            ),
            make_action(
                "price",
                summary="Set a bounded first-trial offer.",
                reason="Price is a visible action.",
                parameters={"list_price": 45, "coupon_value": 5},
            ),
            make_action(
                "channel",
                summary="Use one trusted platform and one direct landing page.",
                reason="Keep the path understandable.",
            ),
            make_action(
                "promotion",
                summary="Use review-led content.",
                reason="Trust needs evidence.",
                parameters={"content_budget": 2500},
            ),
            make_action(
                "retention",
                summary="Send use reminders after trial.",
                reason="Repeat needs a trigger.",
            ),
        ]
        payload = make_payload(candidates=[make_candidate(actions=actions)])
        agent = DecisionAgent(
            RecordingBackend(payload),
            make_action_space(
                allowed_categories=frozenset(
                    {"positioning", "product", "price", "channel", "promotion", "retention"}
                )
            ),
        )

        proposal = agent.propose_initial_strategies(make_context())

        self.assertEqual(
            {item.category for item in proposal.candidates[0].actions},
            {"positioning", "product", "price", "channel", "promotion", "retention"},
        )

    def test_counterexample_rejects_action_outside_action_space(self):
        payload = make_payload(
            candidates=[
                make_candidate(
                    actions=[
                        make_action(
                            "finance",
                            summary="Issue a finance-only action.",
                            reason="This should not be in the marketing ActionSpace.",
                        )
                    ]
                )
            ]
        )
        agent = DecisionAgent(RecordingBackend(payload), make_action_space())

        with self.assertRaisesRegex(DecisionOutputError, "outside the ActionSpace"):
            agent.propose_initial_strategies(make_context())

    def test_counterexample_rejects_unapproved_product_claim(self):
        payload = make_payload(
            candidates=[
                make_candidate(
                    actions=[
                        make_action(
                            "product",
                            summary="Promise a cure feature.",
                            reason="This claim is not an input product fact.",
                            product_claims=["medical_cure"],
                        )
                    ]
                )
            ]
        )
        agent = DecisionAgent(
            RecordingBackend(payload),
            make_action_space(allowed_categories=frozenset({"product"})),
        )

        with self.assertRaisesRegex(DecisionOutputError, "unapproved product claims"):
            agent.propose_initial_strategies(make_context())

    def test_counterexample_rejects_market_result_prediction(self):
        payload = make_payload(
            candidates=[
                make_candidate(
                    hypothesis="Raise conversion rate by polishing the offer.",
                )
            ]
        )
        agent = DecisionAgent(RecordingBackend(payload), make_action_space())

        with self.assertRaisesRegex(DecisionOutputError, "market-result prediction"):
            agent.propose_initial_strategies(make_context())

    def test_counterexample_rejects_persona_mutation_payload(self):
        candidate = make_candidate()
        candidate["persona_updates"] = ["Make cautious buyers impulsive."]
        payload = make_payload(candidates=[candidate])
        agent = DecisionAgent(RecordingBackend(payload), make_action_space())

        with self.assertRaisesRegex(DecisionOutputError, "unsupported keys"):
            agent.propose_initial_strategies(make_context())

    def test_counterexample_rejects_result_forecast_hidden_in_parameters(self):
        action = make_action(parameters={"expected_conversion_rate": 0.4})
        payload = make_payload(candidates=[make_candidate(actions=[action])])
        agent = DecisionAgent(RecordingBackend(payload), make_action_space())

        with self.assertRaisesRegex(DecisionOutputError, "market-result prediction"):
            agent.propose_initial_strategies(make_context())

    def test_counterexample_rejects_unbounded_numeric_action_parameter(self):
        action = make_action(
            "channel",
            summary="Allocate an unsupported numeric channel action.",
            reason="Numeric actions need declared boundaries.",
            parameters={"budget_share": 0.5},
        )
        payload = make_payload(candidates=[make_candidate(actions=[action])])
        agent = DecisionAgent(
            RecordingBackend(payload),
            make_action_space(allowed_categories=frozenset({"channel"})),
        )

        with self.assertRaisesRegex(DecisionOutputError, "needs an ActionSpace limit"):
            agent.propose_initial_strategies(make_context())

    def test_counterexample_rejects_candidate_missing_allowed_action_category(self):
        agent = DecisionAgent(
            RecordingBackend(make_payload()),
            make_action_space(allowed_categories=frozenset({"price", "promotion"})),
        )

        with self.assertRaisesRegex(DecisionOutputError, "missing: promotion"):
            agent.propose_initial_strategies(make_context())

    def test_special_contract_repair_retry_can_fix_missing_action_category(self):
        valid_payload = make_payload(
            candidates=[
                make_candidate(
                    actions=[
                        make_action("price"),
                        make_action(
                            "promotion",
                            summary="Put a small proof-led launch budget behind the trial offer.",
                            reason="Promotion must concretely support the test without changing claims.",
                            parameters={"content_budget": 1000},
                        ),
                    ]
                )
            ]
        )
        backend = QueueBackend([make_payload(), valid_payload])
        agent = DecisionAgent(
            backend,
            make_action_space(allowed_categories=frozenset({"price", "promotion"})),
        )

        proposal = agent.propose_initial_strategies(make_context())

        self.assertEqual(len(backend.prompts), 2)
        self.assertEqual(proposal.candidates[0].name, "Trust-first trial")
        self.assertIn("Action coverage contract", backend.prompts[0])
        self.assertIn("Do not invent numeric keys", backend.prompts[0])
        self.assertIn("missing: promotion", backend.prompts[1])
        self.assertIn("Use only parameter keys listed by ActionSpace", backend.prompts[1])
        self.assertIn("Rejected response excerpt", backend.prompts[1])

    def test_counterexample_rejects_noop_action_language(self):
        action = make_action(
            "promotion",
            summary="No action for this category.",
            reason="Pause the category this round.",
            parameters={},
        )
        agent = DecisionAgent(
            RecordingBackend(make_payload(candidates=[make_candidate(actions=[action])])),
            make_action_space(allowed_categories=frozenset({"promotion"})),
        )

        with self.assertRaisesRegex(DecisionOutputError, "cannot pause"):
            agent.propose_initial_strategies(make_context())

    def test_limit_large_round_history_and_dense_evidence_remain_usable(self):
        tested = tuple(f"Prior qualitative direction {index}" for index in range(120))
        dense_feedback = " ".join(
            f"Segment {index} had a distinct hesitation." for index in range(180)
        )
        backend = RecordingBackend(make_payload())
        agent = DecisionAgent(backend, make_action_space())

        proposal = agent.revise_strategies(
            make_context(tested_strategies=tested),
            RoundEvidence(
                consumer_feedback_summary=dense_feedback,
                feedback_synthesis="Signals conflict across trust, price, and repeat triggers.",
                critique="Keep actions interpretable even under dense feedback.",
            ),
        )

        self.assertEqual(proposal.candidates[0].name, "Trust-first trial")
        self.assertIn("Prior qualitative direction 119", backend.prompts[0])
        self.assertGreater(len(backend.prompts[0]), len(dense_feedback))

    def test_input_rejects_revision_without_consumer_summary(self):
        agent = DecisionAgent(RecordingBackend(make_payload()), make_action_space())

        with self.assertRaisesRegex(DecisionInputError, "consumer feedback summary"):
            agent.revise_strategies(make_context(), RoundEvidence(" "))

    def test_ucb_family_brief_requires_and_preserves_candidate_family(self):
        candidate = make_candidate(
            family_id="trust_risk_reduction",
            family_fit_note="This strategy reduces first-use uncertainty.",
        )
        backend = RecordingBackend(make_payload(candidates=[candidate]))
        agent = DecisionAgent(backend, make_action_space())

        proposal = agent.propose_initial_strategies(
            make_context(),
            search_brief=make_search_brief(),
        )

        self.assertEqual(proposal.candidates[0].family_id, "trust_risk_reduction")
        self.assertIn("Family search brief", backend.prompts[0])
        self.assertIn("one candidate for each selected family", backend.prompts[0])

    def test_ucb_family_brief_rejects_candidate_without_family_id(self):
        agent = DecisionAgent(RecordingBackend(make_payload()), make_action_space())

        with self.assertRaisesRegex(DecisionOutputError, "family_id"):
            agent.propose_initial_strategies(
                make_context(),
                search_brief=make_search_brief(),
            )

    def test_ucb_family_brief_rejects_duplicate_family_candidates(self):
        payload = make_payload(
            candidates=[
                make_candidate(
                    "Trust A",
                    family_id="trust_risk_reduction",
                    family_fit_note="One trust variant.",
                ),
                make_candidate(
                    "Trust B",
                    family_id="trust_risk_reduction",
                    family_fit_note="A second trust variant.",
                ),
            ]
        )
        agent = DecisionAgent(RecordingBackend(payload), make_action_space())

        with self.assertRaisesRegex(DecisionOutputError, "repeats"):
            agent.propose_initial_strategies(
                make_context(),
                search_brief=make_search_brief(
                    make_family("trust_risk_reduction"),
                    make_family("trial_value_entry"),
                ),
            )

    def test_ucb_family_fit_note_cannot_hide_result_prediction(self):
        payload = make_payload(
            candidates=[
                make_candidate(
                    family_id="trust_risk_reduction",
                    family_fit_note="This family raises conversion rate.",
                )
            ]
        )
        agent = DecisionAgent(RecordingBackend(payload), make_action_space())

        with self.assertRaisesRegex(DecisionOutputError, "market-result prediction"):
            agent.propose_initial_strategies(
                make_context(),
                search_brief=make_search_brief(),
            )


if __name__ == "__main__":
    unittest.main()
