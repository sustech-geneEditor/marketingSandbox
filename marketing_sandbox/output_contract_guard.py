"""Role-aware output contract checks for sandbox LLM results."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass
from typing import Any, Pattern

from .action_space import ActionSpace, ActionSpaceValidationError
from .consumer_agent import (
    FORBIDDEN_CONSUMER_KEYS,
    FORBIDDEN_CONSUMER_TERMS,
    ConsumerFeedback,
)
from .critic_agent import (
    CONSUMER_VOICE_KEYS,
    FORBIDDEN_CRITIC_KEYS,
    FORBIDDEN_CRITIC_TERMS,
    CritiqueReport,
)
from .decision_agent import FORBIDDEN_RESULT_TERMS, StrategyProposal
from .feedback_synthesizer import (
    FORBIDDEN_SUMMARY_KEYS,
    FORBIDDEN_SUMMARY_TERMS,
    FeedbackSummary,
)


ROLE_DECISION = "DecisionAgent"
ROLE_CONSUMER = "ConsumerAgent"
ROLE_SUMMARY = "FeedbackSynthesizer"
ROLE_CRITIC = "CriticAgent"


class OutputContractGuardError(Exception):
    """Base error for OutputContractGuard failures."""


class OutputContractInputError(OutputContractGuardError):
    """Raised when a guard call lacks the data needed to check a contract."""


class OutputContractViolation(OutputContractGuardError):
    """Raised when a caller wants a rejected contract result to fail fast."""

    def __init__(self, result: "ContractCheckResult") -> None:
        self.result = result
        first_message = result.issues[0].message if result.issues else "unknown issue"
        super().__init__(f"{result.role} output contract rejected: {first_message}")


@dataclass(frozen=True)
class ContractIssue:
    """One reason a sandbox role output should not enter round history."""

    code: str
    path: str
    message: str
    rewrite_hint: str


@dataclass(frozen=True)
class ContractCheckResult:
    """Accept-or-rewrite result returned by OutputContractGuard."""

    role: str
    issues: tuple[ContractIssue, ...] = ()

    @property
    def accepted(self) -> bool:
        """Return True when the output obeys the role contract."""

        return not self.issues

    @property
    def rewrite_required(self) -> bool:
        """Return True when the producing role should rewrite its output."""

        return bool(self.issues)

    @property
    def rewrite_instruction(self) -> str:
        """Render a concise instruction that can be sent back to an LLM role."""

        if not self.issues:
            return ""
        hints: list[str] = []
        for issue in self.issues:
            if issue.rewrite_hint not in hints:
                hints.append(issue.rewrite_hint)
        return f"Rewrite {self.role} output. " + " ".join(hints)

    def require_acceptance(self) -> None:
        """Raise when a caller cannot proceed with an invalid role output."""

        if not self.accepted:
            raise OutputContractViolation(self)


@dataclass(frozen=True)
class _KeyRule:
    code: str
    pattern: Pattern[str]
    message: str
    rewrite_hint: str


@dataclass(frozen=True)
class _TextRule:
    code: str
    pattern: Pattern[str]
    message: str
    rewrite_hint: str


class OutputContractGuard:
    """Check each sandbox LLM result against its own output contract."""

    _ROLE_ALIASES = {
        "decision": ROLE_DECISION,
        "decisionagent": ROLE_DECISION,
        "decision_agent": ROLE_DECISION,
        "consumer": ROLE_CONSUMER,
        "consumeragent": ROLE_CONSUMER,
        "consumer_agent": ROLE_CONSUMER,
        "feedback": ROLE_SUMMARY,
        "summary": ROLE_SUMMARY,
        "feedbacksynthesizer": ROLE_SUMMARY,
        "feedback_synthesizer": ROLE_SUMMARY,
        "critic": ROLE_CRITIC,
        "criticagent": ROLE_CRITIC,
        "critic_agent": ROLE_CRITIC,
    }
    _EXPECTED_TYPES = {
        ROLE_DECISION: StrategyProposal,
        ROLE_CONSUMER: ConsumerFeedback,
        ROLE_SUMMARY: FeedbackSummary,
        ROLE_CRITIC: CritiqueReport,
    }
    _DECISION_TEXT_RULE = _TextRule(
        code="decision_result_prediction",
        pattern=FORBIDDEN_RESULT_TERMS,
        message="DecisionAgent output includes a market-result prediction.",
        rewrite_hint=(
            "Keep DecisionAgent text on actions, tradeoffs, and validation questions "
            "instead of result forecasts."
        ),
    )
    _CONSUMER_TEXT_RULE = _TextRule(
        code="consumer_numeric_judgement",
        pattern=FORBIDDEN_CONSUMER_TERMS,
        message="ConsumerAgent output includes a probability, score, or market judgement.",
        rewrite_hint=(
            "Rewrite consumer reactions as qualitative feelings, friction, and reasons."
        ),
    )
    _SUMMARY_TEXT_RULE = _TextRule(
        code="summary_fake_precision",
        pattern=FORBIDDEN_SUMMARY_TERMS,
        message="FeedbackSynthesizer output includes a score, probability, or forecast.",
        rewrite_hint=(
            "Rewrite the summary as qualitative synthesis without fake precision."
        ),
    )
    _CRITIC_TEXT_RULE = _TextRule(
        code="critic_forecast",
        pattern=FORBIDDEN_CRITIC_TERMS,
        message="CriticAgent output includes a probability, loss, or business forecast.",
        rewrite_hint=(
            "Rewrite the critique as evidence gaps and boundary risks, not forecasts."
        ),
    )
    _CONSUMER_KEY_RULE = _KeyRule(
        code="consumer_forbidden_field",
        pattern=FORBIDDEN_CONSUMER_KEYS,
        message="ConsumerAgent output includes a forbidden numeric judgement field.",
        rewrite_hint=(
            "Remove numeric consumer judgement fields and keep qualitative feedback."
        ),
    )
    _SUMMARY_KEY_RULE = _KeyRule(
        code="summary_forbidden_field",
        pattern=FORBIDDEN_SUMMARY_KEYS,
        message="FeedbackSynthesizer output includes a scoring or forecast field.",
        rewrite_hint=(
            "Remove score, rank, probability, and forecast fields from the summary."
        ),
    )
    _CRITIC_KEY_RULE = _KeyRule(
        code="critic_forbidden_field",
        pattern=FORBIDDEN_CRITIC_KEYS,
        message="CriticAgent output includes a forecast or probability field.",
        rewrite_hint=(
            "Remove risk probability and business forecast fields from the critique."
        ),
    )
    _CRITIC_CONSUMER_VOICE_RULE = _KeyRule(
        code="critic_consumer_voice",
        pattern=CONSUMER_VOICE_KEYS,
        message="CriticAgent output includes a consumer-feedback field.",
        rewrite_hint=(
            "Keep the critic in reviewer voice instead of consumer reaction fields."
        ),
    )

    def check_decision_proposal(
        self, proposal: StrategyProposal, action_space: ActionSpace
    ) -> ContractCheckResult:
        """Check DecisionAgent actions and text with the supplied ActionSpace."""

        return self.check(ROLE_DECISION, proposal, action_space=action_space)

    def check_consumer_feedback(self, feedback: ConsumerFeedback) -> ContractCheckResult:
        """Check one qualitative ConsumerAgent output."""

        return self.check(ROLE_CONSUMER, feedback)

    def check_feedback_summary(self, summary: FeedbackSummary) -> ContractCheckResult:
        """Check one qualitative FeedbackSynthesizer output."""

        return self.check(ROLE_SUMMARY, summary)

    def check_critique_report(self, report: CritiqueReport) -> ContractCheckResult:
        """Check one qualitative CriticAgent output."""

        return self.check(ROLE_CRITIC, report)

    def check(
        self,
        role: str,
        output: Any,
        *,
        action_space: ActionSpace | None = None,
    ) -> ContractCheckResult:
        """Check a typed output or raw payload for one named sandbox role."""

        normalized_role = self._normalize_role(role)
        if normalized_role == ROLE_DECISION:
            if not isinstance(action_space, ActionSpace):
                raise OutputContractInputError(
                    "DecisionAgent contract checks need an ActionSpace."
                )
        issues: list[ContractIssue] = []
        self._check_output_type(normalized_role, output, issues)
        if normalized_role == ROLE_DECISION:
            self._scan_value(
                output,
                path="$",
                text_rule=self._DECISION_TEXT_RULE,
                key_rules=(),
                reject_numeric_scalars=False,
                role=normalized_role,
                issues=issues,
            )
            if isinstance(output, StrategyProposal):
                self._check_decision_actions(output, action_space, issues)
        elif normalized_role == ROLE_CONSUMER:
            self._scan_value(
                output,
                path="$",
                text_rule=self._CONSUMER_TEXT_RULE,
                key_rules=(self._CONSUMER_KEY_RULE,),
                reject_numeric_scalars=True,
                role=normalized_role,
                issues=issues,
            )
        elif normalized_role == ROLE_SUMMARY:
            self._scan_value(
                output,
                path="$",
                text_rule=self._SUMMARY_TEXT_RULE,
                key_rules=(self._SUMMARY_KEY_RULE,),
                reject_numeric_scalars=True,
                role=normalized_role,
                issues=issues,
            )
        else:
            self._scan_value(
                output,
                path="$",
                text_rule=self._CRITIC_TEXT_RULE,
                key_rules=(self._CRITIC_KEY_RULE, self._CRITIC_CONSUMER_VOICE_RULE),
                reject_numeric_scalars=True,
                role=normalized_role,
                issues=issues,
            )
        return ContractCheckResult(role=normalized_role, issues=tuple(issues))

    @classmethod
    def _normalize_role(cls, role: str) -> str:
        if not isinstance(role, str) or not role.strip():
            raise OutputContractInputError("Output role must be non-empty text.")
        normalized = role.strip()
        if normalized in cls._EXPECTED_TYPES:
            return normalized
        alias = normalized.lower().replace("-", "_").replace(" ", "")
        if alias in cls._ROLE_ALIASES:
            return cls._ROLE_ALIASES[alias]
        raise OutputContractInputError(f"Unsupported sandbox output role: {role}.")

    @classmethod
    def _check_output_type(
        cls, role: str, output: Any, issues: list[ContractIssue]
    ) -> None:
        expected_type = cls._EXPECTED_TYPES[role]
        if isinstance(output, expected_type):
            return
        issues.append(
            ContractIssue(
                code="role_output_type",
                path="$",
                message=f"{role} output should be {expected_type.__name__}.",
                rewrite_hint=(
                    f"Return the {expected_type.__name__} contract for {role}."
                ),
            )
        )

    @classmethod
    def _check_decision_actions(
        cls,
        proposal: StrategyProposal,
        action_space: ActionSpace,
        issues: list[ContractIssue],
    ) -> None:
        for candidate_index, strategy in enumerate(proposal.candidates):
            try:
                action_space.validate_strategy_actions(strategy.actions)
            except ActionSpaceValidationError as error:
                issues.append(
                    ContractIssue(
                        code="action_space_violation",
                        path=f"$.candidates[{candidate_index}].actions",
                        message=str(error),
                        rewrite_hint=(
                            "Keep DecisionAgent actions inside ActionSpace limits, "
                            "cover every allowed category with a concrete action, "
                            "and turn missing bounds into validation questions."
                        ),
                    )
                )

    @classmethod
    def _scan_value(
        cls,
        value: Any,
        *,
        path: str,
        text_rule: _TextRule,
        key_rules: tuple[_KeyRule, ...],
        reject_numeric_scalars: bool,
        role: str,
        issues: list[ContractIssue],
    ) -> None:
        if is_dataclass(value) and not isinstance(value, type):
            for data_field in fields(value):
                cls._scan_value(
                    getattr(value, data_field.name),
                    path=f"{path}.{data_field.name}",
                    text_rule=text_rule,
                    key_rules=key_rules,
                    reject_numeric_scalars=reject_numeric_scalars,
                    role=role,
                    issues=issues,
                )
            return
        if isinstance(value, Mapping):
            for key, nested in value.items():
                key_text = str(key)
                key_path = f"{path}.{key_text}"
                normalized_key = key_text.replace("_", " ")
                for key_rule in key_rules:
                    if key_rule.pattern.search(normalized_key):
                        issues.append(
                            ContractIssue(
                                code=key_rule.code,
                                path=key_path,
                                message=key_rule.message,
                                rewrite_hint=key_rule.rewrite_hint,
                            )
                        )
                cls._scan_value(
                    nested,
                    path=key_path,
                    text_rule=text_rule,
                    key_rules=key_rules,
                    reject_numeric_scalars=reject_numeric_scalars,
                    role=role,
                    issues=issues,
                )
            return
        if isinstance(value, str):
            if text_rule.pattern.search(value):
                issues.append(
                    ContractIssue(
                        code=text_rule.code,
                        path=path,
                        message=text_rule.message,
                        rewrite_hint=text_rule.rewrite_hint,
                    )
                )
            return
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            for index, nested in enumerate(value):
                cls._scan_value(
                    nested,
                    path=f"{path}[{index}]",
                    text_rule=text_rule,
                    key_rules=key_rules,
                    reject_numeric_scalars=reject_numeric_scalars,
                    role=role,
                    issues=issues,
                )
            return
        if (
            reject_numeric_scalars
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
        ):
            issues.append(
                ContractIssue(
                    code="bare_numeric_value",
                    path=path,
                    message=f"{role} output contains a bare numeric value.",
                    rewrite_hint=(
                        f"Keep {role} judgements qualitative; factual numbers may be "
                        "quoted in text when context supplied them."
                    ),
                )
            )
