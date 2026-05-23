"""Contract tests for CriticAgent."""

from __future__ import annotations

import copy
import unittest

from marketing_sandbox import (
    AdvocacyReaction,
    BehaviorDiagnosis,
    CompetitorReaction,
    ConsumerFeedback,
    CriticAgent,
    CriticContext,
    CriticInputError,
    CriticOutputError,
    FeedbackSummary,
    RepeatPurchaseReaction,
    Strategy,
    StrategyAction,
)


class RecordingBackend:
    """Stable critic backend used by contract tests."""

    def __init__(self, response):
        self.response = response
        self.prompts: list[str] = []

    def generate(self, prompt: str):
        self.prompts.append(prompt)
        return copy.deepcopy(self.response)


def make_strategy(**changes) -> Strategy:
    base = {
        "name": "Trust-first trial",
        "hypothesis": "Use reassurance and a first-trial offer.",
        "actions": (
            StrategyAction(
                category="product",
                summary="Use a trial pack with return support.",
                reason="Reduce first-use risk.",
                product_claims=("trial_pack",),
            ),
            StrategyAction(
                category="price",
                summary="Use a concrete launch offer.",
                reason="Make trial easy to understand.",
                parameters={"list_price": 49, "discount_rate": 0.1},
            ),
        ),
        "target_consumers": ("Trust-sensitive commuters",),
        "expected_tradeoffs": ("Repeat logic may remain thinner than first trial.",),
    }
    base.update(changes)
    return Strategy(**base)


def make_feedback(persona_name="Trust-sensitive commuter", **changes) -> ConsumerFeedback:
    base = {
        "persona_name": persona_name,
        "scenario_name": "Competitor trust pressure",
        "first_impression": "Practical and less risky than an unknown launch.",
        "understood_offer": "A bottled tea trial with reassurance.",
        "perceived_positioning": "Convenient and trying to look dependable.",
        "strongest_pull": "Trial support lowers first-use waste.",
        "strongest_rejection": "Repeat habit is still unclear.",
        "current_attitude": "Interested but cautious.",
        "behavior_diagnosis": BehaviorDiagnosis(
            first_signal="Trial support.",
            reference_point="A familiar bottled tea.",
            perceived_risk="Unknown taste and weak routine fit.",
            action_friction="Switching stores.",
            dominant_driver="Risk reduction.",
        ),
        "repeat_purchase": RepeatPurchaseReaction(
            feeling="Repeat does not feel automatic.",
            condition="Experience and reorder path must be smooth.",
            habit_or_inertia="Old drink habits still matter.",
        ),
        "competitor_reaction": CompetitorReaction(
            likely_shift="May drift back to a familiar competitor.",
            reason="Familiarity remains stronger there.",
            retention_condition="A dependable first experience.",
        ),
        "advocacy": AdvocacyReaction(
            recommendation_feeling="Recommendation waits on experience.",
            sharing_feeling="Not ready to share the offer alone.",
            friend_description="A careful new tea trial.",
        ),
        "behavior_notes": ("Reference point mattered.", "Trust remains conditional."),
    }
    base.update(changes)
    return ConsumerFeedback(**base)


def make_summary(**changes) -> FeedbackSummary:
    base = {
        "strategy_name": "Trust-first trial",
        "scenario_names": ("Competitor trust pressure",),
        "overall_feel": "A trust-aware trial strategy with weaker repeat logic.",
        "who_was_moved": ("Cautious trial seekers moved closer.",),
        "who_was_not_moved": ("Habit-bound buyers stayed unconvinced.",),
        "strongest_evidence": ("Trial support reduces hesitation.",),
        "weakest_points": ("Repeat reason is still thin.",),
        "repeat_purchase_feel": "Repeat depends on experience and convenience.",
        "competitor_pressure_feel": "Familiar competitors still expose a weak point.",
        "next_round_focus": ("Test repeat triggers before broadening reach.",),
        "missing_evidence": ("Synthetic feedback does not prove real demand.",),
        "qualitative_tags": ("trust-aware trial",),
    }
    base.update(changes)
    return FeedbackSummary(**base)


