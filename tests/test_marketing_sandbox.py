import unittest

from marketing_sandbox import (
    ActionSpace,
    AdvocacyReaction,
    BehaviorDiagnosis,
    CompetitorReaction,
    ConsumerFeedback,
    CriticSearchSignals,
    CritiqueReport,
    FeedbackSearchSignals,
    FeedbackSummary,
    MarketingSandbox,
    OutputContractViolation,
    Persona,
    RepeatPurchaseReaction,
    SandboxContext,
    SandboxInputError,
    Scenario,
    Strategy,
    StrategyAction,
    StrategyFamily,
    StrategyProposal,
    RewardMapper,
    UCBSearchConfig,
    UCBSearchController,
)


def make_persona(name="Trust-sensitive commuter"):
    return Persona(
        name=name,
        core_need="A daily drink that feels dependable.",
        purchase_motivation="Reliable convenience.",
        current_alternative="A familiar bottled tea.",
        price_sensitivity="Not bargain-only, but notices trial cost.",
        trust_sensitivity="Needs believable reassurance.",
        promotion_sensitivity="Offers help when they do not cheapen trust.",
        channel_preference="A checkout path already used during commute.",
        social_influence="Reads reviews for unfamiliar brands.",
        main_barrier="Unknown routine fit.",
        repeat_trigger="A smooth first use and easy reorder path.",
        switching_threshold="A familiar competitor can pull attention away.",
    )


def make_strategy(name="Trust-first trial", **changes):
    base = {
        "name": name,
        "hypothesis": "Lower trial hesitation without inventing market demand.",
        "actions": (
            StrategyAction(
                category="product",
                summary="Use a confirmed trial pack.",
                reason="Reduce first-use regret.",
                product_claims=("trial_pack",),
            ),
            StrategyAction(
                category="price",
                summary="Keep the first offer concrete.",
                reason="The decision action should stay bounded.",
                parameters={"list_price": 49, "discount_rate": 0.1},
            ),
        ),
        "target_consumers": ("Trust-sensitive commuters",),
        "expected_tradeoffs": ("Repeat reasons may remain thin.",),
    }
    base.update(changes)
    return Strategy(**base)


def make_proposal(strategy=None, **changes):
    chosen_strategy = strategy or make_strategy()
    base = {
        "decision_note": "Start with a trust-aware trial direction.",
        "candidates": (chosen_strategy,),
        "next_validation_question": "Does the first offer stay credible?",
    }
    base.update(changes)
    return StrategyProposal(**base)


def make_feedback(persona_name, scenario_name, **changes):
    base = {
        "persona_name": persona_name,
        "scenario_name": scenario_name,
        "first_impression": "It feels cautious and practical.",
        "understood_offer": "A drink trial with reassurance.",
        "perceived_positioning": "Convenient and trying to earn trust.",
        "strongest_pull": "The first try feels less wasteful.",
        "strongest_rejection": "Repeat routine fit is still unclear.",
        "current_attitude": "Interested but careful.",
        "behavior_diagnosis": BehaviorDiagnosis(
            first_signal="Trial support.",
            reference_point="A familiar drink alternative.",
            perceived_risk="Unknown routine fit.",
            action_friction="Changing my usual store path.",
            dominant_driver="Risk reduction.",
        ),
        "repeat_purchase": RepeatPurchaseReaction(
            feeling="Repeat does not feel automatic yet.",
            condition="First use and reorder need to be smooth.",
            habit_or_inertia="Old habits still matter.",
        ),
        "competitor_reaction": CompetitorReaction(
            likely_shift="A familiar competitor still tempts me.",
            reason="Convenience already feels proven there.",
            retention_condition="A dependable first experience.",
        ),
        "advocacy": AdvocacyReaction(
            recommendation_feeling="Experience needs to come first.",
            sharing_feeling="The launch offer alone is not enough.",
            friend_description="A careful new drink trial.",
        ),
        "behavior_notes": ("Reference points matter here.",),
    }
    base.update(changes)
    return ConsumerFeedback(**base)


