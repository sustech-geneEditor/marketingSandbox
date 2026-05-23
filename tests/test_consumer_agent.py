"""Contract tests for ConsumerAgent."""

from __future__ import annotations

import copy
import unittest

from marketing_sandbox import (
    ConsumerAgent,
    ConsumerInputError,
    ConsumerOutputError,
    DEFAULT_CONSUMER_PERSONAS,
    Persona,
    ProductContext,
    Scenario,
    Strategy,
    StrategyAction,
)


class RecordingBackend:
    """Stable consumer backend used by contract tests."""

    def __init__(self, response):
        self.response = response
        self.prompts: list[str] = []

    def generate(self, prompt: str):
        self.prompts.append(prompt)
        return copy.deepcopy(self.response)


def make_persona(**changes) -> Persona:
    base = {
        "name": "Trust-sensitive commuter",
        "core_need": "A convenient daily drink that does not feel risky.",
        "purchase_motivation": "Reliable convenience for a busy commute.",
        "current_alternative": "A familiar bottled tea from a platform store.",
        "price_sensitivity": "Not bargain-only, but notices first-trial cost.",
        "trust_sensitivity": "Needs believable product and service cues.",
        "promotion_sensitivity": "Offers help only when they do not feel cheap.",
        "channel_preference": "Trusted platform with quick delivery.",
        "social_influence": "Reads reviews before trying unknown brands.",
        "main_barrier": "Unknown quality and unclear repeat reason.",
        "repeat_trigger": "A smooth first experience plus easy reminder.",
        "switching_threshold": "Will switch if a familiar competitor is easier and safer.",
    }
    base.update(changes)
    return Persona(**base)


def make_strategy(**changes) -> Strategy:
    base = {
        "name": "Trust-first trial",
        "hypothesis": "Use reassurance and a bounded launch offer.",
        "actions": (
            StrategyAction(
                category="product",
                summary="Offer a trial pack with return support.",
                reason="Reduce first-use risk.",
                product_claims=("trial_pack",),
            ),
            StrategyAction(
                category="price",
                summary="Use a concrete launch price.",
                reason="Make the first move legible.",
                parameters={"list_price": 49, "discount_rate": 0.1},
            ),
        ),
        "target_consumers": ("Trust-sensitive commuters",),
        "expected_tradeoffs": ("The offer still needs repeat reasons.",),
    }
    base.update(changes)
    return Strategy(**base)


def make_scenario(**changes) -> Scenario:
    base = {
        "name": "Competitor trust pressure",
        "situation": "The launch is visible beside a familiar competitor.",
        "competitor_pressure": "The competitor feels more familiar.",
        "trust_pressure": "Reviews are visible but still early.",
        "friction_pressure": "The buyer wants a quick checkout path.",
    }
    base.update(changes)
    return Scenario(**base)


def make_product_context(**changes) -> ProductContext:
    base = {
        "facts": (
            "The tea is sold as a ready-to-drink bottle.",
            "A trial pack exists.",
        ),
        "brand_facts": ("The brand promises clear ingredient information.",),
        "competitor_facts": ("The leading competitor is familiar in convenience channels.",),
    }
    base.update(changes)
    return ProductContext(**base)


def make_payload(**changes):
    base = {
        "first_impression": "It feels practical and less risky than an unknown launch.",
        "understood_offer": "A trial-oriented bottled tea launch with reassurance.",
        "perceived_positioning": "Convenient but trying to look trustworthy.",
        "strongest_pull": "The trial pack and clear support lower the feeling of waste.",
        "strongest_rejection": "I still do not know whether it will become my routine.",
        "current_attitude": "Interested enough to consider trying, still cautious.",
        "behavior_diagnosis": {
            "first_signal": "The trial pack and return support.",
            "reference_point": "My familiar bottled tea alternative.",
            "perceived_risk": "An unknown taste and weak repeat habit.",
            "action_friction": "Switching from the store I already use.",
            "dominant_driver": "Risk reduction matters more than novelty here.",
        },
        "repeat_purchase": {
            "feeling": "Repeat purchase does not feel automatic yet.",
            "condition": "The first use is pleasant and the next order is convenient.",
            "habit_or_inertia": "My old drink habit still has momentum.",
        },
        "competitor_reaction": {
            "likely_shift": "I may drift back to the familiar competitor under pressure.",
            "reason": "Familiarity and convenience still work in its favor.",
            "retention_condition": "A trustworthy first experience plus an easy repeat path.",
        },
        "advocacy": {
            "recommendation_feeling": "I would wait for a good first experience.",
            "sharing_feeling": "I would not share just because of the launch offer.",
            "friend_description": "A practical new tea that is trying to make trial feel safe.",
        },
        "behavior_notes": [
            "Reference point and perceived risk clearly mattered.",
            "Social influence mattered only as review reassurance.",
        ],
    }
    base.update(changes)
    return base


