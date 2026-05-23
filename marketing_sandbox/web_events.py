"""Map completed sandbox results into visualization-friendly web events."""

from __future__ import annotations

import math
import re
from typing import Any, Mapping, Sequence

from .consumer_agent import ConsumerFeedback
from .critic_agent import CritiqueReport
from .decision_agent import Strategy, StrategyAction, StrategyProposal
from .feedback_synthesizer import FeedbackSummary
from .marketing_sandbox import RoundResult, SandboxResult, StrategyTestResult
from .search_models import SearchSelection, SearchUpdate, StrategyFamily


WEB_EVENT_CONTRACT_VERSION = "marketing-sandbox-web-events/v1"
WEB_EVENT_TYPES = frozenset(
    {
        "run_started",
        "round_progress",
        "round_started",
        "family_selected",
        "strategy_proposed",
        "consumer_feedback_ready",
        "feedback_summary_ready",
        "critique_ready",
        "search_updated",
        "round_completed",
        "run_failed",
        "run_completed",
    }
)
WEB_EVENT_CONTRACT: Mapping[str, Mapping[str, Any]] = {
    "run_started": {
        "category": "lifecycle",
        "requiredFields": ("id", "type", "round", "actorId", "actorRole", "headline", "summary"),
        "purpose": "Marks the beginning of one live or replayed sandbox run.",
    },
    "round_progress": {
        "category": "lifecycle",
        "requiredFields": ("id", "type", "round", "progress", "headline", "summary"),
        "purpose": "Shows that a live round has entered model calls before a completed round exists.",
    },
    "round_started": {
        "category": "lifecycle",
        "requiredFields": ("id", "type", "round", "proposal", "headline", "summary"),
        "purpose": "Opens a completed round payload for playback and panels.",
    },
    "family_selected": {
        "category": "ucb",
        "requiredFields": ("id", "type", "round", "family", "internalSearch", "headline", "summary"),
        "purpose": "Shows which strategy family the search controller selected.",
    },
    "strategy_proposed": {
        "category": "strategy_proposal",
        "requiredFields": ("id", "type", "round", "strategy", "proposal", "headline", "summary"),
        "purpose": "Shows the concrete DecisionAgent strategy candidate.",
    },
    "consumer_feedback_ready": {
        "category": "role_speech",
        "requiredFields": ("id", "type", "round", "feedback", "strategyName", "headline", "summary"),
        "purpose": "Shows one persona agent's qualitative reaction.",
    },
    "feedback_summary_ready": {
        "category": "synthesis",
        "requiredFields": ("id", "type", "round", "synthesis", "strategyName", "headline", "summary"),
        "purpose": "Shows the qualitative feedback synthesis.",
    },
    "critique_ready": {
        "category": "critique",
        "requiredFields": ("id", "type", "round", "critique", "strategyName", "headline", "summary"),
        "purpose": "Shows the critic agent's risk and boundary review.",
    },
    "search_updated": {
        "category": "reward_ucb",
        "requiredFields": ("id", "type", "round", "search", "headline", "summary"),
        "purpose": "Carries internal reward and family arm update metrics.",
    },
    "round_completed": {
        "category": "safe_boundary",
        "requiredFields": ("id", "type", "round", "evidence", "headline", "summary"),
        "purpose": "Marks a safe archive boundary after one complete round.",
    },
    "run_completed": {
        "category": "lifecycle",
        "requiredFields": ("id", "type", "round", "result", "headline", "summary"),
        "purpose": "Marks normal completion of a run.",
    },
    "run_failed": {
        "category": "lifecycle",
        "requiredFields": ("id", "type", "round", "issue", "headline", "summary"),
        "purpose": "Marks a failed live run with a safe, redacted error detail.",
    },
}
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
ASCII_TOKEN_PATTERN = re.compile(r"[^a-z0-9]+")


class WebEventMappingError(Exception):
    """Raised when sandbox data cannot become a browser event sequence."""