def make_summary(strategy_name, feedbacks, **changes):
    scenarios = tuple(dict.fromkeys(item.scenario_name for item in feedbacks))
    base = {
        "strategy_name": strategy_name,
        "scenario_names": scenarios,
        "overall_feel": f"{strategy_name} feels like a careful trial strategy.",
        "who_was_moved": ("Cautious triers moved closer.",),
        "who_was_not_moved": ("Habit-bound buyers stayed unconvinced.",),
        "strongest_evidence": ("Trial reassurance lowers hesitation.",),
        "weakest_points": ("Repeat fit is still unclear.",),
        "repeat_purchase_feel": "Repeat depends on experience and convenience.",
        "competitor_pressure_feel": "Familiar competitors expose a weak point.",
        "next_round_focus": ("Test the repeat trigger.",),
        "missing_evidence": ("Synthetic reactions do not prove demand.",),
        "qualitative_tags": ("trust-aware trial",),
    }
    base.update(changes)
    return FeedbackSummary(**base)


def make_critique(strategy_name, **changes):
    base = {
        "strategy_name": strategy_name,
        "main_loopholes": ("First trial is clearer than repeat choice.",),
        "unrealistic_assumptions": ("Reassurance may not replace routine fit.",),
        "product_boundary_risks": ("Do not stretch confirmed product claims.",),
        "brand_risks": ("A discount-heavy voice could flatten trust.",),
        "execution_risks": ("Too many touchpoints could scatter launch support.",),
        "self_deception_checks": ("Synthetic curiosity can flatter the offer.",),
        "must_validate_next": ("Verify whether repeat triggers stand up.",),
        "unresolved_questions": ("The round cannot prove habit formation.",),
        "evidence_used": ("Feedback says routine fit remains uncertain.",),
    }
    base.update(changes)
    return CritiqueReport(**base)


def make_feedback_search_signals(**changes):
    base = {
        "core_target_response": "mixed",
        "trial_momentum": "conditional",
        "strategy_clarity": "clear",
        "repeat_logic": "conditional",
        "competitor_resilience": "fragile",
        "evidence_consistency": "mixed",
        "signal_note": "First-trial reassurance is clearer than repeat proof.",
    }
    base.update(changes)
    return FeedbackSearchSignals(**base)


def make_critic_search_signals(**changes):
    base = {
        "product_boundary_risk": "contained",
        "brand_risk": "watch",
        "execution_risk": "contained",
        "self_deception_risk": "watch",
        "risk_note": "The round still leans on synthetic first-trial interest.",
    }
    base.update(changes)
    return CriticSearchSignals(**base)


def make_family(family_id="trust_risk_reduction"):
    return StrategyFamily(
        family_id=family_id,
        name="Trust risk reduction",
        core_barrier="Cautious buyers fear a bad first try.",
        win_mechanism="Reduce perceived risk before broadening reach.",
        generation_guidance="Use bounded reassurance and trial actions.",
        expected_action_patterns=("product reassurance",),
        failure_signals=("trust collapses into discount-only voice",),
    )


def make_context(**changes):
    base = {
        "product_facts": (
            "Cold-brew tea exists as a ready-to-drink bottle.",
            "A trial pack exists.",
        ),
        "marketing_objectives": ("Find a defendable first strategy direction.",),
        "core_target": "Trust-sensitive commuters",
        "product_boundaries": ("Do not promise medical outcomes.",),
        "brand_boundaries": ("Do not become bargain-only.",),
        "brand_facts": ("Ingredient information is available.",),
        "market_facts": ("Convenience and trust are visible comparison points.",),
        "competitor_facts": ("A familiar competitor is easier to recall.",),
        "execution_boundaries": ("Launch support starts with one staffed channel.",),
        "known_facts": ("Consumer feedback in the sandbox is synthetic.",),
    }
    base.update(changes)
    return SandboxContext(**base)


def make_action_space():
    return ActionSpace(
        allowed_categories=frozenset({"product", "price"}),
        allowed_product_claims=frozenset({"trial_pack"}),
        parameter_limits={"price": {"list_price": (0, 100), "discount_rate": (0, 0.3)}},
    )


class StubDecisionAgent:
    def __init__(self, *proposals):
        self.proposals = proposals
        self.initial_contexts = []
        self.revisions = []

    def propose_initial_strategies(self, context):
        self.initial_contexts.append(context)
        return self.proposals[0]

    def revise_strategies(self, context, evidence):
        self.revisions.append((context, evidence))
        return self.proposals[len(self.revisions)]


