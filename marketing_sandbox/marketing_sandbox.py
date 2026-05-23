"""Orchestration entry point for the AI marketing sandbox."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .action_space import ActionSpace
from .consumer_agent import ConsumerFeedback, ProductContext, Scenario
from .critic_agent import CriticContext, CritiqueReport
from .decision_agent import DecisionContext, RoundEvidence, Strategy, StrategyProposal
from .feedback_synthesizer import FeedbackSummary
from .output_contract_guard import OutputContractGuard
from .reward_mapper import RewardMapper
from .search_models import (
    SearchObservation,
    SearchSelection,
    SearchUpdate,
)
from .ucb_search_controller import UCBSearchController


class MarketingSandboxError(Exception):
    """Base error for MarketingSandbox failures."""


class SandboxInputError(MarketingSandboxError):
    """Raised when the sandbox cannot run from its configured collaborators."""


@dataclass(frozen=True)
class SandboxContext:
    """Facts and boundaries shared by one marketing sandbox run."""

    product_facts: tuple[str, ...]
    marketing_objectives: tuple[str, ...]
    core_target: str
    product_boundaries: tuple[str, ...]
    brand_boundaries: tuple[str, ...]
    brand_facts: tuple[str, ...] = ()
    market_facts: tuple[str, ...] = ()
    competitor_facts: tuple[str, ...] = ()
    execution_boundaries: tuple[str, ...] = ()
    known_facts: tuple[str, ...] = ()


@dataclass(frozen=True)
class StrategyTestResult:
    """Feedback, synthesis, and critique for one strategy in one round."""

    strategy: Strategy
    consumer_feedbacks: tuple[ConsumerFeedback, ...]
    feedback_summary: FeedbackSummary
    critique_report: CritiqueReport
    search_observation: SearchObservation | None = None


@dataclass(frozen=True)
class RoundResult:
    """One saved sandbox round across all candidate strategy tests."""

    round_index: int
    proposal: StrategyProposal
    strategy_tests: tuple[StrategyTestResult, ...]
    next_round_evidence: RoundEvidence
    search_selection: SearchSelection | None = None
    search_updates: tuple[SearchUpdate, ...] = ()

    @property
    def consumer_feedbacks(self) -> tuple[ConsumerFeedback, ...]:
        """Flatten consumer feedback from every strategy tested this round."""

        return tuple(
            feedback
            for strategy_test in self.strategy_tests
            for feedback in strategy_test.consumer_feedbacks
        )

    @property
    def feedback_summaries(self) -> tuple[FeedbackSummary, ...]:
        """Return feedback summaries in candidate strategy order."""

        return tuple(item.feedback_summary for item in self.strategy_tests)

    @property
    def critique_reports(self) -> tuple[CritiqueReport, ...]:
        """Return critique reports in candidate strategy order."""

        return tuple(item.critique_report for item in self.strategy_tests)


@dataclass(frozen=True)
class SandboxResult:
    """Qualitative sandbox output after one or more saved rounds."""

    rounds: tuple[RoundResult, ...]
    recommended_strategy_directions: tuple[str, ...]
    paused_strategy_directions: tuple[str, ...]
    audience_insights: tuple[str, ...]
    strategy_risks: tuple[str, ...]
    real_market_validation_questions: tuple[str, ...]
    decision_logic: tuple[str, ...]
    family_search_trace: tuple[SearchUpdate, ...] = ()
    search_notes: tuple[str, ...] = ()


class MarketingSandbox:
    """Host the decision, consumer, synthesis, and critique sandbox loop."""

    def __init__(
        self,
        *,
        context: SandboxContext,
        action_space: ActionSpace,
        decision_agent: Any,
        consumer_agents: Sequence[Any] | None,
        feedback_synthesizer: Any,
        critic_agent: Any,
        scenarios: Sequence[Scenario] | None,
        output_guard: OutputContractGuard | None = None,
        search_controller: UCBSearchController | None = None,
        reward_mapper: RewardMapper | None = None,
    ) -> None:
        self.context = context
        self.action_space = action_space
        self.decision_agent = decision_agent
        self.consumer_agents = (
            tuple(consumer_agents) if consumer_agents is not None else ()
        )
        self.feedback_synthesizer = feedback_synthesizer
        self.critic_agent = critic_agent
        self.scenarios = tuple(scenarios) if scenarios is not None else ()
        self.output_guard = output_guard or OutputContractGuard()
        self.search_controller = search_controller
        self.reward_mapper = reward_mapper
        self._history: list[RoundResult] = []
        self._validate_configuration()

    @property
    def history(self) -> tuple[RoundResult, ...]:
        """Return saved rounds without exposing the mutable history list."""

        return tuple(self._history)

    def run(self, *, round_count: int = 1) -> SandboxResult:
        """Run one or more rounds and return the current sandbox result."""

        if isinstance(round_count, bool) or not isinstance(round_count, int):
            raise SandboxInputError("Sandbox round_count must be an integer.")
        if round_count < 1:
            raise SandboxInputError("Sandbox needs at least one round to run.")
        for _ in range(round_count):
            self.run_round()
        return self.build_result()

    def run_round(self, *, evidence: RoundEvidence | None = None) -> RoundResult:
        """Run and save one round, revising from prior evidence when available."""

        round_evidence = evidence
        if round_evidence is None and self._history:
            round_evidence = self._history[-1].next_round_evidence
        decision_context = self._build_decision_context()
        round_index = len(self._history) + 1
        search_selection = self._select_search_families(round_index)
        proposal = self._propose_strategies(
            decision_context,
            round_evidence,
            search_selection,
        )
        self.output_guard.check_decision_proposal(
            proposal, self.action_space
        ).require_acceptance()
        if search_selection is not None:
            self._validate_search_proposal(proposal, search_selection)

        prior_summary = round_evidence.feedback_synthesis if round_evidence else ""
        strategy_tests: list[StrategyTestResult] = []
        observations: list[SearchObservation] = []
        for strategy in proposal.candidates:
            strategy_test = self.test_strategy(strategy, prior_summary=prior_summary)
            if search_selection is not None:
                observation = self._build_search_observation(
                    round_index, strategy_test
                )
                strategy_test = StrategyTestResult(
                    strategy=strategy_test.strategy,
                    consumer_feedbacks=strategy_test.consumer_feedbacks,
                    feedback_summary=strategy_test.feedback_summary,
                    critique_report=strategy_test.critique_report,
                    search_observation=observation,
                )
                observations.append(observation)
            strategy_tests.append(strategy_test)
        search_updates = self._update_search(
            tuple(observations),
            search_selection,
        )
        tests_tuple = tuple(strategy_tests)
        round_result = RoundResult(
            round_index=round_index,
            proposal=proposal,
            strategy_tests=tests_tuple,
            next_round_evidence=self._build_round_evidence(tests_tuple),
            search_selection=search_selection,
            search_updates=search_updates,
        )
        self._history.append(round_result)
        return round_result

    def test_strategy(
        self, strategy: Strategy, *, prior_summary: str = ""
    ) -> StrategyTestResult:
        """Test one strategy across configured consumers and scenarios."""

        product_context = self._build_product_context()
        feedbacks: list[ConsumerFeedback] = []
        for scenario in self.scenarios:
            for consumer_agent in self.consumer_agents:
                feedback = consumer_agent.react_to_strategy(
                    strategy, scenario, product_context
                )
                self.output_guard.check_consumer_feedback(
                    feedback
                ).require_acceptance()
                feedbacks.append(feedback)

        feedback_batch = tuple(feedbacks)
        summary = self.feedback_synthesizer.synthesize(
            strategy,
            feedback_batch,
            core_target=self.context.core_target,
            prior_summary=prior_summary,
        )
        self.output_guard.check_feedback_summary(summary).require_acceptance()

        critique = self.critic_agent.critique(
            strategy,
            feedback_batch,
            summary,
            self._build_critic_context(),
        )
        self.output_guard.check_critique_report(critique).require_acceptance()
        return StrategyTestResult(
            strategy=strategy,
            consumer_feedbacks=feedback_batch,
            feedback_summary=summary,
            critique_report=critique,
        )

    def build_result(self) -> SandboxResult:
        """Summarize saved sandbox history without inventing market scores."""

        if not self._history:
            return SandboxResult(
                rounds=(),
                recommended_strategy_directions=(),
                paused_strategy_directions=(),
                audience_insights=(),
                strategy_risks=(),
                real_market_validation_questions=(),
                decision_logic=(),
                family_search_trace=(),
                search_notes=(),
            )

        latest_round = self._history[-1]
        latest_names = tuple(
            strategy.name for strategy in latest_round.proposal.candidates
        )
        prior_names = tuple(
            strategy.name
            for round_result in self._history[:-1]
            for strategy in round_result.proposal.candidates
        )
        paused_names = tuple(name for name in prior_names if name not in latest_names)

        audience_insights: list[str] = []
        strategy_risks: list[str] = []
        validation_questions: list[str] = [
            latest_round.proposal.next_validation_question
        ]
        decision_logic: list[str] = []
        for strategy_test in latest_round.strategy_tests:
            summary = strategy_test.feedback_summary
            critique = strategy_test.critique_report
            audience_insights.extend(summary.who_was_moved)
            audience_insights.extend(summary.who_was_not_moved)
            strategy_risks.extend(critique.main_loopholes)
            strategy_risks.extend(critique.product_boundary_risks)
            strategy_risks.extend(critique.brand_risks)
            strategy_risks.extend(critique.execution_risks)
            validation_questions.extend(summary.missing_evidence)
            validation_questions.extend(critique.must_validate_next)
            validation_questions.extend(critique.unresolved_questions)
            decision_logic.append(
                f"{strategy_test.strategy.name}: {summary.overall_feel}"
            )
            decision_logic.extend(summary.next_round_focus)
        family_search_trace = tuple(
            update
            for round_result in self._history
            for update in round_result.search_updates
        )
        search_notes = tuple(
            f"Round {round_result.round_index} searched families: "
            + ", ".join(round_result.search_selection.selected_family_ids)
            for round_result in self._history
            if round_result.search_selection is not None
        )

        return SandboxResult(
            rounds=self.history,
            recommended_strategy_directions=self._dedupe(latest_names),
            paused_strategy_directions=self._dedupe(paused_names),
            audience_insights=self._dedupe(audience_insights),
            strategy_risks=self._dedupe(strategy_risks),
            real_market_validation_questions=self._dedupe(validation_questions),
            decision_logic=self._dedupe(decision_logic),
            family_search_trace=family_search_trace,
            search_notes=self._dedupe(search_notes),
        )

    def _build_decision_context(self) -> DecisionContext:
        return DecisionContext(
            product_facts=self.context.product_facts,
            marketing_objectives=self.context.marketing_objectives,
            brand_boundaries=self.context.brand_boundaries,
            market_facts=self.context.market_facts,
            competitor_facts=self.context.competitor_facts,
            target_personas=self._consumer_persona_names(),
            scenarios=tuple(scenario.name for scenario in self.scenarios),
            tested_strategies=tuple(
                strategy.name
                for round_result in self._history
                for strategy in round_result.proposal.candidates
            ),
        )

    def _build_product_context(self) -> ProductContext:
        return ProductContext(
            facts=self.context.product_facts,
            brand_facts=self.context.brand_facts,
            competitor_facts=self.context.competitor_facts,
        )

    def _build_critic_context(self) -> CriticContext:
        return CriticContext(
            product_boundaries=self.context.product_boundaries,
            brand_boundaries=self.context.brand_boundaries,
            execution_boundaries=self.context.execution_boundaries,
            known_facts=self.context.known_facts,
        )

    @staticmethod
    def _build_round_evidence(
        strategy_tests: Sequence[StrategyTestResult],
    ) -> RoundEvidence:
        feedback_lines: list[str] = []
        synthesis_lines: list[str] = []
        critique_lines: list[str] = []
        for strategy_test in strategy_tests:
            strategy_name = strategy_test.strategy.name
            for feedback in strategy_test.consumer_feedbacks:
                feedback_lines.append(
                    f"{strategy_name} / {feedback.persona_name} / "
                    f"{feedback.scenario_name}: attitude {feedback.current_attitude}; "
                    f"pull {feedback.strongest_pull}; "
                    f"rejection {feedback.strongest_rejection}; "
                    f"repeat {feedback.repeat_purchase.feeling}; "
                    f"competitor {feedback.competitor_reaction.likely_shift}."
                )
            summary = strategy_test.feedback_summary
            synthesis_lines.append(
                f"{strategy_name}: {summary.overall_feel} "
                f"Next focus: {'; '.join(summary.next_round_focus)}"
            )
            critique = strategy_test.critique_report
            critique_lines.append(
                f"{strategy_name}: loopholes {'; '.join(critique.main_loopholes)} "
                f"Must validate: {'; '.join(critique.must_validate_next)}"
            )
        return RoundEvidence(
            consumer_feedback_summary="\n".join(feedback_lines),
            feedback_synthesis="\n".join(synthesis_lines),
            critique="\n".join(critique_lines),
        )

    def _validate_configuration(self) -> None:
        if not isinstance(self.action_space, ActionSpace):
            raise SandboxInputError("MarketingSandbox needs an ActionSpace.")
        self._require_method(
            self.decision_agent,
            "propose_initial_strategies",
            "DecisionAgent",
        )
        self._require_method(self.decision_agent, "revise_strategies", "DecisionAgent")
        self._require_method(
            self.feedback_synthesizer, "synthesize", "FeedbackSynthesizer"
        )
        self._require_method(self.critic_agent, "critique", "CriticAgent")
        if self.search_controller is not None:
            if not isinstance(self.search_controller, UCBSearchController):
                raise SandboxInputError(
                    "MarketingSandbox search_controller must be UCBSearchController."
                )
            if not isinstance(self.reward_mapper, RewardMapper):
                raise SandboxInputError(
                    "MarketingSandbox UCB search needs a RewardMapper."
                )
        elif self.reward_mapper is not None:
            raise SandboxInputError(
                "MarketingSandbox RewardMapper needs a UCB search controller."
            )
        if not self.consumer_agents:
            raise SandboxInputError("MarketingSandbox needs ConsumerAgent instances.")
        for consumer_agent in self.consumer_agents:
            self._require_method(consumer_agent, "react_to_strategy", "ConsumerAgent")
        if not self.scenarios:
            raise SandboxInputError("MarketingSandbox needs Scenario instances.")
        for scenario in self.scenarios:
            if not isinstance(scenario, Scenario):
                raise SandboxInputError("MarketingSandbox scenarios must be Scenario objects.")
            if not scenario.name.strip() or not scenario.situation.strip():
                raise SandboxInputError("Sandbox Scenario needs a name and situation.")
        self._validate_context(self.context)

    @classmethod
    def _validate_context(cls, context: SandboxContext) -> None:
        if not isinstance(context, SandboxContext):
            raise SandboxInputError("MarketingSandbox needs a SandboxContext.")
        cls._require_text_items(context.product_facts, "product facts")
        cls._require_text_items(context.marketing_objectives, "marketing objectives")
        cls._require_text_items(context.product_boundaries, "product boundaries")
        cls._require_text_items(context.brand_boundaries, "brand boundaries")
        if not isinstance(context.core_target, str) or not context.core_target.strip():
            raise SandboxInputError("SandboxContext needs a core target.")

    @staticmethod
    def _require_method(item: Any, method_name: str, label: str) -> None:
        if not callable(getattr(item, method_name, None)):
            raise SandboxInputError(f"MarketingSandbox needs a {label}.")

    @staticmethod
    def _require_text_items(items: Sequence[str], label: str) -> None:
        if not items or not any(
            isinstance(item, str) and item.strip() for item in items
        ):
            raise SandboxInputError(f"SandboxContext needs {label}.")

    def _consumer_persona_names(self) -> tuple[str, ...]:
        names: list[str] = []
        for index, consumer_agent in enumerate(self.consumer_agents, start=1):
            persona = getattr(consumer_agent, "persona", None)
            name = getattr(persona, "name", "")
            names.append(name.strip() or f"consumer agent {index}")
        return tuple(names)

    @staticmethod
    def _dedupe(items: Sequence[str]) -> tuple[str, ...]:
        unique: list[str] = []
        for item in items:
            if item not in unique:
                unique.append(item)
        return tuple(unique)

    def _select_search_families(
        self, round_index: int
    ) -> SearchSelection | None:
        if self.search_controller is None:
            return None
        return self.search_controller.select(round_index, self.history)

    def _propose_strategies(
        self,
        decision_context: DecisionContext,
        round_evidence: RoundEvidence | None,
        search_selection: SearchSelection | None,
    ) -> StrategyProposal:
        search_brief = search_selection.brief if search_selection is not None else None
        if round_evidence is None:
            if search_brief is None:
                return self.decision_agent.propose_initial_strategies(
                    decision_context
                )
            return self.decision_agent.propose_initial_strategies(
                decision_context,
                search_brief=search_brief,
            )
        if search_brief is None:
            return self.decision_agent.revise_strategies(
                decision_context, round_evidence
            )
        return self.decision_agent.revise_strategies(
            decision_context,
            round_evidence,
            search_brief=search_brief,
        )

    @staticmethod
    def _validate_search_proposal(
        proposal: StrategyProposal, search_selection: SearchSelection
    ) -> None:
        expected = tuple(search_selection.selected_family_ids)
        actual = [strategy.family_id for strategy in proposal.candidates]
        if any(not family_id for family_id in actual):
            raise SandboxInputError("UCB strategy candidates need family ids.")
        if len(actual) != len(set(actual)):
            raise SandboxInputError(
                "UCB strategy candidates must not repeat selected families."
            )
        if len(actual) != len(expected) or set(actual) != set(expected):
            raise SandboxInputError(
                "UCB strategy candidates must cover selected families exactly."
            )

    def _build_search_observation(
        self, round_index: int, strategy_test: StrategyTestResult
    ) -> SearchObservation:
        summary_signals = strategy_test.feedback_summary.search_signals
        critic_signals = strategy_test.critique_report.search_risk_signals
        if summary_signals is None:
            raise SandboxInputError(
                "UCB search needs FeedbackSummary search signals."
            )
        if critic_signals is None:
            raise SandboxInputError(
                "UCB search needs CritiqueReport search risk signals."
            )
        if self.reward_mapper is None:
            raise SandboxInputError("UCB search needs a RewardMapper.")
        return SearchObservation(
            round_index=round_index,
            family_id=strategy_test.strategy.family_id,
            strategy_name=strategy_test.strategy.name,
            summary_signals=summary_signals,
            critic_signals=critic_signals,
            reward_breakdown=self.reward_mapper.map(summary_signals, critic_signals),
        )

    def _update_search(
        self,
        observations: tuple[SearchObservation, ...],
        search_selection: SearchSelection | None,
    ) -> tuple[SearchUpdate, ...]:
        if search_selection is None:
            return ()
        if self.search_controller is None:
            raise SandboxInputError("UCB SearchSelection needs a search controller.")
        return self.search_controller.update(observations, selection=search_selection)
