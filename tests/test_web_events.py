"""Tests for mapping completed sandbox runs into browser event payloads."""

from __future__ import annotations

import json
import math
import unittest

from marketing_sandbox import (
    AdvocacyReaction,
    BehaviorDiagnosis,
    CompetitorReaction,
    ConsumerFeedback,
    CriticSearchSignals,
    CritiqueReport,
    FamilyArmState,
    FeedbackSearchSignals,
    FeedbackSummary,
    RepeatPurchaseReaction,
    RewardBreakdown,
    RoundEvidence,
    RoundResult,
    SandboxResult,
    SandboxWebEventMapper,
    SearchBrief,
    SearchObservation,
    SearchSelection,
    SearchUpdate,
    Strategy,
    StrategyAction,
    StrategyFamily,
    StrategyProposal,
    StrategyTestResult,
    WEB_EVENT_CONTRACT,
    WEB_EVENT_CONTRACT_VERSION,
    WEB_EVENT_TYPES,
    WebEventMappingError,
)


def make_action(**changes):
    base = {
        "category": "promotion",
        "summary": "Use proof-led launch content.",
        "reason": "The strategy needs a clear first signal.",
        "parameters": {"content_focus": "proof-led"},
        "product_claims": (),
    }
    base.update(changes)
    return StrategyAction(**base)


def make_strategy(name="Trust-first trial", family_id="trust_risk_reduction", **changes):
    base = {
        "name": name,
        "hypothesis": "Reduce hesitation with trust proof before asking for repeat.",
        "actions": (make_action(),),
        "target_consumers": ("Trust-sensitive buyers",),
        "expected_tradeoffs": ("May move slower than a discount-led launch.",),
        "family_id": family_id,
        "family_fit_note": "This candidate lowers perceived risk before conversion.",
    }
    base.update(changes)
    return Strategy(**base)


def make_proposal(strategy=None, **changes):
    selected_strategy = strategy or make_strategy()
    base = {
        "decision_note": "Open the round with one auditable strategy.",
        "candidates": (selected_strategy,),
        "next_validation_question": "Does trust proof hold under competitor pressure?",
    }
    base.update(changes)
    return StrategyProposal(**base)


def make_feedback(persona_name="Value Pragmatist", scenario_name="Normal launch", **changes):
    base = {
        "persona_name": persona_name,
        "scenario_name": scenario_name,
        "first_impression": "The offer feels clearer than a noisy launch.",
        "understood_offer": "A proof-led first look at the product.",
        "perceived_positioning": "Careful and trying to be trustworthy.",
        "strongest_pull": "The message lowers comparison effort.",
        "strongest_rejection": "Repeat value is still not obvious.",
        "current_attitude": "Interested but waiting for experience.",
        "behavior_diagnosis": BehaviorDiagnosis(
            first_signal="The simple proof-led message.",
            reference_point="The familiar alternative already in mind.",
            perceived_risk="Product fit is not proven yet.",
            action_friction="Switching attention during comparison.",
            dominant_driver="Clarity under uncertainty.",
        ),
        "repeat_purchase": RepeatPurchaseReaction(
            feeling="Repeat choice is still conditional.",
            condition="First use confirms the message.",
            habit_or_inertia="Existing habits still hold an advantage.",
        ),
        "competitor_reaction": CompetitorReaction(
            likely_shift="A familiar competitor can still pull attention back.",
            reason="Familiarity lowers comparison effort.",
            retention_condition="Clear first experience and repeat reason.",
        ),
        "advocacy": AdvocacyReaction(
            recommendation_feeling="Recommendation waits for experience.",
            sharing_feeling="The message alone is not a sharing trigger.",
            friend_description="A careful product launch worth checking.",
        ),
        "behavior_notes": (
            "Reference point and attention limits mattered.",
            "Social proof did not dominate this first reaction.",
        ),
    }
    base.update(changes)
    return ConsumerFeedback(**base)


def make_feedback_signals(**changes):
    base = {
        "core_target_response": "mixed",
        "trial_momentum": "conditional",
        "strategy_clarity": "clear",
        "repeat_logic": "conditional",
        "competitor_resilience": "fragile",
        "evidence_consistency": "mixed",
        "signal_note": "The round clarified trial interest but repeat proof stayed thin.",
    }
    base.update(changes)
    return FeedbackSearchSignals(**base)


def make_critic_signals(**changes):
    base = {
        "product_boundary_risk": "contained",
        "brand_risk": "watch",
        "execution_risk": "contained",
        "self_deception_risk": "watch",
        "risk_note": "Readable feedback can flatter a weak repeat offer.",
    }
    base.update(changes)
    return CriticSearchSignals(**base)