class FamilyStubDecisionAgent(StubDecisionAgent):
    def __init__(self, *proposals):
        super().__init__(*proposals)
        self.search_briefs = []

    def propose_initial_strategies(self, context, *, search_brief=None):
        self.search_briefs.append(search_brief)
        return super().propose_initial_strategies(context)

    def revise_strategies(self, context, evidence, *, search_brief=None):
        self.search_briefs.append(search_brief)
        return super().revise_strategies(context, evidence)


class StubConsumerAgent:
    def __init__(self, persona, feedback_factory=make_feedback):
        self.persona = persona
        self.feedback_factory = feedback_factory
        self.calls = []

    def react_to_strategy(self, strategy, scenario, product_context):
        self.calls.append((strategy, scenario, product_context))
        return self.feedback_factory(self.persona.name, scenario.name)


class StubFeedbackSynthesizer:
    def __init__(self, *, with_search_signals=False):
        self.calls = []
        self.with_search_signals = with_search_signals

    def synthesize(self, strategy, feedbacks, *, core_target, prior_summary=""):
        self.calls.append((strategy, feedbacks, core_target, prior_summary))
        changes = {}
        if self.with_search_signals:
            changes["search_signals"] = make_feedback_search_signals()
        return make_summary(strategy.name, feedbacks, **changes)


class StubCriticAgent:
    def __init__(self, *, with_search_signals=False):
        self.calls = []
        self.with_search_signals = with_search_signals

    def critique(self, strategy, feedbacks, feedback_summary, context):
        self.calls.append((strategy, feedbacks, feedback_summary, context))
        changes = {}
        if self.with_search_signals:
            changes["search_risk_signals"] = make_critic_search_signals()
        return make_critique(strategy.name, **changes)


def make_sandbox(
    *,
    proposals=None,
    consumers=None,
    scenarios=None,
    context=None,
    critic=None,
    decision_agent=None,
    search_controller=None,
    reward_mapper=None,
    with_search_signals=False,
):
    decision_agent = decision_agent or StubDecisionAgent(
        *(proposals or (make_proposal(),))
    )
    feedback_synthesizer = StubFeedbackSynthesizer(
        with_search_signals=with_search_signals
    )
    critic_agent = (
        critic
        if critic is not None
        else StubCriticAgent(with_search_signals=with_search_signals)
    )
    sandbox = MarketingSandbox(
        context=context or make_context(),
        action_space=make_action_space(),
        decision_agent=decision_agent,
        consumer_agents=consumers
        if consumers is not None
        else (
            StubConsumerAgent(make_persona()),
            StubConsumerAgent(make_persona("Price-aware explorer")),
        ),
        feedback_synthesizer=feedback_synthesizer,
        critic_agent=critic_agent,
        scenarios=scenarios
        if scenarios is not None
        else (
            Scenario("Normal launch", "The product is shown in a normal shelf moment."),
            Scenario(
                "Competitor trust pressure",
                "The product sits beside a familiar competitor.",
                competitor_pressure="The competitor has deeper familiarity.",
            ),
        ),
        search_controller=search_controller,
        reward_mapper=reward_mapper,
    )
    return sandbox, decision_agent, feedback_synthesizer, critic_agent