class ConsumerAgentTests(unittest.TestCase):
    def test_normal_reaction_returns_qualitative_feedback(self):
        backend = RecordingBackend(make_payload())
        agent = ConsumerAgent(backend, make_persona())

        feedback = agent.react_to_strategy(
            make_strategy(), make_scenario(), make_product_context()
        )

        self.assertEqual(feedback.persona_name, "Trust-sensitive commuter")
        self.assertEqual(feedback.scenario_name, "Competitor trust pressure")
        self.assertIn("consider trying", feedback.current_attitude)
        self.assertIn("Behavioral priors", backend.prompts[0])

    def test_boundary_minimum_optional_context_still_reacts(self):
        backend = RecordingBackend(make_payload())
        agent = ConsumerAgent(backend, make_persona())
        scenario = Scenario(name="Normal launch", situation="The product is shown once.")
        context = ProductContext(facts=("A trial pack exists.",))

        feedback = agent.react_to_strategy(make_strategy(), scenario, context)

        self.assertEqual(feedback.scenario_name, "Normal launch")
        self.assertIn("none supplied", backend.prompts[0])

    def test_boundary_single_strategy_action_still_renders(self):
        strategy = make_strategy(
            actions=(
                StrategyAction(
                    category="promotion",
                    summary="Show one review-led message.",
                    reason="Keep the signal simple.",
                ),
            )
        )
        backend = RecordingBackend(make_payload())
        agent = ConsumerAgent(backend, make_persona())

        agent.react_to_strategy(strategy, make_scenario(), make_product_context())

        self.assertIn("Show one review-led message", backend.prompts[0])

    def test_boundary_numeric_decision_actions_are_visible_not_rejected(self):
        backend = RecordingBackend(make_payload())
        agent = ConsumerAgent(backend, make_persona())

        agent.react_to_strategy(make_strategy(), make_scenario(), make_product_context())

        self.assertIn('"discount_rate": 0.1', backend.prompts[0])
        self.assertIn('"list_price": 49', backend.prompts[0])

    def test_special_prompt_carries_social_and_habit_persona_traits(self):
        backend = RecordingBackend(make_payload())
        persona = make_persona(
            social_influence="Needs a friend's experience before trusting the claim.",
            repeat_trigger="A weekly commute reminder plus stable taste.",
        )
        agent = ConsumerAgent(backend, persona)

        agent.react_to_strategy(make_strategy(), make_scenario(), make_product_context())

        prompt = backend.prompts[0]
        self.assertIn("friend's experience", prompt)
        self.assertIn("weekly commute reminder", prompt)

    def test_special_default_catalog_exposes_ten_distinct_consumer_personas(self):
        agents = tuple(
            ConsumerAgent(RecordingBackend(make_payload()), persona)
            for persona in DEFAULT_CONSUMER_PERSONAS
        )

        self.assertEqual(len(agents), 10)
        self.assertEqual(len({agent.persona.name for agent in agents}), 10)
        self.assertIn("Outcome-focused optimizer", {agent.persona.name for agent in agents})
        self.assertIn("Occasion relationship buyer", {agent.persona.name for agent in agents})

    def test_special_competitor_pressure_reaches_prompt(self):
        backend = RecordingBackend(make_payload())
        scenario = make_scenario(
            competitor_pressure="A competitor is easier to grab during the commute.",
            trust_pressure="The competitor has deeper review history.",
        )
        agent = ConsumerAgent(backend, make_persona())

        agent.react_to_strategy(make_strategy(), scenario, make_product_context())

        self.assertIn("easier to grab", backend.prompts[0])
        self.assertIn("deeper review history", backend.prompts[0])

    def test_special_behavior_notes_preserve_active_and_inactive_priors(self):
        payload = make_payload(
            behavior_notes=[
                "Immediate friction mattered because the checkout path is unclear.",
                "Gift identity did not clearly matter in this commuter moment.",
            ]
        )
        agent = ConsumerAgent(RecordingBackend(payload), make_persona())

        feedback = agent.react_to_strategy(
            make_strategy(), make_scenario(), make_product_context()
        )

        self.assertIn("checkout path", feedback.behavior_notes[0])
        self.assertIn("did not clearly matter", feedback.behavior_notes[1])

    def test_counterexample_rejects_purchase_probability_text(self):
        payload = make_payload(current_attitude="My purchase probability feels high.")
        agent = ConsumerAgent(RecordingBackend(payload), make_persona())

        with self.assertRaisesRegex(ConsumerOutputError, "probability, score"):
            agent.react_to_strategy(make_strategy(), make_scenario(), make_product_context())

    def test_counterexample_rejects_numeric_score_field(self):
        payload = make_payload()
        payload["strategy_score"] = 8
        agent = ConsumerAgent(RecordingBackend(payload), make_persona())

        with self.assertRaisesRegex(ConsumerOutputError, "numeric judgement field"):
            agent.react_to_strategy(make_strategy(), make_scenario(), make_product_context())

    def test_counterexample_rejects_invented_acceptable_price_text(self):
        payload = make_payload(
            strongest_pull="My acceptable price would be a number I invented."
        )
        agent = ConsumerAgent(RecordingBackend(payload), make_persona())

        with self.assertRaisesRegex(ConsumerOutputError, "probability, score"):
            agent.react_to_strategy(make_strategy(), make_scenario(), make_product_context())

    def test_counterexample_rejects_market_share_nested_field(self):
        payload = make_payload()
        payload["advocacy"]["market_share"] = "looks promising"
        agent = ConsumerAgent(RecordingBackend(payload), make_persona())

        with self.assertRaisesRegex(ConsumerOutputError, "numeric judgement field"):
            agent.react_to_strategy(make_strategy(), make_scenario(), make_product_context())

    def test_counterexample_rejects_brand_manager_advice_key(self):
        payload = make_payload(marketing_advice="Spend more on coupons.")
        agent = ConsumerAgent(RecordingBackend(payload), make_persona())

        with self.assertRaisesRegex(ConsumerOutputError, "unsupported keys"):
            agent.react_to_strategy(make_strategy(), make_scenario(), make_product_context())

    def test_limit_dense_strategy_and_scenario_still_build_feedback_prompt(self):
        dense_actions = tuple(
            StrategyAction(
                category="promotion" if index % 2 else "channel",
                summary=f"Action {index} gives a distinct shopper cue.",
                reason="Stress a legal but dense message path.",
                parameters={"named_mode": f"mode-{index}"},
            )
            for index in range(140)
        )
        dense_strategy = make_strategy(actions=dense_actions)
        dense_scenario = make_scenario(
            situation=" ".join(
                f"Moment {index} adds a market cue." for index in range(160)
            )
        )
        backend = RecordingBackend(make_payload())
        agent = ConsumerAgent(backend, make_persona())

        feedback = agent.react_to_strategy(
            dense_strategy, dense_scenario, make_product_context()
        )

        self.assertEqual(feedback.perceived_positioning, "Convenient but trying to look trustworthy.")
        self.assertIn("Action 139", backend.prompts[0])
        self.assertGreater(len(backend.prompts[0]), len(dense_scenario.situation))

    def test_input_rejects_strategy_without_actions(self):
        agent = ConsumerAgent(RecordingBackend(make_payload()), make_persona())
        strategy = make_strategy(actions=())

        with self.assertRaisesRegex(ConsumerInputError, "named strategy with actions"):
            agent.react_to_strategy(strategy, make_scenario(), make_product_context())


if __name__ == "__main__":
    unittest.main()
