"""Critic agent contracts for the marketing sandbox."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Callable, Mapping, Protocol, Sequence

from .consumer_agent import ConsumerFeedback
from .decision_agent import Strategy
from .feedback_synthesizer import FeedbackSummary


RawCritiqueResponse = str | Mapping[str, Any]

FORBIDDEN_CRITIC_TERMS = re.compile(
    r"(?i)("
    r"risk probability|loss probability|budget loss|profit forecast|"
    r"revenue forecast|sales forecast|conversion rate|repurchase rate|"
    r"purchase probability|market share|"
    r"风险概率|损失概率|预算损失|利润预测|收入预测|销量预测|"
    r"转化率|复购率|购买概率|市场份额"
    r")"
)

FORBIDDEN_CRITIC_KEYS = re.compile(
    r"(?i)("
    r"risk[_ ]?probability|loss[_ ]?probability|budget[_ ]?loss|"
    r"profit[_ ]?forecast|revenue[_ ]?forecast|sales[_ ]?forecast|"
    r"conversion[_ ]?rate|repurchase[_ ]?rate|purchase[_ ]?probability|"
    r"market[_ ]?share|"
    r"风险概率|损失概率|预算损失|利润预测|收入预测|销量预测|"
    r"转化率|复购率|购买概率|市场份额"
    r")"
)

CONSUMER_VOICE_KEYS = re.compile(
    r"(?i)(first[_ ]?impression|current[_ ]?attitude|purchase[_ ]?feeling|"
    r"第一印象|购买态度)"
)


class CriticAgentError(Exception):
    """Base error for critic failures."""


class CriticInputError(CriticAgentError):
    """Raised when the critic lacks strategy or evidence context."""


class CriticOutputError(CriticAgentError):
    """Raised when critic output violates the critique contract."""


class CriticBackend(Protocol):
    """Minimal interface expected from a CriticAgent model adapter."""

    def generate(self, prompt: str) -> RawCritiqueResponse:
        """Return a JSON string or an already parsed mapping."""


@dataclass(frozen=True)
class CriticSearchSignals:
    """Controlled risk labels for the system search layer."""

    product_boundary_risk: str
    brand_risk: str
    execution_risk: str
    self_deception_risk: str
    risk_note: str


@dataclass(frozen=True)
class CriticContext:
    """Boundaries and evidence the critic should use."""

    product_boundaries: tuple[str, ...]
    brand_boundaries: tuple[str, ...]
    execution_boundaries: tuple[str, ...] = ()
    known_facts: tuple[str, ...] = ()


@dataclass(frozen=True)
class CritiqueReport:
    """Qualitative critique of one strategy round."""

    strategy_name: str
    main_loopholes: tuple[str, ...]
    unrealistic_assumptions: tuple[str, ...]
    product_boundary_risks: tuple[str, ...]
    brand_risks: tuple[str, ...]
    execution_risks: tuple[str, ...]
    self_deception_checks: tuple[str, ...]
    must_validate_next: tuple[str, ...]
    unresolved_questions: tuple[str, ...]
    evidence_used: tuple[str, ...]
    search_risk_signals: CriticSearchSignals | None = None


class CriticAgent:
    """Adversarial reviewer for qualitative marketing strategy rounds."""

    def __init__(
        self,
        backend: CriticBackend | Callable[[str], RawCritiqueResponse],
    ) -> None:
        self._backend = backend
        self.last_prompt: str | None = None

    def critique(
        self,
        strategy: Strategy,
        feedbacks: Sequence[ConsumerFeedback],
        feedback_summary: FeedbackSummary,
        context: CriticContext,
    ) -> CritiqueReport:
        """Return a critique grounded in strategy, feedback, and boundaries."""

        prompt = self.build_prompt(strategy, feedbacks, feedback_summary, context)
        self.last_prompt = prompt
        response = self._call_backend(prompt)
        payload = self._load_payload(response)
        report = self._parse_report(payload, strategy)
        self._validate_report(report)
        return report

    def build_prompt(
        self,
        strategy: Strategy,
        feedbacks: Sequence[ConsumerFeedback],
        feedback_summary: FeedbackSummary,
        context: CriticContext,
    ) -> str:
        """Build a critique prompt without calling a backend."""

        self._validate_inputs(strategy, feedbacks, feedback_summary, context)
        return f"""You are the CriticAgent in an AI marketing sandbox.