class MarketingSandboxTests(unittest.TestCase):
    def test_normal_one_round_routes_proposal_feedback_summary_and_critique(self):
        sandbox, decision_agent, synthesizer, critic = make_sandbox()

        result = sandbox.run()

        round_result = result.rounds[0]
        self.assertEqual(round_result.round_index, 1)
        self.assertEqual(len(round_result.strategy_tests[0].consumer_feedbacks), 4)
        self.assertEqual(result.recommended_strategy_directions, ("Trust-first trial",))
        self.assertIn("Trust-sensitive commuter", decision_agent.initial_contexts[0].target_personas)
        self.assertEqual(synthesizer.calls[0][2], "Trust-sensitive commuters")
        self.assertIn("one staffed channel", critic.calls[0][3].execution_boundaries[0])

    def test_boundary_single_consumer_single_scenario_single_strategy_runs(self):
        sandbox, _, _, _ = make_sandbox(
            consumers=(StubConsumerAgent(make_persona()),),
            scenarios=(Scenario("Normal launch", "The offer appears once."),),
        )

        round_result = sandbox.run_round()

        self.assertEqual(len(round_result.strategy_tests), 1)
        self.assertEqual(len(round_result.consumer_feedbacks), 1)
        self.assertIn("attitude Interested but careful", round_result.next_round_evidence.consumer_feedback_summary)

    def test_boundary_minimum_optional_context_still_builds_role_contexts(self):
        context = SandboxContext(
            product_facts=("A trial pack exists.",),
            marketing_objectives=("Learn where hesitation lands.",),
            core_target="Cautious triers",
            product_boundaries=("Stay inside product facts.",),
            brand_boundaries=("Do not damage trust.",),
        )
        sandbox, _, _, critic = make_sandbox(
            context=context,
            consumers=(StubConsumerAgent(make_persona()),),
            scenarios=(Scenario("Normal launch", "The offer appears once."),),
        )

        sandbox.run()

        critic_context = critic.calls[0][3]
        self.assertEqual(critic_context.execution_boundaries, ())
        self.assertEqual(critic_context.known_facts, ())

    def test_boundary_build_result_before_rounds_is_empty(self):
        sandbox, _, _, _ = make_sandbox()

        result = sandbox.build_result()

        self.assertEqual(result.rounds, ())
        self.assertEqual(result.recommended_strategy_directions, ())

    def test_special_multiple_candidate_strategies_are_tested_separately(self):
        proposal = make_proposal(
            candidates=(
                make_strategy("Trust-first trial"),
                make_strategy("Convenience-led path"),
            )
        )
        sandbox, _, synthesizer, critic = make_sandbox(proposals=(proposal,))

        round_result = sandbox.run_round()

        self.assertEqual(
            [item.strategy.name for item in round_result.strategy_tests],
            ["Trust-first trial", "Convenience-led path"],
        )
        self.assertEqual(len(synthesizer.calls), 2)
        self.assertEqual(len(critic.calls), 2)

    def test_special_second_round_revises_from_saved_round_evidence(self):
        first = make_proposal(strategy=make_strategy("Trust-first trial"))
        second = make_proposal(strategy=make_strategy("Repeat-ready path"))
        sandbox, decision_agent, synthesizer, _ = make_sandbox(
            proposals=(first, second)
        )

        result = sandbox.run(round_count=2)

        revision_context, evidence = decision_agent.revisions[0]
        self.assertIn("Trust-first trial", revision_context.tested_strategies)
        self.assertIn("Trust-first trial", evidence.feedback_synthesis)
        self.assertIn("Trust-first trial", synthesizer.calls[-1][3])
        self.assertEqual(result.paused_strategy_directions, ("Trust-first trial",))

    def test_special_strategy_test_preserves_all_scenario_feedback_for_summary(self):
        scenarios = (
            Scenario("Channel friction", "Checkout takes longer than expected."),
            Scenario("Trust pressure", "The competitor has deeper review history."),
            Scenario("Budget caution", "The buyer is watching spend."),
        )
        sandbox, _, synthesizer, _ = make_sandbox(scenarios=scenarios)

        sandbox.run_round()

        feedbacks = synthesizer.calls[0][1]
        self.assertEqual({item.scenario_name for item in feedbacks}, {item.name for item in scenarios})
        self.assertEqual(len(feedbacks), 6)

    def test_counterexample_missing_consumer_agents_is_rejected(self):
        with self.assertRaisesRegex(SandboxInputError, "ConsumerAgent"):
            MarketingSandbox(
                context=make_context(),
                action_space=make_action_space(),
                decision_agent=StubDecisionAgent(make_proposal()),
                consumer_agents=None,
                feedback_synthesizer=StubFeedbackSynthesizer(),
                critic_agent=StubCriticAgent(),
                scenarios=(Scenario("Normal launch", "The offer appears once."),),
            )

    def test_counterexample_missing_critic_agent_is_rejected(self):
        with self.assertRaisesRegex(SandboxInputError, "CriticAgent"):
            MarketingSandbox(
                context=make_context(),
                action_space=make_action_space(),
                decision_agent=StubDecisionAgent(make_proposal()),
                consumer_agents=(StubConsumerAgent(make_persona()),),
                feedback_synthesizer=StubFeedbackSynthesizer(),
                critic_agent=None,
                scenarios=(Scenario("Normal launch", "The offer appears once."),),
            )

    def test_counterexample_outside_action_space_does_not_pollute_history(self):
        unsafe_strategy = make_strategy(
            actions=(
                StrategyAction(
                    category="channel",
                    summary="Allocate undeclared channel share.",
                    reason="This numeric move has no sandbox boundary.",
                    parameters={"budget_share": 0.5},
                ),
            )
        )
        sandbox, _, _, _ = make_sandbox(
            proposals=(make_proposal(strategy=unsafe_strategy),)
        )

        with self.assertRaises(OutputContractViolation):
            sandbox.run_round()

        self.assertEqual(sandbox.history, ())

    def test_limit_many_consumers_scenarios_and_candidates_still_save_one_round(self):
        consumers = tuple(
            StubConsumerAgent(make_persona(f"Persona {index}")) for index in range(10)
        )
        scenarios = tuple(
            Scenario(f"Scenario {index}", f"Pressure case {index}.")
            for index in range(5)
        )
        proposal = make_proposal(
            candidates=tuple(make_strategy(f"Strategy {index}") for index in range(4))
        )
        sandbox, _, _, _ = make_sandbox(
            proposals=(proposal,), consumers=consumers, scenarios=scenarios
        )

        round_result = sandbox.run_round()

        self.assertEqual(len(round_result.strategy_tests), 4)
        self.assertEqual(len(round_result.consumer_feedbacks), 200)
        self.assertEqual(len(sandbox.history), 1)

    def test_ucb_round_saves_family_selection_observation_and_update(self):
        strategy = make_strategy(family_id="trust_risk_reduction")
        proposal = make_proposal(strategy=strategy)
        decision_agent = FamilyStubDecisionAgent(proposal)
        controller = UCBSearchController((make_family(),))
        sandbox, _, _, _ = make_sandbox(
            proposals=(proposal,),
            decision_agent=decision_agent,
            search_controller=controller,
            reward_mapper=RewardMapper(),
            with_search_signals=True,
        )

        result = sandbox.run()

        round_result = result.rounds[0]
        self.assertEqual(
            round_result.search_selection.selected_family_ids,
            ("trust_risk_reduction",),
        )
        self.assertIsNotNone(round_result.strategy_tests[0].search_observation)
        self.assertEqual(round_result.search_updates[0].state_after.pull_count, 1)
        self.assertIn("searched families", result.search_notes[0])
        self.assertIsNotNone(decision_agent.search_briefs[0])

    def test_ucb_missing_summary_signals_does_not_update_family_state(self):
        strategy = make_strategy(family_id="trust_risk_reduction")
        proposal = make_proposal(strategy=strategy)
        controller = UCBSearchController((make_family(),))
        sandbox, _, _, _ = make_sandbox(
            proposals=(proposal,),
            decision_agent=FamilyStubDecisionAgent(proposal),
            search_controller=controller,
            reward_mapper=RewardMapper(),
        )

        with self.assertRaisesRegex(SandboxInputError, "search signals"):
            sandbox.run_round()

        self.assertEqual(sandbox.history, ())
        self.assertEqual(controller.total_pulls, 0)

    def test_ucb_candidate_family_mismatch_fails_before_feedback_calls(self):
        proposal = make_proposal(
            strategy=make_strategy(family_id="trial_value_entry")
        )
        controller = UCBSearchController((make_family(),))
        sandbox, _, synthesizer, _ = make_sandbox(
            proposals=(proposal,),
            decision_agent=FamilyStubDecisionAgent(proposal),
            search_controller=controller,
            reward_mapper=RewardMapper(),
            with_search_signals=True,
        )

        with self.assertRaisesRegex(SandboxInputError, "cover selected"):
            sandbox.run_round()

        self.assertEqual(synthesizer.calls, [])
        self.assertEqual(controller.total_pulls, 0)

    def test_ucb_two_cold_families_can_be_tested_in_one_round(self):
        trust = make_strategy("Trust", family_id="trust_risk_reduction")
        trial = make_strategy("Trial", family_id="trial_value_entry")
        proposal = make_proposal(candidates=(trust, trial))
        controller = UCBSearchController(
            (make_family(), make_family("trial_value_entry")),
            UCBSearchConfig(candidate_slots_per_round=2),
        )
        sandbox, _, _, _ = make_sandbox(
            proposals=(proposal,),
            decision_agent=FamilyStubDecisionAgent(proposal),
            search_controller=controller,
            reward_mapper=RewardMapper(),
            with_search_signals=True,
        )

        round_result = sandbox.run_round()

        self.assertEqual(len(round_result.search_updates), 2)
        self.assertEqual(controller.total_pulls, 2)


if __name__ == "__main__":
    unittest.main()
