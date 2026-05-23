"""Qualitative feedback synthesis contracts for the marketing sandbox."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Callable, Mapping, Protocol, Sequence

from .consumer_agent import ConsumerFeedback
from .decision_agent import Strategy


RawFeedbackSummaryResponse = str | Mapping[str, Any]

FORBIDDEN_SUMMARY_TERMS = re.compile(
    r"(?i)("
    r"overall score|total score|dimension score|ranking score|rank score|"
    r"conversion rate|repurchase rate|repeat purchase rate|purchase probability|"
    r"repurchase probability|market share|market percentage|sales forecast|"
    r"总分|维度分|排名分|转化率|复购率|购买概率|复购概率|"
    r"市场份额|市场占比|销量预测"
    r")"
)

FORBIDDEN_SUMMARY_KEYS = re.compile(
    r"(?i)("
    r"score|rank[_ ]?score|dimension[_ ]?score|conversion[_ ]?rate|"
    r"repurchase[_ ]?rate|purchase[_ ]?probability|"
    r"repurchase[_ ]?probability|market[_ ]?share|market[_ ]?percentage|"
    r"总分|维度分|排名分|转化率|复购率|概率|市场份额|市场占比"
    r")"
)


class FeedbackSynthesizerError(Exception):
    """Base error for feedback synthesis failures."""


class FeedbackSynthesisInputError(FeedbackSynthesizerError):
    """Raised when feedback synthesis lacks strategy or feedback context."""


class FeedbackSynthesisOutputError(FeedbackSynthesizerError):
    """Raised when a synthesis backend violates the summary contract."""


class FeedbackSynthesizerBackend(Protocol):
    """Minimal interface expected from a feedback synthesis adapter."""

    def generate(self, prompt: str) -> RawFeedbackSummaryResponse:
        """Return a JSON string or an already parsed mapping."""


@dataclass(frozen=True)
class FeedbackSearchSignals:
    """Controlled qualitative labels used by the system search layer."""

    core_target_response: str
    trial_momentum: str
    strategy_clarity: str
    repeat_logic: str
    competitor_resilience: str
    evidence_consistency: str
    signal_note: str


@dataclass(frozen=True)
class FeedbackSummary:
    """Qualitative round summary derived from consumer feedback."""

    strategy_name: str
    scenario_names: tuple[str, ...]
    overall_feel: str
    who_was_moved: tuple[str, ...]
    who_was_not_moved: tuple[str, ...]
    strongest_evidence: tuple[str, ...]
    weakest_points: tuple[str, ...]
    repeat_purchase_feel: str
    competitor_pressure_feel: str
    next_round_focus: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    qualitative_tags: tuple[str, ...]
    search_signals: FeedbackSearchSignals | None = None


class FeedbackSynthesizer:
    """Summarize consumer feedback without inventing numeric evaluation."""

    def __init__(
        self,
        backend: FeedbackSynthesizerBackend
        | Callable[[str], RawFeedbackSummaryResponse],
    ) -> None:
        self._backend = backend
        self.last_prompt: str | None = None

    def synthesize(
        self,
        strategy: Strategy,
        feedbacks: Sequence[ConsumerFeedback],
        *,
        core_target: str,
        prior_summary: str = "",
    ) -> FeedbackSummary:
        """Return one qualitative summary for a strategy feedback batch."""

        prompt = self.build_prompt(
            strategy,
            feedbacks,
            core_target=core_target,
            prior_summary=prior_summary,
        )
        self.last_prompt = prompt
        response = self._call_backend(prompt)
        payload = self._load_payload(response)
        summary = self._parse_summary(payload, strategy, feedbacks)
        self._validate_summary(summary)
        return summary

    def build_prompt(
        self,
        strategy: Strategy,
        feedbacks: Sequence[ConsumerFeedback],
        *,
        core_target: str,
        prior_summary: str = "",
    ) -> str:
        """Build the qualitative synthesis prompt without calling a backend."""

        self._validate_inputs(strategy, feedbacks, core_target)
        prior = prior_summary.strip() or "none supplied"
        return f"""You are the FeedbackSynthesizer in an AI marketing sandbox.