def make_summary(strategy_name="Trust-first trial", **changes):
    base = {
        "strategy_name": strategy_name,
        "scenario_names": ("Normal launch",),
        "overall_feel": "This feels like a careful trust-first opening move.",
        "who_was_moved": ("Trust-sensitive buyers noticed lower message friction.",),
        "who_was_not_moved": ("Repeat-minded buyers still need stronger proof.",),
        "strongest_evidence": ("Consumers could restate the offer.",),
        "weakest_points": ("Repeat logic is still conditional.",),
        "repeat_purchase_feel": "Repeat depends on product experience and access.",
        "competitor_pressure_feel": "Competitor familiarity still presses on the offer.",
        "next_round_focus": ("Test repeat reason without bloating the message.",),
        "missing_evidence": ("Synthetic reactions do not prove real demand.",),
        "qualitative_tags": ("trust-first", "repeat still open"),
        "search_signals": make_feedback_signals(),
    }
    base.update(changes)
    return FeedbackSummary(**base)


def make_critique(strategy_name="Trust-first trial", **changes):
    base = {
        "strategy_name": strategy_name,
        "main_loopholes": ("Message clarity does not prove product fit.",),
        "unrealistic_assumptions": ("Attention may not become action on its own.",),
        "product_boundary_risks": ("Stay inside supplied product facts.",),
        "brand_risks": ("Do not make the brand generic while simplifying.",),
        "execution_risks": ("The message still needs a consistent touchpoint.",),
        "self_deception_checks": ("Readable feedback can flatter a weak offer.",),
        "must_validate_next": ("Validate repeat reason with outside evidence.",),
        "unresolved_questions": ("The round cannot settle real demand.",),
        "evidence_used": ("Consumers kept repeat value conditional.",),
        "search_risk_signals": make_critic_signals(),
    }
    base.update(changes)
    return CritiqueReport(**base)


def make_family(family_id="trust_risk_reduction"):
    return StrategyFamily(
        family_id=family_id,
        name="Trust risk reduction",
        core_barrier="Cautious buyers fear a bad first try.",
        win_mechanism="Reduce regret and product-fit risk before conversion.",
        generation_guidance="Lead with proof, support, and clear boundaries.",
        expected_action_patterns=("proof-led promotion", "support-backed product offer"),
        failure_signals=("trust collapses into generic reassurance",),
    )


def make_selection(family=None, round_index=1, score=math.inf):
    selected_family = family or make_family()
    brief = SearchBrief(
        selected_families=(selected_family,),
        generation_intents={selected_family.family_id: "cold_start"},
        qualitative_memory={
            selected_family.family_id: ("Prior qualitative note stayed text-only.",)
        },
    )
    return SearchSelection(
        round_index=round_index,
        brief=brief,
        selection_reasons={
            selected_family.family_id: "Cold-start coverage before exploitation."
        },
        ucb_scores={selected_family.family_id: score},
    )


def make_reward(**changes):
    base = {
        "reward": 0.72,
        "positive_utility": 0.84,
        "risk_penalty": 0.12,
        "positive_components": {"strategy_clarity": 0.15, "trial_momentum": 0.1},
        "risk_components": {"brand_risk": 0.04, "self_deception_risk": 0.08},
        "applied_caps": ("none",),
        "mapping_note": "Internal search utility only.",
    }
    base.update(changes)
    return RewardBreakdown(**base)


def make_observation(strategy=None, family_id="trust_risk_reduction", **changes):
    selected_strategy = strategy or make_strategy(family_id=family_id)
    base = {
        "round_index": 1,
        "family_id": family_id,
        "strategy_name": selected_strategy.name,
        "summary_signals": make_feedback_signals(),
        "critic_signals": make_critic_signals(),
        "reward_breakdown": make_reward(),
    }
    base.update(changes)
    return SearchObservation(**base)


def make_update(strategy=None, family_id="trust_risk_reduction"):
    observation = make_observation(strategy=strategy, family_id=family_id)
    before = FamilyArmState(family_id)
    after = before.add_observation(observation)
    return SearchUpdate(
        family_id=family_id,
        observation=observation,
        state_before=before,
        state_after=after,
    )