Your job:
- Attack weak assumptions in the current strategy.
- Check product boundary risk, brand risk, execution risk, evidence gaps, and
  where the sandbox might be flattering itself.
- Use the strategy, consumer feedback, feedback summary, and supplied boundaries.

Do not:
- Speak as a consumer or repeat consumer first-impression feedback as your report.
- Invent risk probabilities, budget losses, sales forecasts, revenue forecasts,
  profit forecasts, conversion rates, repurchase rates, market share, or market outcomes.
- Invent product boundaries or treat synthetic feedback as real market statistics.

Strategy under critique:
{self._render_strategy(strategy)}

Consumer feedback evidence:
{self._render_feedback_batch(feedbacks)}

Feedback summary evidence:
{self._render_summary(feedback_summary)}

Product boundaries:
{self._format_lines(context.product_boundaries)}

Brand boundaries:
{self._format_lines(context.brand_boundaries)}

Execution boundaries:
{self._format_lines(context.execution_boundaries)}

Known facts:
{self._format_lines(context.known_facts)}

Return JSON only with exactly this shape:
{{
  "main_loopholes": ["largest strategy loophole"],
  "unrealistic_assumptions": ["assumption that may not hold"],
  "product_boundary_risks": ["product-boundary or claim risk"],
  "brand_risks": ["brand risk"],
  "execution_risks": ["execution risk"],
  "self_deception_checks": ["where the sandbox may flatter itself"],
  "must_validate_next": ["question or condition that must be tested next"],
  "unresolved_questions": ["what still cannot be concluded"],
  "evidence_used": ["qualitative evidence or boundary used for the critique"],
  "search_risk_signals": {{
    "product_boundary_risk": "contained|watch|serious",
    "brand_risk": "contained|watch|serious",
    "execution_risk": "contained|watch|serious",
    "self_deception_risk": "contained|watch|serious",
    "risk_note": "qualitative reason for these risk labels"
  }}
}}
"""

    def _call_backend(self, prompt: str) -> RawCritiqueResponse:
        backend_generate = getattr(self._backend, "generate", None)
        if callable(backend_generate):
            return backend_generate(prompt)
        if callable(self._backend):
            return self._backend(prompt)
        raise CriticInputError("CriticAgent backend must be callable.")

    def _load_payload(self, response: RawCritiqueResponse) -> Mapping[str, Any]:
        if isinstance(response, str):
            try:
                payload = json.loads(response)
            except json.JSONDecodeError as exc:
                raise CriticOutputError("Critic backend returned invalid JSON.") from exc
        else:
            payload = response
        if not isinstance(payload, Mapping):
            raise CriticOutputError("Critic output must be a JSON object.")
        self._reject_forbidden_payload(payload)
        return payload

    def _parse_report(
        self, payload: Mapping[str, Any], strategy: Strategy
    ) -> CritiqueReport:
        required = {
            "main_loopholes",
            "unrealistic_assumptions",
            "product_boundary_risks",
            "brand_risks",
            "execution_risks",
            "self_deception_checks",
            "must_validate_next",
            "unresolved_questions",
            "evidence_used",
        }
        self._check_keys(
            payload,
            required=required,
            allowed=required | {"search_risk_signals"},
            label="critique",
        )
        return CritiqueReport(
            strategy_name=strategy.name,
            main_loopholes=self._parse_text_sequence(
                payload["main_loopholes"], "main_loopholes"
            ),
            unrealistic_assumptions=self._parse_text_sequence(
                payload["unrealistic_assumptions"], "unrealistic_assumptions"
            ),
            product_boundary_risks=self._parse_text_sequence(
                payload["product_boundary_risks"], "product_boundary_risks"
            ),
            brand_risks=self._parse_text_sequence(payload["brand_risks"], "brand_risks"),
            execution_risks=self._parse_text_sequence(
                payload["execution_risks"], "execution_risks"
            ),
            self_deception_checks=self._parse_text_sequence(
                payload["self_deception_checks"], "self_deception_checks"
            ),
            must_validate_next=self._parse_text_sequence(
                payload["must_validate_next"], "must_validate_next"
            ),
            unresolved_questions=self._parse_text_sequence(
                payload["unresolved_questions"], "unresolved_questions"
            ),
            evidence_used=self._parse_text_sequence(
                payload["evidence_used"], "evidence_used"
            ),
            search_risk_signals=self._parse_search_risk_signals(
                payload.get("search_risk_signals")
            ),
        )

    def _validate_report(self, report: CritiqueReport) -> None:
        for text in (
            report.strategy_name,
            *report.main_loopholes,
            *report.unrealistic_assumptions,
            *report.product_boundary_risks,
            *report.brand_risks,
            *report.execution_risks,
            *report.self_deception_checks,
            *report.must_validate_next,
            *report.unresolved_questions,
            *report.evidence_used,
        ):
            self._reject_forbidden_terms(text)
        if report.search_risk_signals is not None:
            for text in report.search_risk_signals.__dict__.values():
                self._reject_forbidden_terms(text)

    @staticmethod
    def _validate_inputs(
        strategy: Strategy,
        feedbacks: Sequence[ConsumerFeedback],
        feedback_summary: FeedbackSummary,
        context: CriticContext,
    ) -> None:
        if not strategy.name.strip() or not strategy.actions:
            raise CriticInputError("CriticAgent needs a named strategy with actions.")
        if not feedbacks:
            raise CriticInputError("CriticAgent needs at least one ConsumerFeedback.")
        if feedback_summary.strategy_name != strategy.name:
            raise CriticInputError("FeedbackSummary must match the strategy under critique.")
        if not context.product_boundaries:
            raise CriticInputError("CriticContext needs product boundaries.")
        if not context.brand_boundaries:
            raise CriticInputError("CriticContext needs brand boundaries.")

    @classmethod
    def _reject_forbidden_payload(cls, value: Any) -> None:
        if isinstance(value, Mapping):
            for key, nested in value.items():
                normalized_key = str(key).replace("_", " ")
                if FORBIDDEN_CRITIC_KEYS.search(normalized_key):
                    raise CriticOutputError(
                        "CriticAgent output includes a forbidden forecast or probability field."
                    )
                if CONSUMER_VOICE_KEYS.search(normalized_key):
                    raise CriticOutputError(
                        "CriticAgent output includes a consumer-feedback field."
                    )
                cls._reject_forbidden_payload(nested)
        elif isinstance(value, str):
            cls._reject_forbidden_terms(value)
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            for nested in value:
                cls._reject_forbidden_payload(nested)

    @staticmethod
    def _reject_forbidden_terms(text: str) -> None:
        if FORBIDDEN_CRITIC_TERMS.search(text):
            raise CriticOutputError(
                "CriticAgent output includes a forbidden probability, loss, or forecast."
            )

    @staticmethod
    def _render_strategy(strategy: Strategy) -> str:
        action_lines = []
        for action in strategy.actions:
            params = json.dumps(dict(action.parameters), ensure_ascii=True, sort_keys=True)
            claims = ", ".join(action.product_claims) or "none"
            action_lines.append(
                f"- {action.category}: {action.summary} | reason: {action.reason} "
                f"| parameters: {params} | product claims: {claims}"
            )
        return (
            f"- name: {strategy.name}\n"
            f"- hypothesis: {strategy.hypothesis}\n"
            f"- targets: {', '.join(strategy.target_consumers)}\n"
            f"- expected tradeoffs: {', '.join(strategy.expected_tradeoffs)}\n"
            f"- actions:\n" + "\n".join(action_lines)
        )

    @staticmethod
    def _render_feedback_batch(feedbacks: Sequence[ConsumerFeedback]) -> str:
        blocks = []
        for feedback in feedbacks:
            blocks.append(
                f"- persona: {feedback.persona_name}\n"
                f"  scenario: {feedback.scenario_name}\n"
                f"  attitude: {feedback.current_attitude}\n"
                f"  strongest pull: {feedback.strongest_pull}\n"
                f"  strongest rejection: {feedback.strongest_rejection}\n"
                f"  perceived risk: {feedback.behavior_diagnosis.perceived_risk}\n"
                f"  repeat feeling: {feedback.repeat_purchase.feeling}\n"
                f"  competitor shift: {feedback.competitor_reaction.likely_shift}"
            )
        return "\n".join(blocks)

    @staticmethod
    def _render_summary(summary: FeedbackSummary) -> str:
        return (
            f"- strategy: {summary.strategy_name}\n"
            f"- scenarios: {', '.join(summary.scenario_names)}\n"
            f"- overall feel: {summary.overall_feel}\n"
            f"- moved: {'; '.join(summary.who_was_moved)}\n"
            f"- not moved: {'; '.join(summary.who_was_not_moved)}\n"
            f"- weakest points: {'; '.join(summary.weakest_points)}\n"
            f"- next focus: {'; '.join(summary.next_round_focus)}\n"
            f"- missing evidence: {'; '.join(summary.missing_evidence)}"
        )

    @staticmethod
    def _format_lines(lines: Sequence[str]) -> str:
        cleaned = [line.strip() for line in lines if line.strip()]
        return "\n".join(f"- {line}" for line in cleaned) or "- none supplied"

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
            raise CriticOutputError(f"{label} is missing keys: {rendered}.")
        extra = keys - allowed
        if extra:
            rendered = ", ".join(sorted(extra))
            raise CriticOutputError(f"{label} has unsupported keys: {rendered}.")

    @staticmethod
    def _require_text(value: Any, label: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise CriticOutputError(f"{label} must be non-empty text.")
        return value.strip()

    def _parse_text_sequence(self, value: Any, label: str) -> tuple[str, ...]:
        if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
            raise CriticOutputError(f"{label} must be a list.")
        parsed = tuple(self._require_text(item, label) for item in value)
        if not parsed:
            raise CriticOutputError(f"{label} must contain at least one item.")
        return parsed

    def _parse_search_risk_signals(self, item: Any) -> CriticSearchSignals | None:
        if item is None:
            return None
        if not isinstance(item, Mapping):
            raise CriticOutputError("search_risk_signals must be a JSON object.")
        required = {
            "product_boundary_risk",
            "brand_risk",
            "execution_risk",
            "self_deception_risk",
            "risk_note",
        }
        self._check_keys(
            item,
            required=required,
            allowed=required,
            label="search_risk_signals",
        )
        return CriticSearchSignals(
            product_boundary_risk=self._require_risk_label(
                item["product_boundary_risk"],
                "search_risk_signals.product_boundary_risk",
            ),
            brand_risk=self._require_risk_label(
                item["brand_risk"], "search_risk_signals.brand_risk"
            ),
            execution_risk=self._require_risk_label(
                item["execution_risk"], "search_risk_signals.execution_risk"
            ),
            self_deception_risk=self._require_risk_label(
                item["self_deception_risk"],
                "search_risk_signals.self_deception_risk",
            ),
            risk_note=self._require_text(
                item["risk_note"], "search_risk_signals.risk_note"
            ),
        )

    @staticmethod
    def _require_risk_label(value: Any, label: str) -> str:
        parsed = CriticAgent._require_text(value, label)
        if parsed not in {"contained", "watch", "serious"}:
            raise CriticOutputError(
                f"{label} must use one of: contained, serious, watch."
            )
        return parsed