Your job:
- Synthesize the consumer feedback for one candidate strategy.
- Describe the strategy's overall feel, who is moved, who is not moved, where
  repeat-purchase logic feels natural or weak, and how competitor pressure lands.
- Give the DecisionAgent qualitative direction for the next round.

Do not:
- Output overall scores, dimension scores, ranking scores, probabilities,
  conversion rates, repurchase rates, market-share predictions, or sales forecasts.
- Pretend consumer agents are real market statistics.
- Replace synthesis with a brand-manager proposal or a critic report.

Core target:
{core_target.strip()}

Strategy under review:
{self._render_strategy(strategy)}

Consumer feedback batch:
{self._render_feedback_batch(feedbacks)}

Prior summary context:
{prior}

Return JSON only with exactly this shape:
{{
  "overall_feel": "what kind of strategy this now feels like",
  "who_was_moved": ["consumer segment reaction that was moved"],
  "who_was_not_moved": ["consumer segment reaction that stayed unconvinced"],
  "strongest_evidence": ["strongest qualitative signal in the feedback"],
  "weakest_points": ["weakest qualitative signal or tension"],
  "repeat_purchase_feel": "how repeat purchase feels from this feedback",
  "competitor_pressure_feel": "how this strategy feels under competitor pressure",
  "next_round_focus": ["direction the next round should test"],
        "missing_evidence": ["what this feedback still cannot establish"],
  "qualitative_tags": ["non-numeric tag such as trust-sensitive or short-term trial"],
  "search_signals": {{
    "core_target_response": "moved|mixed|unmoved",
    "trial_momentum": "pulled_closer|conditional|pushed_away",
    "strategy_clarity": "clear|partial|confusing",
    "repeat_logic": "natural|conditional|weak",
    "competitor_resilience": "holds|fragile|displaced",
    "evidence_consistency": "consistent|mixed|thin",
    "signal_note": "qualitative reason for these search labels"
  }}
}}
"""

    def _call_backend(self, prompt: str) -> RawFeedbackSummaryResponse:
        backend_generate = getattr(self._backend, "generate", None)
        if callable(backend_generate):
            return backend_generate(prompt)
        if callable(self._backend):
            return self._backend(prompt)
        raise FeedbackSynthesisInputError("FeedbackSynthesizer backend must be callable.")

    def _load_payload(self, response: RawFeedbackSummaryResponse) -> Mapping[str, Any]:
        if isinstance(response, str):
            try:
                payload = json.loads(response)
            except json.JSONDecodeError as exc:
                raise FeedbackSynthesisOutputError(
                    "FeedbackSynthesizer backend returned invalid JSON."
                ) from exc
        else:
            payload = response
        if not isinstance(payload, Mapping):
            raise FeedbackSynthesisOutputError(
                "FeedbackSynthesizer output must be a JSON object."
            )
        self._reject_forbidden_payload(payload)
        return payload

    def _parse_summary(
        self,
        payload: Mapping[str, Any],
        strategy: Strategy,
        feedbacks: Sequence[ConsumerFeedback],
    ) -> FeedbackSummary:
        self._check_keys(
            payload,
            required={
                "overall_feel",
                "who_was_moved",
                "who_was_not_moved",
                "strongest_evidence",
                "weakest_points",
                "repeat_purchase_feel",
                "competitor_pressure_feel",
                "next_round_focus",
                "missing_evidence",
                "qualitative_tags",
            },
            allowed={
                "overall_feel",
                "who_was_moved",
                "who_was_not_moved",
                "strongest_evidence",
                "weakest_points",
                "repeat_purchase_feel",
                "competitor_pressure_feel",
                "next_round_focus",
                "missing_evidence",
                "qualitative_tags",
                "search_signals",
            },
            label="feedback summary",
        )
        scenario_names = tuple(dict.fromkeys(item.scenario_name for item in feedbacks))
        return FeedbackSummary(
            strategy_name=strategy.name,
            scenario_names=scenario_names,
            overall_feel=self._require_text(payload["overall_feel"], "overall_feel"),
            who_was_moved=self._parse_text_sequence(
                payload["who_was_moved"], "who_was_moved"
            ),
            who_was_not_moved=self._parse_text_sequence(
                payload["who_was_not_moved"], "who_was_not_moved"
            ),
            strongest_evidence=self._parse_text_sequence(
                payload["strongest_evidence"], "strongest_evidence"
            ),
            weakest_points=self._parse_text_sequence(
                payload["weakest_points"], "weakest_points"
            ),
            repeat_purchase_feel=self._require_text(
                payload["repeat_purchase_feel"], "repeat_purchase_feel"
            ),
            competitor_pressure_feel=self._require_text(
                payload["competitor_pressure_feel"], "competitor_pressure_feel"
            ),
            next_round_focus=self._parse_text_sequence(
                payload["next_round_focus"], "next_round_focus"
            ),
            missing_evidence=self._parse_text_sequence(
                payload["missing_evidence"], "missing_evidence"
            ),
            qualitative_tags=self._parse_text_sequence(
                payload["qualitative_tags"], "qualitative_tags"
            ),
            search_signals=self._parse_search_signals(payload.get("search_signals")),
        )

    def _validate_summary(self, summary: FeedbackSummary) -> None:
        for text in (
            summary.strategy_name,
            *summary.scenario_names,
            summary.overall_feel,
            *summary.who_was_moved,
            *summary.who_was_not_moved,
            *summary.strongest_evidence,
            *summary.weakest_points,
            summary.repeat_purchase_feel,
            summary.competitor_pressure_feel,
            *summary.next_round_focus,
            *summary.missing_evidence,
            *summary.qualitative_tags,
        ):
            self._reject_forbidden_terms(text)
        if summary.search_signals is not None:
            for text in summary.search_signals.__dict__.values():
                self._reject_forbidden_terms(text)

    @staticmethod
    def _validate_inputs(
        strategy: Strategy, feedbacks: Sequence[ConsumerFeedback], core_target: str
    ) -> None:
        if not strategy.name.strip() or not strategy.actions:
            raise FeedbackSynthesisInputError(
                "FeedbackSynthesizer needs a named strategy with actions."
            )
        if not feedbacks:
            raise FeedbackSynthesisInputError(
                "FeedbackSynthesizer needs at least one ConsumerFeedback."
            )
        if not core_target.strip():
            raise FeedbackSynthesisInputError("FeedbackSynthesizer needs a core target.")

    @classmethod
    def _reject_forbidden_payload(cls, value: Any) -> None:
        if isinstance(value, Mapping):
            for key, nested in value.items():
                normalized_key = str(key).replace("_", " ")
                if FORBIDDEN_SUMMARY_KEYS.search(normalized_key):
                    raise FeedbackSynthesisOutputError(
                        "FeedbackSynthesizer output includes a forbidden scoring or forecast field."
                    )
                cls._reject_forbidden_payload(nested)
        elif isinstance(value, str):
            cls._reject_forbidden_terms(value)
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            for nested in value:
                cls._reject_forbidden_payload(nested)

    @staticmethod
    def _reject_forbidden_terms(text: str) -> None:
        if FORBIDDEN_SUMMARY_TERMS.search(text):
            raise FeedbackSynthesisOutputError(
                "FeedbackSynthesizer output includes a forbidden score, probability, or market forecast."
            )

    @staticmethod
    def _render_strategy(strategy: Strategy) -> str:
        action_lines = []
        for action in strategy.actions:
            params = json.dumps(dict(action.parameters), ensure_ascii=True, sort_keys=True)
            action_lines.append(
                f"- {action.category}: {action.summary} | reason: {action.reason} | parameters: {params}"
            )
        targets = ", ".join(strategy.target_consumers)
        tradeoffs = ", ".join(strategy.expected_tradeoffs)
        return (
            f"- name: {strategy.name}\n"
            f"- hypothesis: {strategy.hypothesis}\n"
            f"- target consumers: {targets}\n"
            f"- expected tradeoffs: {tradeoffs}\n"
            f"- actions:\n" + "\n".join(action_lines)
        )

    @classmethod
    def _render_feedback_batch(cls, feedbacks: Sequence[ConsumerFeedback]) -> str:
        blocks = []
        for feedback in feedbacks:
            notes = "; ".join(feedback.behavior_notes)
            blocks.append(
                f"- persona: {feedback.persona_name}\n"
                f"  scenario: {feedback.scenario_name}\n"
                f"  first impression: {feedback.first_impression}\n"
                f"  attitude: {feedback.current_attitude}\n"
                f"  strongest pull: {feedback.strongest_pull}\n"
                f"  strongest rejection: {feedback.strongest_rejection}\n"
                f"  reference point: {feedback.behavior_diagnosis.reference_point}\n"
                f"  perceived risk: {feedback.behavior_diagnosis.perceived_risk}\n"
                f"  repeat feeling: {feedback.repeat_purchase.feeling}\n"
                f"  competitor shift: {feedback.competitor_reaction.likely_shift}\n"
                f"  advocacy: {feedback.advocacy.recommendation_feeling}\n"
                f"  behavior notes: {notes}"
            )
        return "\n".join(blocks)

    @staticmethod
    def _check_keys(
        item: Mapping[str, Any],
        *,
        required: set[str],
        allowed: set[str],
        label: str,
    ) -> None:
        keys = set(item.keys())
        missing = required - keys
        if missing:
            rendered = ", ".join(sorted(missing))
            raise FeedbackSynthesisOutputError(f"{label} is missing keys: {rendered}.")
        extra = keys - allowed
        if extra:
            rendered = ", ".join(sorted(extra))
            raise FeedbackSynthesisOutputError(f"{label} has unsupported keys: {rendered}.")

    @staticmethod
    def _require_text(value: Any, label: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise FeedbackSynthesisOutputError(f"{label} must be non-empty text.")
        return value.strip()

    def _parse_text_sequence(self, value: Any, label: str) -> tuple[str, ...]:
        if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
            raise FeedbackSynthesisOutputError(f"{label} must be a list.")
        parsed = tuple(self._require_text(item, label) for item in value)
        if not parsed:
            raise FeedbackSynthesisOutputError(f"{label} must contain at least one item.")
        return parsed

    def _parse_search_signals(self, item: Any) -> FeedbackSearchSignals | None:
        if item is None:
            return None
        if not isinstance(item, Mapping):
            raise FeedbackSynthesisOutputError("search_signals must be a JSON object.")
        required = {
            "core_target_response",
            "trial_momentum",
            "strategy_clarity",
            "repeat_logic",
            "competitor_resilience",
            "evidence_consistency",
            "signal_note",
        }
        self._check_keys(
            item,
            required=required,
            allowed=required,
            label="search_signals",
        )
        return FeedbackSearchSignals(
            core_target_response=self._require_label(
                item["core_target_response"],
                "search_signals.core_target_response",
                {"moved", "mixed", "unmoved"},
            ),
            trial_momentum=self._require_label(
                item["trial_momentum"],
                "search_signals.trial_momentum",
                {"pulled_closer", "conditional", "pushed_away"},
            ),
            strategy_clarity=self._require_label(
                item["strategy_clarity"],
                "search_signals.strategy_clarity",
                {"clear", "partial", "confusing"},
            ),
            repeat_logic=self._require_label(
                item["repeat_logic"],
                "search_signals.repeat_logic",
                {"natural", "conditional", "weak"},
            ),
            competitor_resilience=self._require_label(
                item["competitor_resilience"],
                "search_signals.competitor_resilience",
                {"holds", "fragile", "displaced"},
            ),
            evidence_consistency=self._require_label(
                item["evidence_consistency"],
                "search_signals.evidence_consistency",
                {"consistent", "mixed", "thin"},
            ),
            signal_note=self._require_text(
                item["signal_note"], "search_signals.signal_note"
            ),
        )

    @staticmethod
    def _require_label(value: Any, label: str, allowed: set[str]) -> str:
        parsed = FeedbackSynthesizer._require_text(value, label)
        if parsed not in allowed:
            allowed_text = ", ".join(sorted(allowed))
            raise FeedbackSynthesisOutputError(
                f"{label} must use one of: {allowed_text}."
            )
        return parsed