def make_context(**changes) -> CriticContext:
    base = {
        "product_boundaries": (
            "Do not claim health outcomes.",
            "Trial pack exists; subscription pack is not confirmed.",
        ),
        "brand_boundaries": (
            "The brand should not become bargain-only.",
        ),
        "execution_boundaries": (
            "Only one launch channel can be staffed well at first.",
        ),
        "known_facts": (
            "Consumer feedback is synthetic strategy feedback.",
        ),
    }
    base.update(changes)
    return CriticContext(**base)


def make_payload(**changes):
    base = {
        "main_loopholes": [
            "The strategy solves first trial more clearly than repeat choice."
        ],
        "unrealistic_assumptions": [
            "Reassurance cues may not substitute for a real usage reason."
        ],
        "product_boundary_risks": [
            "Do not stretch trial support into an unconfirmed product promise."
        ],
        "brand_risks": [
            "A price-led launch could flatten the trust positioning if overused."
        ],
        "execution_risks": [
            "The launch will wobble if reassurance content and channel support are scattered."
        ],
        "self_deception_checks": [
            "Synthetic interest from trial seekers may flatter the offer."
        ],
        "must_validate_next": [
            "Verify whether repeat triggers can stand without more promotion."
        ],
        "unresolved_questions": [
            "The round cannot prove the brand can hold trust after first use."
        ],
        "evidence_used": [
            "Feedback summary says repeat reason is thin.",
            "Brand boundary rejects bargain-only positioning.",
        ],
    }
    base.update(changes)
    return base