def make_round(
    round_index=1,
    *,
    with_search=True,
    strategy=None,
    feedbacks=None,
):
    selected_strategy = strategy or make_strategy()
    selected_feedbacks = feedbacks or (
        make_feedback("Value Pragmatist"),
        make_feedback("Trust First"),
    )
    summary = make_summary(selected_strategy.name)
    critique = make_critique(selected_strategy.name)
    update = make_update(selected_strategy, selected_strategy.family_id)
    strategy_test = StrategyTestResult(
        strategy=selected_strategy,
        consumer_feedbacks=selected_feedbacks,
        feedback_summary=summary,
        critique_report=critique,
        search_observation=update.observation if with_search else None,
    )
    family = make_family(selected_strategy.family_id)
    return RoundResult(
        round_index=round_index,
        proposal=make_proposal(selected_strategy),
        strategy_tests=(strategy_test,),
        next_round_evidence=RoundEvidence(
            consumer_feedback_summary="Consumers stayed interested but cautious.",
            feedback_synthesis="Trust proof helped, repeat proof stayed thin.",
            critique="The strategy still needs outside validation.",
        ),
        search_selection=make_selection(family, round_index) if with_search else None,
        search_updates=(update,) if with_search else (),
    )


def make_result(rounds=None, **changes):
    selected_rounds = rounds if rounds is not None else (make_round(),)
    base = {
        "rounds": selected_rounds,
        "recommended_strategy_directions": ("Keep testing trust-first proof.",),
        "paused_strategy_directions": ("Pause discount-only messaging.",),
        "audience_insights": ("Cautious buyers need proof before trial.",),
        "strategy_risks": ("Synthetic feedback does not prove real demand.",),
        "real_market_validation_questions": ("Can real buyers repeat without more discount?",),
        "decision_logic": ("Prefer directions with qualitative proof and contained risk.",),
        "family_search_trace": tuple(
            update
            for round_result in selected_rounds
            for update in round_result.search_updates
        ),
        "search_notes": ("Internal reward remains search utility only.",),
    }
    base.update(changes)
    return SandboxResult(**base)


