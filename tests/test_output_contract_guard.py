import unittest

from marketing_sandbox import (
    ActionSpace,
    AdvocacyReaction,
    BehaviorDiagnosis,
    CompetitorReaction,
    ConsumerFeedback,
    CritiqueReport,
    CriticSearchSignals,
    FeedbackSearchSignals,
    FeedbackSummary,
    OutputContractGuard,
    OutputContractViolation,
    RepeatPurchaseReaction,
    Strategy,
    StrategyAction,
    StrategyProposal,
)


def make_action_space(**changes):
    base = {
        "allowed_categories": frozenset({"product", "price"}),
        "allowed_product_claims": frozenset({"trial_pack", "return_guarantee"}),
        "parameter_limits": {
            "price": {"list_price": (0, 100), "discount_rate": (0, 0.3)},
        },
    }
    base.update(changes)
    return ActionSpace(**base)


def make_strategy(**changes):
    base = {
        "name": "Trust-first trial",
        "hypothesis": "Make first trial feel lower risk without faking demand.",
        "actions": (
            StrategyAction(
                category="product",
                summary="Use the confirmed trial pack with return support.",
                reason="Reduce first-use regret.",
                product_claims=("trial_pack", "return_guarantee"),
            ),
            StrategyAction(
                category="price",
                summary="Set one bounded launch offer.",
                reason="Make trial cost legible.",
                parameters={"list_price": 49, "discount_rate": 0.1},
            ),
        ),
        "target_consumers": ("Trust-sensitive commuters",),
        "expected_tradeoffs": ("Repeat reasons may remain weaker than trial cues.",),
    }
    base.update(changes)
    return Strategy(**base)


def make_proposal(**changes):
    base = {
        "decision_note": "Test the trust-and-trial direction before widening reach.",
        "candidates": (make_strategy(),),
        "next_validation_question": "Does the offer lower hesitation without weakening trust?",
    }
    base.update(changes)
    return StrategyProposal(**base)


def make_feedback(**changes):
    base = {
        "persona_name": "Trust-sensitive commuter",
        "scenario_name": "Competitor trust pressure",
        "first_impression": "It feels practical and cautious.",
        "understood_offer": "A trial-oriented drink with reassurance.",
        "perceived_positioning": "Convenient and trying to look dependable.",
        "strongest_pull": "Trial support lowers waste anxiety.",
        "strongest_rejection": "The repeat reason is still thin.",
        "current_attitude": "Interested but still careful.",
        "behavior_diagnosis": BehaviorDiagnosis(
            first_signal="Trial support.",
            reference_point="A familiar drink alternative.",
            perceived_risk="Unknown routine fit.",
            action_friction="Switching my usual store.",
            dominant_driver="Risk reduction.",
        ),
        "repeat_purchase": RepeatPurchaseReaction(
            feeling="Repeat does not feel automatic yet.",
            condition="The first use and reorder path need to be smooth.",
            habit_or_inertia="Old habits still matter.",
        ),
        "competitor_reaction": CompetitorReaction(
            likely_shift="I may drift toward the familiar option.",
            reason="Its convenience is already trusted.",
            retention_condition="A dependable first experience.",
        ),
        "advocacy": AdvocacyReaction(
            recommendation_feeling="I would wait for real experience.",
            sharing_feeling="The offer alone is not share-worthy.",
            friend_description="A careful new drink trial.",
        ),
        "behavior_notes": ("Reference points matter here.",),
    }
    base.update(changes)
    return ConsumerFeedback(**base)


def make_summary(**changes):
    base = {
        "strategy_name": "Trust-first trial",
        "scenario_names": ("Competitor trust pressure",),
        "overall_feel": "A careful trial strategy with thin repeat logic.",
        "who_was_moved": ("Cautious triers moved closer.",),
        "who_was_not_moved": ("Habit-bound buyers stayed unconvinced.",),
        "strongest_evidence": ("Trial support lowers felt risk.",),
        "weakest_points": ("Repeat logic is not natural yet.",),
        "repeat_purchase_feel": "Repeat depends on experience and convenience.",
        "competitor_pressure_feel": "Familiar competitors still expose a weak point.",
        "next_round_focus": ("Test repeat triggers.",),
        "missing_evidence": ("Synthetic feedback does not prove real demand.",),
        "qualitative_tags": ("trust-aware trial",),
    }
    base.update(changes)
    return FeedbackSummary(**base)