class CriticAgentTests(unittest.TestCase):
    def test_normal_critique_returns_boundary_aware_report(self):
        backend = RecordingBackend(make_payload())
        critic = CriticAgent(backend)

        report = critic.critique(
            make_strategy(), [make_feedback()], make_summary(), make_context()
        )

        self.assertEqual(report.strategy_name, "Trust-first trial")
        self.assertIn("repeat choice", report.main_loopholes[0])
        self.assertIn("Do not", backend.prompts[0])
        self.assertIn("one launch channel", backend.prompts[0])

    def test_boundary_minimum_optional_critic_context_is_allowed(self):
        backend = RecordingBackend(make_payload())
        critic = CriticAgent(backend)
        context = CriticContext(
            product_boundaries=("Stay within existing product facts.",),
            brand_boundaries=("Do not damage the brand.",),
        )

        report = critic.critique(
            make_strategy(), [make_feedback()], make_summary(), context
        )

        self.assertEqual(report.brand_risks[0], make_payload()["brand_risks"][0])
        self.assertIn("none supplied", backend.prompts[0])

    def test_boundary_single_feedback_and_single_summary_scenario_work(self):
        critic = CriticAgent(RecordingBackend(make_payload()))

        report = critic.critique(
            make_strategy(), (make_feedback(),), make_summary(), make_context()
        )

        self.assertEqual(len(report.evidence_used), 2)

    def test_boundary_numeric_decision_actions_are_context_not_forecasts(self):
        backend = RecordingBackend(make_payload())
        critic = CriticAgent(backend)

        critic.critique(make_strategy(), [make_feedback()], make_summary(), make_context())

        self.assertIn('"discount_rate": 0.1', backend.prompts[0])
        self.assertIn('"list_price": 49', backend.prompts[0])

    def test_special_product_boundary_and_summary_weakness_reach_prompt(self):
        backend = RecordingBackend(make_payload())
        critic = CriticAgent(backend)

        critic.critique(
            make_strategy(),
            [make_feedback()],
            make_summary(weakest_points=("Product reassurance risks overclaiming.",)),
            make_context(product_boundaries=("Do not add a subscription pack yet.",)),
        )

        prompt = backend.prompts[0]
        self.assertIn("overclaiming", prompt)
        self.assertIn("subscription pack", prompt)

    def test_special_conflicting_feedback_reaches_prompt(self):
        backend = RecordingBackend(make_payload())
        critic = CriticAgent(backend)
        explorer = make_feedback(
            "Price-aware explorer",
            strongest_pull="The launch offer feels easy to try.",
            strongest_rejection="The story feels ordinary once price is removed.",
        )

        critic.critique(
            make_strategy(),
            [make_feedback(), explorer],
            make_summary(),
            make_context(),
        )

        self.assertIn("ordinary once price is removed", backend.prompts[0])

    def test_special_self_deception_checks_remain_distinct(self):
        payload = make_payload(
            self_deception_checks=[
                "Do not treat a tidy synthetic summary as field evidence.",
                "Do not assume initial curiosity means a stable brand role.",
            ]
        )
        critic = CriticAgent(RecordingBackend(payload))

        report = critic.critique(
            make_strategy(), [make_feedback()], make_summary(), make_context()
        )

        self.assertIn("field evidence", report.self_deception_checks[0])
        self.assertIn("stable brand role", report.self_deception_checks[1])

    def test_counterexample_rejects_risk_probability_text(self):
        payload = make_payload(
            brand_risks=["Risk probability rises if the story leans on discounting."]
        )
        critic = CriticAgent(RecordingBackend(payload))

        with self.assertRaisesRegex(CriticOutputError, "probability, loss"):
            critic.critique(make_strategy(), [make_feedback()], make_summary(), make_context())

    def test_counterexample_rejects_profit_forecast_field(self):
        payload = make_payload()
        payload["profit_forecast"] = "not allowed"
        critic = CriticAgent(RecordingBackend(payload))

        with self.assertRaisesRegex(CriticOutputError, "forecast or probability field"):
            critic.critique(make_strategy(), [make_feedback()], make_summary(), make_context())

    def test_counterexample_rejects_consumer_feedback_field(self):
        payload = make_payload()
        payload["first_impression"] = "I would buy it."
        critic = CriticAgent(RecordingBackend(payload))

        with self.assertRaisesRegex(CriticOutputError, "consumer-feedback field"):
            critic.critique(make_strategy(), [make_feedback()], make_summary(), make_context())

    def test_counterexample_rejects_summary_for_other_strategy(self):
        critic = CriticAgent(RecordingBackend(make_payload()))

        with self.assertRaisesRegex(CriticInputError, "must match"):
            critic.critique(
                make_strategy(),
                [make_feedback()],
                make_summary(strategy_name="Other strategy"),
                make_context(),
            )

    def test_limit_dense_feedback_and_boundaries_still_build_critique(self):
        feedbacks = [
            make_feedback(
                f"Persona {index}",
                strongest_rejection=f"Tension {index} remains unresolved.",
            )
            for index in range(180)
        ]
        context = make_context(
            known_facts=tuple(f"Known fact {index}" for index in range(140))
        )
        backend = RecordingBackend(make_payload())
        critic = CriticAgent(backend)

        report = critic.critique(make_strategy(), feedbacks, make_summary(), context)

        self.assertIn("first trial", report.main_loopholes[0])
        self.assertIn("Persona 179", backend.prompts[0])
        self.assertIn("Known fact 139", backend.prompts[0])

    def test_ucb_risk_signals_are_parsed_as_categorical_labels(self):
        payload = make_payload(
            search_risk_signals={
                "product_boundary_risk": "watch",
                "brand_risk": "contained",
                "execution_risk": "watch",
                "self_deception_risk": "serious",
                "risk_note": "Synthetic curiosity still needs pressure testing.",
            }
        )
        critic = CriticAgent(RecordingBackend(payload))

        report = critic.critique(
            make_strategy(), [make_feedback()], make_summary(), make_context()
        )

        self.assertEqual(report.search_risk_signals.self_deception_risk, "serious")
        self.assertIn("search_risk_signals", critic.last_prompt)

    def test_ucb_risk_signals_reject_unknown_label(self):
        payload = make_payload(
            search_risk_signals={
                "product_boundary_risk": "watch",
                "brand_risk": "contained",
                "execution_risk": "urgent",
                "self_deception_risk": "watch",
                "risk_note": "Risk labels stay controlled.",
            }
        )
        critic = CriticAgent(RecordingBackend(payload))

        with self.assertRaisesRegex(CriticOutputError, "must use one of"):
            critic.critique(
                make_strategy(), [make_feedback()], make_summary(), make_context()
            )

    def test_ucb_risk_note_still_rejects_forecast_text(self):
        payload = make_payload(
            search_risk_signals={
                "product_boundary_risk": "watch",
                "brand_risk": "contained",
                "execution_risk": "watch",
                "self_deception_risk": "watch",
                "risk_note": "This implies a profit forecast.",
            }
        )
        critic = CriticAgent(RecordingBackend(payload))

        with self.assertRaisesRegex(CriticOutputError, "forecast"):
            critic.critique(
                make_strategy(), [make_feedback()], make_summary(), make_context()
            )


if __name__ == "__main__":
    unittest.main()