class SandboxWebEventMapperTests(unittest.TestCase):
    def test_normal_result_emits_ordered_complete_event_sequence(self):
        events = SandboxWebEventMapper().map_result(make_result(), run_id="runA")

        self.assertEqual(events[0]["type"], "run_started")
        self.assertEqual(events[0]["contractVersion"], WEB_EVENT_CONTRACT_VERSION)
        self.assertEqual(events[-1]["type"], "run_completed")
        self.assertEqual(
            [event["type"] for event in events[1:-1]],
            [
                "round_started",
                "family_selected",
                "strategy_proposed",
                "consumer_feedback_ready",
                "consumer_feedback_ready",
                "feedback_summary_ready",
                "critique_ready",
                "search_updated",
                "round_completed",
            ],
        )
        self.assertTrue(all(event["id"].startswith("runA-") for event in events))

    def test_normal_event_contract_covers_all_browser_event_types(self):
        self.assertEqual(set(WEB_EVENT_CONTRACT), set(WEB_EVENT_TYPES))
        for event_type, contract in WEB_EVENT_CONTRACT.items():
            self.assertIn("category", contract)
            self.assertIn("requiredFields", contract)
            self.assertIn("purpose", contract)
            self.assertIn("id", contract["requiredFields"])
            self.assertIn("type", contract["requiredFields"])
            self.assertIn("round", contract["requiredFields"])

    def test_boundary_empty_result_still_emits_run_boundaries(self):
        result = make_result(rounds=())

        events = SandboxWebEventMapper().map_result(result, run_id="empty")

        self.assertEqual([event["type"] for event in events], ["run_started", "run_completed"])
        self.assertEqual(events[-1]["round"], 0)
        self.assertIn("No completed sandbox rounds", events[-1]["summary"])

    def test_boundary_round_progress_event_is_live_only_and_contract_safe(self):
        mapper = SandboxWebEventMapper()
        mapper.start_stream(run_id="progress")

        events = mapper.append_round_progress(
            round_index=1,
            expected_model_calls=13,
            persona_count=10,
            candidate_count=1,
        )

        self.assertEqual(events[0]["type"], "round_progress")
        self.assertEqual(events[0]["round"], 1)
        self.assertEqual(events[0]["progress"]["expectedModelCalls"], 13)
        self.assertIn("Provider-check", events[0]["progress"]["note"])

    def test_boundary_failed_stream_event_is_redacted_and_contract_safe(self):
        mapper = SandboxWebEventMapper(sensitive_values=("runtime-secret",))
        mapper.start_stream(run_id="failedrun")

        events = mapper.fail_stream(
            RuntimeError("provider failed with runtime-secret"),
            round_index=1,
            issue_kind="runtime_error",
        )

        self.assertEqual(events[0]["type"], "run_failed")
        self.assertEqual(events[0]["round"], 1)
        self.assertEqual(events[0]["issue"]["kind"], "runtime_error")
        self.assertIn("[redacted]", events[0]["issue"]["message"])
        self.assertNotIn("runtime-secret", repr(events))

    def test_boundary_map_round_omits_run_boundary_events(self):
        events = SandboxWebEventMapper().map_round(make_round(), run_id="single")

        self.assertEqual(events[0]["type"], "round_started")
        self.assertNotIn("run_started", {event["type"] for event in events})
        self.assertNotIn("run_completed", {event["type"] for event in events})

    def test_boundary_non_ucb_round_omits_family_and_search_events(self):
        events = SandboxWebEventMapper().map_round(
            make_round(with_search=False),
            run_id="oldpath",
        )

        event_types = {event["type"] for event in events}
        self.assertNotIn("family_selected", event_types)
        self.assertNotIn("search_updated", event_types)
        self.assertIn("strategy_proposed", event_types)

    def test_special_family_selection_preserves_labeled_ucb_score(self):
        family_event = next(
            event
            for event in SandboxWebEventMapper().map_round(make_round(), run_id="ucb")
            if event["type"] == "family_selected"
        )

        self.assertEqual(family_event["internalSearch"]["ucbScore"]["value"], None)
        self.assertEqual(
            family_event["internalSearch"]["ucbScore"]["display"],
            "cold start infinity",
        )
        self.assertIn("not a purchase rate", family_event["internalSearch"]["metricBoundary"])

    def test_special_search_update_preserves_reward_and_arm_state_metrics(self):
        search_event = next(
            event
            for event in SandboxWebEventMapper().map_round(make_round(), run_id="metrics")
            if event["type"] == "search_updated"
        )

        metrics = search_event["search"]["internalMetrics"]
        self.assertEqual(metrics["reward"], 0.72)
        self.assertEqual(metrics["positiveUtility"], 0.84)
        self.assertEqual(metrics["riskPenalty"], 0.12)
        self.assertEqual(metrics["stateBefore"]["meanReward"], 0.0)
        self.assertEqual(metrics["stateAfter"]["meanReward"], 0.72)
        self.assertIn("not market outcomes", metrics["metricBoundary"])

    def test_special_detailed_role_payloads_survive_mapping(self):
        events = SandboxWebEventMapper().map_round(make_round(), run_id="detail")
        feedback_event = next(event for event in events if event["type"] == "consumer_feedback_ready")
        summary_event = next(event for event in events if event["type"] == "feedback_summary_ready")
        critique_event = next(event for event in events if event["type"] == "critique_ready")

        self.assertEqual(
            feedback_event["feedback"]["behaviorDiagnosis"]["dominantDriver"],
            "Clarity under uncertainty.",
        )
        self.assertEqual(
            summary_event["synthesis"]["searchSignals"]["strategy_clarity"],
            "clear",
        )
        self.assertEqual(
            critique_event["critique"]["searchRiskSignals"]["brand_risk"],
            "watch",
        )

    def test_special_sensitive_values_are_redacted_recursively(self):
        secret = "session-secret"
        strategy = make_strategy(
            actions=(
                make_action(
                    parameters={
                        "content_focus": "proof-led",
                        "debug_secret": f"token:{secret}",
                    }
                ),
            )
        )
        result = make_result(rounds=(make_round(strategy=strategy),))

        payload = json.dumps(
            SandboxWebEventMapper(sensitive_values=(secret,)).map_result(result),
            sort_keys=True,
        )

        self.assertNotIn(secret, payload)
        self.assertIn("[redacted]", payload)

    def test_counterexample_invalid_run_id_is_rejected(self):
        with self.assertRaisesRegex(WebEventMappingError, "run_id"):
            SandboxWebEventMapper().map_result(make_result(), run_id="bad id!")

    def test_counterexample_wrong_result_type_is_rejected(self):
        with self.assertRaisesRegex(WebEventMappingError, "SandboxResult"):
            SandboxWebEventMapper().map_result({"rounds": []})

    def test_limit_many_rounds_keep_unique_event_ids(self):
        rounds = tuple(make_round(index, with_search=False) for index in range(1, 26))

        events = SandboxWebEventMapper().map_result(
            make_result(rounds=rounds),
            run_id="longrun",
        )

        ids = [event["id"] for event in events]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(events[-1]["round"], 25)


if __name__ == "__main__":
    unittest.main()