def make_critique(**changes):
    base = {
        "strategy_name": "Trust-first trial",
        "main_loopholes": ("First trial is clearer than the repeat reason.",),
        "unrealistic_assumptions": ("Reassurance may not replace routine fit.",),
        "product_boundary_risks": ("Do not stretch confirmed trial claims.",),
        "brand_risks": ("A discount-heavy voice could flatten trust.",),
        "execution_risks": ("Too many launch touchpoints may scatter support.",),
        "self_deception_checks": ("Synthetic curiosity can flatter the offer.",),
        "must_validate_next": ("Verify the repeat trigger.",),
        "unresolved_questions": ("The round cannot prove habit formation.",),
        "evidence_used": ("Feedback says routine fit stays uncertain.",),
    }
    base.update(changes)
    return CritiqueReport(**base)


class OutputContractGuardTests(unittest.TestCase):
    def test_normal_decision_proposal_allows_bounded_numeric_actions(self):
        result = OutputContractGuard().check_decision_proposal(
            make_proposal(), make_action_space()
        )

        self.assertTrue(result.accepted)
        self.assertEqual(result.issues, ())

    def test_boundary_consumer_text_can_quote_factual_product_numbers(self):
        feedback = make_feedback(
            understood_offer="A supplied 500 ml bottle fact makes the offer easier to picture."
        )

        result = OutputContractGuard().check_consumer_feedback(feedback)

        self.assertTrue(result.accepted)

    def test_boundary_summary_with_one_scenario_stays_qualitative(self):
        summary = make_summary(scenario_names=("Normal launch",))

        result = OutputContractGuard().check_feedback_summary(summary)

        self.assertTrue(result.accepted)
        self.assertEqual(result.role, "FeedbackSynthesizer")

    def test_boundary_critic_can_cite_known_numeric_fact_in_text(self):
        critique = make_critique(
            evidence_used=("Known execution fact: the launch cap is 3000.",)
        )

        result = OutputContractGuard().check_critique_report(critique)

        self.assertTrue(result.accepted)

    def test_special_decision_checks_product_claims_and_price_bounds_together(self):
        strategy = make_strategy(
            actions=make_strategy().actions
            + (
                StrategyAction(
                    category="promotion",
                    summary="Keep evidence content focused.",
                    reason="Trust claims need a clear carrier.",
                    parameters={"content_budget": 2500},
                ),
            )
        )

        result = OutputContractGuard().check(
            "decision_agent",
            make_proposal(candidates=(strategy,)),
            action_space=make_action_space(
                allowed_categories=frozenset({"product", "price", "promotion"}),
                parameter_limits={
                    "price": {"list_price": (0, 100), "discount_rate": (0, 0.3)},
                    "promotion": {"content_budget": (0, 5000)},
                },
            ),
        )

        self.assertTrue(result.accepted)
        self.assertEqual(result.role, "DecisionAgent")

    def test_special_consumer_nested_reactions_stay_in_consumer_voice(self):
        feedback = make_feedback(
            competitor_reaction=CompetitorReaction(
                likely_shift="A familiar competitor still tempts me.",
                reason="Habit and checkout ease reinforce each other.",
                retention_condition="A repeat path I can remember later.",
            ),
            behavior_notes=("Social proof is conditional in this scenario.",),
        )

        result = OutputContractGuard().check("consumer", feedback)

        self.assertTrue(result.accepted)

    def test_special_summary_alias_keeps_multi_pressure_context_qualitative(self):
        summary = make_summary(
            scenario_names=("Channel friction pressure", "Trust pressure wave 2"),
            strongest_evidence=("Pressure changes which hesitation becomes visible.",),
        )

        result = OutputContractGuard().check("feedback_synthesizer", summary)

        self.assertTrue(result.accepted)

    def test_counterexample_consumer_probability_requests_rewrite(self):
        feedback = make_feedback(current_attitude="My purchase probability feels high.")

        result = OutputContractGuard().check_consumer_feedback(feedback)

        self.assertTrue(result.rewrite_required)
        self.assertIn("consumer_numeric_judgement", {issue.code for issue in result.issues})
        self.assertIn("qualitative", result.rewrite_instruction)

    def test_counterexample_summary_fake_score_field_is_blocked_in_raw_payload(self):
        result = OutputContractGuard().check("summary", {"overall_score": 8})

        self.assertTrue(result.rewrite_required)
        self.assertIn("summary_forbidden_field", {issue.code for issue in result.issues})
        self.assertIn("role_output_type", {issue.code for issue in result.issues})

    def test_counterexample_critic_business_forecast_is_blocked(self):
        critique = make_critique(
            main_loopholes=("The profit forecast pretends the launch is proven.",)
        )

        result = OutputContractGuard().check_critique_report(critique)

        self.assertTrue(result.rewrite_required)
        self.assertIn("critic_forecast", {issue.code for issue in result.issues})

    def test_counterexample_decision_action_outside_action_space_is_blocked(self):
        strategy = make_strategy(
            actions=(
                StrategyAction(
                    category="channel",
                    summary="Allocate a share to a channel.",
                    reason="The move has no declared numeric boundary.",
                    parameters={"budget_share": 0.5},
                ),
            )
        )

        result = OutputContractGuard().check_decision_proposal(
            make_proposal(candidates=(strategy,)),
            make_action_space(allowed_categories=frozenset({"channel"}), parameter_limits={}),
        )

        self.assertTrue(result.rewrite_required)
        self.assertIn("action_space_violation", {issue.code for issue in result.issues})
        self.assertIn("ActionSpace", result.rewrite_instruction)

    def test_counterexample_decision_candidate_missing_category_is_blocked(self):
        strategy = make_strategy(
            actions=(
                StrategyAction(
                    category="price",
                    summary="Set one bounded launch offer.",
                    reason="Make trial cost legible.",
                    parameters={"list_price": 49, "discount_rate": 0.1},
                ),
            )
        )

        result = OutputContractGuard().check_decision_proposal(
            make_proposal(candidates=(strategy,)), make_action_space()
        )

        self.assertTrue(result.rewrite_required)
        self.assertIn("missing: product", result.issues[0].message)

    def test_counterexample_role_mismatch_does_not_enter_round_history(self):
        result = OutputContractGuard().check_consumer_feedback(make_summary())

        with self.assertRaisesRegex(
            OutputContractViolation, "ConsumerAgent output contract rejected"
        ):
            result.require_acceptance()

    def test_limit_dense_decision_output_stays_checkable_when_actions_are_legal(self):
        actions = tuple(
            StrategyAction(
                category="price",
                summary=f"Test bounded price action {index}.",
                reason="Keep numeric actions traceable to the action space.",
                parameters={"list_price": index % 101, "discount_rate": 0.1},
            )
            for index in range(80)
        )
        proposal = make_proposal(candidates=(make_strategy(actions=actions),))

        result = OutputContractGuard().check_decision_proposal(
            proposal, make_action_space(allowed_categories=frozenset({"price"}))
        )

        self.assertTrue(result.accepted)

    def test_ucb_summary_categorical_search_signals_stay_qualitative(self):
        summary = make_summary(
            search_signals=FeedbackSearchSignals(
                core_target_response="mixed",
                trial_momentum="conditional",
                strategy_clarity="partial",
                repeat_logic="weak",
                competitor_resilience="fragile",
                evidence_consistency="mixed",
                signal_note="The cautious target is not fully convinced yet.",
            )
        )

        result = OutputContractGuard().check_feedback_summary(summary)

        self.assertTrue(result.accepted)

    def test_ucb_critic_categorical_risk_signals_stay_qualitative(self):
        critique = make_critique(
            search_risk_signals=CriticSearchSignals(
                product_boundary_risk="watch",
                brand_risk="contained",
                execution_risk="watch",
                self_deception_risk="watch",
                risk_note="Risk is about evidence gaps, not an outcome forecast.",
            )
        )

        result = OutputContractGuard().check_critique_report(critique)

        self.assertTrue(result.accepted)


if __name__ == "__main__":
    unittest.main()