class SandboxWebEventMapper:
    """Convert completed sandbox rounds to the current frontend event shape.

    This mapper stays outside ``MarketingSandbox`` because the core sandbox
    should keep domain results, while the website needs actor ids, UI copy, and
    event ordering. Internal numeric search utility is carried with explicit
    labels so the UI can audit the search path without presenting it as a
    market prediction.
    """

    def __init__(self, *, sensitive_values: Sequence[str] = ()) -> None:
        if isinstance(sensitive_values, (str, bytes)):
            raise WebEventMappingError("sensitive_values must be a text sequence.")
        parsed_values: list[str] = []
        for value in sensitive_values:
            if not isinstance(value, str):
                raise WebEventMappingError("sensitive_values must contain text.")
            if value:
                parsed_values.append(value)
        self._sensitive_values = tuple(parsed_values)
        self._events: list[dict[str, Any]] = []
        self._run_id = ""

    def map_result(
        self,
        result: SandboxResult,
        *,
        run_id: str = "live-run",
    ) -> tuple[dict[str, Any], ...]:
        """Return ordered frontend events for one completed sandbox result."""

        if not isinstance(result, SandboxResult):
            raise WebEventMappingError("map_result needs a SandboxResult.")
        self.start_stream(run_id=run_id)
        for round_result in result.rounds:
            self._append_round(round_result)
        self._append_run_completed(result)
        return tuple(self._sanitize_payload(event) for event in self._events)

    def start_stream(self, *, run_id: str = "live-run") -> tuple[dict[str, Any], ...]:
        """Start a streamable run and return its boundary event."""

        self._start_run(run_id)
        self._append_event(
            "run_started",
            0,
            actor_id="decision",
            actor_role="decision",
            headline="Live sandbox run started",
            summary="The live sandbox run is being translated into web events.",
            bubble="Send the run into the scene.",
        )
        return tuple(self._sanitize_new_events(0))

    def append_round_progress(
        self,
        *,
        round_index: int,
        expected_model_calls: int,
        persona_count: int,
        candidate_count: int,
    ) -> tuple[dict[str, Any], ...]:
        """Append a live-only progress marker before a full round completes."""

        self._require_active_stream()
        if (
            isinstance(round_index, bool)
            or not isinstance(round_index, int)
            or round_index < 1
        ):
            raise WebEventMappingError("round_index must be a positive integer.")
        for value, label in (
            (expected_model_calls, "expected_model_calls"),
            (persona_count, "persona_count"),
            (candidate_count, "candidate_count"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise WebEventMappingError(f"{label} must be a non-negative integer.")
        start_index = len(self._events)
        self._append_event(
            "round_progress",
            round_index,
            actor_id="decision",
            actor_role="decision",
            headline=f"Round {round_index} is calling model agents",
            summary=(
                f"Round {round_index} has started real model calls. "
                f"This round expects about {expected_model_calls} provider calls "
                "before consumer bubbles, reward, and UCB updates can appear."
            ),
            bubble="Calling live agents...",
            progress={
                "stage": "model_calls",
                "expectedModelCalls": expected_model_calls,
                "personaCount": persona_count,
                "candidateCount": candidate_count,
                "note": (
                    "Provider-check only verifies a light API path. A real round "
                    "also needs Decision, Consumer, Feedback, and Critic outputs "
                    "to pass the sandbox contracts."
                ),
            },
        )
        return tuple(self._sanitize_new_events(start_index))

    def append_round_stream(
        self,
        round_result: RoundResult,
    ) -> tuple[dict[str, Any], ...]:
        """Append one completed round to an active stream and return new events."""

        self._require_active_stream()
        start_index = len(self._events)
        self._append_round(round_result)
        return tuple(self._sanitize_new_events(start_index))

    def complete_stream(
        self,
        result: SandboxResult,
    ) -> tuple[dict[str, Any], ...]:
        """Append the run completion boundary to an active stream."""

        if not isinstance(result, SandboxResult):
            raise WebEventMappingError("complete_stream needs a SandboxResult.")
        self._require_active_stream()
        start_index = len(self._events)
        self._append_run_completed(result)
        return tuple(self._sanitize_new_events(start_index))

    def fail_stream(
        self,
        error: Exception,
        *,
        round_index: int,
        issue_kind: str = "runtime_error",
    ) -> tuple[dict[str, Any], ...]:
        """Append a failed-run event with a redacted diagnostic message."""

        self._require_active_stream()
        if (
            isinstance(round_index, bool)
            or not isinstance(round_index, int)
            or round_index < 0
        ):
            raise WebEventMappingError("failure round_index must be non-negative.")
        message = str(error) or error.__class__.__name__
        start_index = len(self._events)
        self._append_event(
            "run_failed",
            round_index,
            actor_id="decision",
            actor_role="decision",
            headline="Live sandbox run failed",
            summary=f"Live run stopped before a safe completed round: {message}",
            detail=message,
            bubble="Run failed before the round could close.",
            issue={
                "kind": issue_kind,
                "message": message,
                "errorType": error.__class__.__name__,
                "safeBoundary": "Only events before the failure should be replayed.",
            },
        )
        return tuple(self._sanitize_new_events(start_index))

    def map_round(
        self,
        round_result: RoundResult,
        *,
        run_id: str = "live-round",
    ) -> tuple[dict[str, Any], ...]:
        """Return events for one saved round without run boundary events."""

        if not isinstance(round_result, RoundResult):
            raise WebEventMappingError("map_round needs a RoundResult.")
        self._start_run(run_id)
        self._append_round(round_result)
        return tuple(self._sanitize_payload(event) for event in self._events)

    def _sanitize_new_events(self, start_index: int) -> list[dict[str, Any]]:
        return [self._sanitize_payload(event) for event in self._events[start_index:]]

    def _require_active_stream(self) -> None:
        if not self._run_id:
            raise WebEventMappingError("stream must be started before appending events.")

    def _start_run(self, run_id: str) -> None:
        if not isinstance(run_id, str) or not RUN_ID_PATTERN.fullmatch(run_id):
            raise WebEventMappingError("run_id must be an ASCII web event id prefix.")
        self._events = []
        self._run_id = run_id

    def _append_round(self, round_result: RoundResult) -> None:
        if not isinstance(round_result, RoundResult):
            raise WebEventMappingError("SandboxResult rounds must be RoundResult.")
        round_index = round_result.round_index
        self._append_event(
            "round_started",
            round_index,
            actor_id="decision",
            actor_role="decision",
            headline=f"Round {round_index} started",
            summary=round_result.proposal.decision_note,
            bubble="Open the next strategy test.",
            proposal={
                "decisionNote": round_result.proposal.decision_note,
                "nextValidationQuestion": round_result.proposal.next_validation_question,
                "candidateCount": len(round_result.proposal.candidates),
            },
        )
        self._append_family_events(round_result)
        self._append_strategy_events(round_result.proposal, round_index)
        for strategy_test_index, strategy_test in enumerate(
            round_result.strategy_tests,
            start=1,
        ):
            self._append_strategy_test_events(
                strategy_test,
                round_index,
                strategy_test_index,
            )
        self._append_search_update_events(round_result.search_updates, round_index)
        self._append_event(
            "round_completed",
            round_index,
            actor_id="decision",
            actor_role="decision",
            headline=f"Round {round_index} completed",
            summary=round_result.proposal.next_validation_question,
            bubble="Keep the next validation question visible.",
            evidence={
                "consumerFeedbackSummary": round_result.next_round_evidence.consumer_feedback_summary,
                "feedbackSynthesis": round_result.next_round_evidence.feedback_synthesis,
                "critique": round_result.next_round_evidence.critique,
            },
        )

    def _append_family_events(self, round_result: RoundResult) -> None:
        selection = round_result.search_selection
        if selection is None:
            return
        if not isinstance(selection, SearchSelection):
            raise WebEventMappingError("search_selection must be SearchSelection.")
        for family in selection.brief.selected_families:
            self._append_family_event(selection, family)

    def _append_family_event(
        self,
        selection: SearchSelection,
        family: StrategyFamily,
    ) -> None:
        family_id = family.family_id
        intent = selection.brief.generation_intents[family_id]
        self._append_event(
            "family_selected",
            selection.round_index,
            actor_id="decision",
            actor_role="decision",
            headline="Strategy family selected",
            summary=selection.selection_reasons[family_id],
            bubble=f"Test {family.name}.",
            family={
                "id": family_id,
                "name": family.name,
                "state": intent.replace("_", " "),
                "note": family.win_mechanism,
                "coreBarrier": family.core_barrier,
                "guidance": family.generation_guidance,
                "expectedActionPatterns": list(family.expected_action_patterns),
                "failureSignals": list(family.failure_signals),
                "selectionReason": selection.selection_reasons[family_id],
            },
            internalSearch={
                "kind": "family_selection",
                "ucbScore": self._score_payload(selection.ucb_scores.get(family_id)),
                "generationIntent": intent,
                "selectionReason": selection.selection_reasons[family_id],
                "metricBoundary": (
                    "UCB score is an internal family-search score, "
                    "not a purchase rate or market forecast."
                ),
            },
        )

    def _append_strategy_events(
        self,
        proposal: StrategyProposal,
        round_index: int,
    ) -> None:
        if not isinstance(proposal, StrategyProposal):
            raise WebEventMappingError("round proposal must be StrategyProposal.")
        for strategy in proposal.candidates:
            self._append_event(
                "strategy_proposed",
                round_index,
                actor_id="decision",
                actor_role="decision",
                headline="DecisionAgent proposed a strategy",
                summary=strategy.hypothesis,
                bubble=strategy.name,
                strategy=self._strategy_payload(strategy),
                proposal={
                    "decisionNote": proposal.decision_note,
                    "nextValidationQuestion": proposal.next_validation_question,
                },
            )

    def _append_strategy_test_events(
        self,
        strategy_test: StrategyTestResult,
        round_index: int,
        strategy_test_index: int,
    ) -> None:
        if not isinstance(strategy_test, StrategyTestResult):
            raise WebEventMappingError("strategy_tests must be StrategyTestResult.")
        strategy_name = strategy_test.strategy.name
        for feedback_index, feedback in enumerate(
            strategy_test.consumer_feedbacks,
            start=1,
        ):
            self._append_feedback_event(
                feedback,
                round_index,
                strategy_name,
                feedback_index,
            )
        self._append_summary_event(
            strategy_test.feedback_summary,
            round_index,
            strategy_name,
            strategy_test_index,
        )
        self._append_critique_event(
            strategy_test.critique_report,
            round_index,
            strategy_name,
            strategy_test_index,
        )

    def _append_feedback_event(
        self,
        feedback: ConsumerFeedback,
        round_index: int,
        strategy_name: str,
        feedback_index: int,
    ) -> None:
        if not isinstance(feedback, ConsumerFeedback):
            raise WebEventMappingError("consumer_feedbacks must be ConsumerFeedback.")
        self._append_event(
            "consumer_feedback_ready",
            round_index,
            actor_id=self._consumer_actor_id(feedback.persona_name, feedback_index),
            actor_role="consumer",
            actor_name=feedback.persona_name,
            headline=f"{feedback.persona_name} responded",
            summary=feedback.current_attitude,
            bubble=feedback.strongest_pull,
            strategyName=strategy_name,
            scenarioName=feedback.scenario_name,
            feedback={
                "firstImpression": feedback.first_impression,
                "barrier": feedback.strongest_rejection,
                "repeat": feedback.repeat_purchase.feeling,
                "competitor": feedback.competitor_reaction.likely_shift,
                "pull": feedback.strongest_pull,
                "understoodOffer": feedback.understood_offer,
                "positioning": feedback.perceived_positioning,
                "currentAttitude": feedback.current_attitude,
                "scenarioName": feedback.scenario_name,
                "behaviorDiagnosis": {
                    "firstSignal": feedback.behavior_diagnosis.first_signal,
                    "referencePoint": feedback.behavior_diagnosis.reference_point,
                    "perceivedRisk": feedback.behavior_diagnosis.perceived_risk,
                    "actionFriction": feedback.behavior_diagnosis.action_friction,
                    "dominantDriver": feedback.behavior_diagnosis.dominant_driver,
                },
                "repeatPurchase": {
                    "feeling": feedback.repeat_purchase.feeling,
                    "condition": feedback.repeat_purchase.condition,
                    "habitOrInertia": feedback.repeat_purchase.habit_or_inertia,
                },
                "competitorReaction": {
                    "likelyShift": feedback.competitor_reaction.likely_shift,
                    "reason": feedback.competitor_reaction.reason,
                    "retentionCondition": feedback.competitor_reaction.retention_condition,
                },
                "advocacy": {
                    "recommendationFeeling": feedback.advocacy.recommendation_feeling,
                    "sharingFeeling": feedback.advocacy.sharing_feeling,
                    "friendDescription": feedback.advocacy.friend_description,
                },
                "behaviorNotes": list(feedback.behavior_notes),
            },
        )

    def _append_summary_event(
        self,
        summary: FeedbackSummary,
        round_index: int,
        strategy_name: str,
        strategy_test_index: int,
    ) -> None:
        if not isinstance(summary, FeedbackSummary):
            raise WebEventMappingError("feedback_summary must be FeedbackSummary.")
        self._append_event(
            "feedback_summary_ready",
            round_index,
            actor_id="synthesizer",
            actor_role="synthesizer",
            headline="Feedback synthesis ready",
            summary=summary.overall_feel,
            bubble=self._first_text(summary.next_round_focus, "Qualitative next step ready."),
            strategyName=strategy_name,
            strategyTestIndex=strategy_test_index,
            synthesis={
                "moved": self._first_text(summary.who_was_moved, summary.overall_feel),
                "unmoved": self._first_text(
                    summary.who_was_not_moved,
                    "No unconvinced segment note supplied.",
                ),
                "next": self._first_text(
                    summary.next_round_focus,
                    "Keep validating qualitative weak points.",
                ),
                "repeat": summary.repeat_purchase_feel,
                "competitor": summary.competitor_pressure_feel,
                "missingEvidence": list(summary.missing_evidence),
                "tags": list(summary.qualitative_tags),
                "scenarioNames": list(summary.scenario_names),
                "strongestEvidence": list(summary.strongest_evidence),
                "weakestPoints": list(summary.weakest_points),
                "searchSignals": self._search_signal_payload(summary.search_signals),
            },
        )

    def _append_critique_event(
        self,
        critique: CritiqueReport,
        round_index: int,
        strategy_name: str,
        strategy_test_index: int,
    ) -> None:
        if not isinstance(critique, CritiqueReport):
            raise WebEventMappingError("critique_report must be CritiqueReport.")
        boundary_note = self._first_text(
            critique.product_boundary_risks,
            self._first_text(critique.brand_risks, "No boundary risk note supplied."),
        )
        self._append_event(
            "critique_ready",
            round_index,
            actor_id="critic",
            actor_role="critic",
            headline="Critic review ready",
            summary=self._first_text(critique.main_loopholes, "Critique is ready."),
            bubble=self._first_text(
                critique.must_validate_next,
                "Keep the weak assumptions visible.",
            ),
            strategyName=strategy_name,
            strategyTestIndex=strategy_test_index,
            critique={
                "mainRisk": self._first_text(
                    critique.main_loopholes,
                    "No main loophole supplied.",
                ),
                "boundary": boundary_note,
                "next": self._first_text(
                    critique.must_validate_next,
                    "Validate weak assumptions outside the sandbox.",
                ),
                "execution": list(critique.execution_risks),
                "selfDeception": list(critique.self_deception_checks),
                "unrealisticAssumptions": list(critique.unrealistic_assumptions),
                "productBoundaryRisks": list(critique.product_boundary_risks),
                "brandRisks": list(critique.brand_risks),
                "mustValidateNext": list(critique.must_validate_next),
                "unresolvedQuestions": list(critique.unresolved_questions),
                "evidenceUsed": list(critique.evidence_used),
                "searchRiskSignals": self._search_signal_payload(
                    critique.search_risk_signals
                ),
            },
        )

    def _append_search_update_events(
        self,
        search_updates: Sequence[SearchUpdate],
        round_index: int,
    ) -> None:
        for update in search_updates:
            if not isinstance(update, SearchUpdate):
                raise WebEventMappingError("search_updates must be SearchUpdate.")
            observation = update.observation
            memory_note = self._memory_note(update)
            reward = observation.reward_breakdown
            self._append_event(
                "search_updated",
                round_index,
                actor_id="decision",
                actor_role="decision",
                headline="Search memory updated",
                summary=f"{update.family_id} recorded completed qualitative evidence.",
                bubble="Keep the family memory qualitative.",
                search={
                    "note": memory_note,
                    "families": [
                        {
                            "id": update.family_id,
                            "label": "qualitative memory updated",
                            "tone": "active",
                        }
                    ],
                    "signals": {
                        "strategyName": observation.strategy_name,
                        "summary": getattr(observation.summary_signals, "signal_note", ""),
                        "risk": getattr(observation.critic_signals, "risk_note", ""),
                        "summaryLabels": self._search_signal_payload(
                            observation.summary_signals
                        ),
                        "riskLabels": self._search_signal_payload(
                            observation.critic_signals
                        ),
                    },
                    "internalMetrics": {
                        "metricBoundary": (
                            "Reward, mean reward, and UCB-related values are "
                            "internal search utility signals, not market outcomes."
                        ),
                        "familyId": update.family_id,
                        "reward": reward.reward,
                        "positiveUtility": reward.positive_utility,
                        "riskPenalty": reward.risk_penalty,
                        "positiveComponents": dict(reward.positive_components),
                        "riskComponents": dict(reward.risk_components),
                        "appliedCaps": list(reward.applied_caps),
                        "mappingNote": reward.mapping_note,
                        "stateBefore": self._arm_state_payload(update.state_before),
                        "stateAfter": self._arm_state_payload(update.state_after),
                    },
                },
            )

    def _append_run_completed(self, result: SandboxResult) -> None:
        if result.rounds:
            latest_round = result.rounds[-1].round_index
            strategy_summary = self._first_text(
                result.recommended_strategy_directions,
                "completed qualitative directions",
            )
            summary = f"Completed run with current direction: {strategy_summary}."
        else:
            latest_round = 0
            summary = "No completed sandbox rounds were available for playback."
        self._append_event(
            "run_completed",
            latest_round,
            actor_id="synthesizer",
            actor_role="synthesizer",
            headline="Live sandbox run completed",
            summary=summary,
            bubble="The event trail is ready.",
            detail=self._join_texts(
                result.real_market_validation_questions,
                "Real-market validation questions remain outside this playback.",
            ),
            result={
                "directions": list(result.recommended_strategy_directions),
                "pausedDirections": list(result.paused_strategy_directions),
                "audienceInsights": list(result.audience_insights),
                "risks": list(result.strategy_risks),
                "validationQuestions": list(result.real_market_validation_questions),
                "decisionLogic": list(result.decision_logic),
                "searchNotes": list(result.search_notes),
            },
        )

    def _append_event(
        self,
        event_type: str,
        round_index: int,
        *,
        actor_id: str,
        actor_role: str,
        headline: str,
        summary: str,
        **extras: Any,
    ) -> None:
        if event_type not in WEB_EVENT_TYPES:
            raise WebEventMappingError(f"Unknown web event type: {event_type}.")
        if (
            isinstance(round_index, bool)
            or not isinstance(round_index, int)
            or round_index < 0
        ):
            raise WebEventMappingError("Web event round must be a non-negative integer.")
        event_number = len(self._events) + 1
        event = {
            "id": f"{self._run_id}-{event_number:04d}-{event_type}",
            "type": event_type,
            "contractVersion": WEB_EVENT_CONTRACT_VERSION,
            "round": round_index,
            "actorId": self._require_text(actor_id, "actor_id"),
            "actorRole": self._require_text(actor_role, "actor_role"),
            "headline": self._require_text(headline, "headline"),
            "summary": self._require_text(summary, "summary"),
        }
        event.update(extras)
        self._events.append(event)

    def _strategy_payload(self, strategy: Strategy) -> dict[str, Any]:
        if not isinstance(strategy, Strategy):
            raise WebEventMappingError("proposal candidates must be Strategy.")
        return {
            "name": strategy.name,
            "familyId": strategy.family_id,
            "intent": strategy.hypothesis,
            "familyFit": strategy.family_fit_note,
            "actions": [self._action_payload(action) for action in strategy.actions],
            "targets": list(strategy.target_consumers),
            "tradeoffs": list(strategy.expected_tradeoffs),
        }

    def _action_payload(self, action: StrategyAction) -> dict[str, Any]:
        if not isinstance(action, StrategyAction):
            raise WebEventMappingError("strategy actions must be StrategyAction.")
        return {
            "category": action.category.title(),
            "note": action.summary,
            "reason": action.reason,
            "parameters": self._json_ready(dict(action.parameters)),
            "productClaims": list(action.product_claims),
        }

    def _memory_note(self, update: SearchUpdate) -> str:
        memory = update.observation.qualitative_memory
        return self._join_texts(
            memory,
            "Completed family evidence was saved for later qualitative search memory.",
        )

    @staticmethod
    def _arm_state_payload(state: Any) -> dict[str, Any]:
        return {
            "pullCount": state.pull_count,
            "rewardSum": state.reward_sum,
            "meanReward": state.mean_reward,
            "lastSelectedRound": state.last_selected_round,
        }

    @staticmethod
    def _score_payload(score: float | None) -> dict[str, Any]:
        if score is None:
            return {"value": None, "display": "not recorded"}
        if math.isinf(score):
            return {"value": None, "display": "cold start infinity"}
        return {"value": float(score), "display": "numeric internal UCB score"}

    @staticmethod
    def _search_signal_payload(signals: Any) -> dict[str, Any] | None:
        if signals is None:
            return None
        values = getattr(signals, "__dict__", None)
        if not isinstance(values, Mapping):
            return None
        return {str(key): value for key, value in values.items()}

    def _sanitize_payload(self, value: Any) -> Any:
        safe_value = self._json_ready(value)
        if isinstance(safe_value, str):
            return self._redact_text(safe_value)
        if isinstance(safe_value, list):
            return [self._sanitize_payload(item) for item in safe_value]
        if isinstance(safe_value, dict):
            return {
                str(key): self._sanitize_payload(item)
                for key, item in safe_value.items()
            }
        return safe_value

    def _redact_text(self, text: str) -> str:
        redacted = text
        for value in self._sensitive_values:
            redacted = redacted.replace(value, "[redacted]")
        return redacted

    @classmethod
    def _json_ready(cls, value: Any) -> Any:
        if isinstance(value, Mapping):
            return {str(key): cls._json_ready(item) for key, item in value.items()}
        if isinstance(value, tuple):
            return [cls._json_ready(item) for item in value]
        if isinstance(value, list):
            return [cls._json_ready(item) for item in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    @staticmethod
    def _consumer_actor_id(persona_name: str, fallback_index: int) -> str:
        token = ASCII_TOKEN_PATTERN.sub("-", persona_name.lower()).strip("-")
        return f"consumer-{token or fallback_index}"

    @classmethod
    def _join_texts(cls, texts: Sequence[str], fallback: str) -> str:
        items = [cls._require_text(item, "text item") for item in texts if item]
        return "; ".join(items) if items else fallback

    @classmethod
    def _first_text(cls, texts: Sequence[str], fallback: str) -> str:
        for item in texts:
            if isinstance(item, str) and item.strip():
                return item.strip()
        return fallback

    @staticmethod
    def _require_text(value: Any, label: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise WebEventMappingError(f"{label} must be non-empty text.")
        return value.strip()
