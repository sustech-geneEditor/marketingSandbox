"""Decision agent contracts for the marketing sandbox.

The DecisionAgent is intentionally backend-agnostic. A caller can attach any
LLM adapter that returns the JSON contract described in the generated prompt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any, Callable, Mapping, Protocol, Sequence

from .action_space import ActionSpace, ActionSpaceValidationError
from .search_models import SearchBrief


RawDecisionResponse = str | Mapping[str, Any]
ActionSpaceSpec = ActionSpace

FORBIDDEN_RESULT_TERMS = re.compile(
    r"(?i)("
    r"purchase probability|conversion rate|repurchase rate|market share|"
    r"risk probability|sales forecast|profit forecast|"
    r"购买概率|转化率|复购率|市场份额|风险概率|销量预测|利润预测"
    r")"
)


class DecisionAgentError(Exception):
    """Base error for DecisionAgent failures."""


class DecisionInputError(DecisionAgentError):
    """Raised when the DecisionAgent cannot start from the supplied context."""


class DecisionOutputError(DecisionAgentError):
    """Raised when a backend output violates the DecisionAgent contract."""


class DecisionBackend(Protocol):
    """Minimal interface expected from a DecisionAgent model adapter."""

    def generate(self, prompt: str) -> RawDecisionResponse:
        """Return a JSON string or an already parsed mapping."""


@dataclass(frozen=True)
class StrategyAction:
    """One decision inside a candidate marketing strategy."""

    category: str
    summary: str
    reason: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    product_claims: tuple[str, ...] = ()


@dataclass(frozen=True)
class Strategy:
    """A candidate marketing strategy built from allowed actions."""

    name: str
    hypothesis: str
    actions: tuple[StrategyAction, ...]
    target_consumers: tuple[str, ...]
    expected_tradeoffs: tuple[str, ...]
    family_id: str = ""
    family_fit_note: str = ""


@dataclass(frozen=True)
class StrategyProposal:
    """DecisionAgent output for one sandbox decision step."""

    decision_note: str
    candidates: tuple[Strategy, ...]
    next_validation_question: str


@dataclass(frozen=True)
class DecisionContext:
    """Facts the DecisionAgent may use while proposing strategies."""

    product_facts: tuple[str, ...]
    marketing_objectives: tuple[str, ...]
    brand_boundaries: tuple[str, ...] = ()
    market_facts: tuple[str, ...] = ()
    competitor_facts: tuple[str, ...] = ()
    target_personas: tuple[str, ...] = ()
    scenarios: tuple[str, ...] = ()
    tested_strategies: tuple[str, ...] = ()


@dataclass(frozen=True)
class RoundEvidence:
    """Qualitative evidence fed back to the DecisionAgent between rounds."""

    consumer_feedback_summary: str
    feedback_synthesis: str = ""
    critique: str = ""


class DecisionAgent:
    """Marketing strategy proposer constrained by an action space."""

    def __init__(
        self,
        backend: DecisionBackend | Callable[[str], RawDecisionResponse],
        action_space: ActionSpaceSpec,
        *,
        max_candidates: int = 3,
        max_contract_repair_attempts: int = 1,
    ) -> None:
        if max_candidates < 1:
            raise DecisionInputError("DecisionAgent must allow at least one candidate.")
        if (
            isinstance(max_contract_repair_attempts, bool)
            or not isinstance(max_contract_repair_attempts, int)
            or max_contract_repair_attempts < 0
        ):
            raise DecisionInputError(
                "DecisionAgent contract repair attempts must be a non-negative integer."
            )
        self._backend = backend
        self.action_space = action_space
        self.max_candidates = max_candidates
        self.max_contract_repair_attempts = max_contract_repair_attempts
        self.last_prompt: str | None = None

    def propose_initial_strategies(
        self,
        context: DecisionContext,
        *,
        search_brief: SearchBrief | None = None,
    ) -> StrategyProposal:
        """Propose first-round candidate strategies."""

        return self._propose(
            context=context,
            evidence=None,
            mode="initial",
            search_brief=search_brief,
        )

    def revise_strategies(
        self,
        context: DecisionContext,
        evidence: RoundEvidence,
        *,
        search_brief: SearchBrief | None = None,
    ) -> StrategyProposal:
        """Propose follow-up strategies after qualitative round evidence."""

        if not evidence.consumer_feedback_summary.strip():
            raise DecisionInputError(
                "Round evidence needs a consumer feedback summary for revision."
            )
        return self._propose(
            context=context,
            evidence=evidence,
            mode="revision",
            search_brief=search_brief,
        )

    def build_prompt(
        self,
        context: DecisionContext,
        evidence: RoundEvidence | None = None,
        *,
        mode: str = "initial",
        search_brief: SearchBrief | None = None,
    ) -> str:
        """Build the DecisionAgent prompt without calling a backend."""

        self._validate_context(context)
        self._validate_search_brief(search_brief)
        evidence_block = self._format_evidence(evidence)
        family_block, family_contract = self._format_search_brief(search_brief)
        return f"""You are the DecisionAgent in an AI marketing sandbox.

Mode: {mode}

Your job:
- Propose candidate marketing strategies inside the ActionSpace.
- You may use numeric marketing actions such as prices, discounts, coupons, and
  budget allocations when those actions stay inside the supplied boundaries.
- Tie every numeric action to a strategy reason.
- In action.parameters, use only parameter names that appear in ActionSpace
  numeric limits or semantic options. Do not invent numeric keys.
- Each candidate's actions must include one concrete action from every allowed
  ActionSpace category.
- For this run the allowed categories are: {", ".join(sorted(self.action_space.allowed_categories))}.
- If a category feels less important, still choose a conservative, concrete,
  boundary-safe action for that category. Never leave a category blank.
- Do not use pause, skip, no-op, do-nothing, or hold-this-category actions.
- Do not change personas, scenarios, product facts, market facts, or brand boundaries.
- Do not invent product claims, certifications, product metrics, or capabilities.
- Do not output sales forecasts, conversion rates, repurchase rates, purchase
  probabilities, market-share predictions, or strategy scores.

ActionSpace:
{self.action_space.describe()}

Action coverage contract:
- Allowed action.category values for this run: {", ".join(sorted(self.action_space.allowed_categories))}.
- For every candidate, collect its action.category values. That set must include
  every allowed category above.
- Example: if allowed categories are product, price, and promotion, every single
  candidate needs at least one product action, one price action, and one promotion
  action.
- Never satisfy a required category with pause, skip, no-op, no action, do
  nothing, hold, leave unchanged, or an empty placeholder.
- If a category is secondary, choose a conservative in-bound concrete action for
  that category instead of omitting it.
- action.parameters must not contain numeric keys that are absent from the
  ActionSpace numeric limits. Put unbounded details in summary/reason as
  qualitative wording instead.

Product facts:
{self._format_lines(context.product_facts)}

Marketing objectives:
{self._format_lines(context.marketing_objectives)}

Brand boundaries:
{self._format_lines(context.brand_boundaries)}

Market facts:
{self._format_lines(context.market_facts)}

Competitor facts:
{self._format_lines(context.competitor_facts)}

Target personas:
{self._format_lines(context.target_personas)}

Scenarios:
{self._format_lines(context.scenarios)}

Previously tested strategies:
{self._format_lines(context.tested_strategies)}

Family search brief:
{family_block}

Qualitative round evidence:
{evidence_block}

Return JSON only with exactly this shape:
{{
  "decision_note": "qualitative decision note",
  "candidates": [
    {{
      {family_contract}
      "name": "strategy name",
      "hypothesis": "what this strategy is trying to change",
      "target_consumers": ["qualitative target segment"],
      "expected_tradeoffs": ["qualitative tradeoff"],
      "actions": [
        {{
          "category": "positioning|product|price|channel|promotion|retention",
          "summary": "action summary",
          "reason": "why this action belongs in the strategy",
          "parameters": {{"optional_numeric_or_named_action_parameter": "value"}},
          "product_claims": ["only approved claims used by product actions"]
        }}
      ]
    }}
  ],
  "next_validation_question": "the next question the sandbox should test"
}}

Return between one and {self.max_candidates} candidate strategies. Each candidate
must cover every allowed ActionSpace category with at least one non-paused,
concrete action.
"""

    def _propose(
        self,
        *,
        context: DecisionContext,
        evidence: RoundEvidence | None,
        mode: str,
        search_brief: SearchBrief | None,
    ) -> StrategyProposal:
        prompt = self.build_prompt(
            context,
            evidence,
            mode=mode,
            search_brief=search_brief,
        )
        next_prompt = prompt
        first_error: DecisionOutputError | None = None
        for attempt_index in range(self.max_contract_repair_attempts + 1):
            self.last_prompt = next_prompt
            response = self._call_backend(next_prompt)
            try:
                return self._proposal_from_response(response, search_brief)
            except DecisionOutputError as error:
                if first_error is None:
                    first_error = error
                if attempt_index >= self.max_contract_repair_attempts:
                    if self.max_contract_repair_attempts == 0:
                        raise
                    attempt_word = (
                        "attempt"
                        if self.max_contract_repair_attempts == 1
                        else "attempts"
                    )
                    raise DecisionOutputError(
                        "Decision backend output stayed invalid after "
                        f"{self.max_contract_repair_attempts} repair {attempt_word}. "
                        f"First error: {first_error}. Last error: {error}."
                    ) from error
                next_prompt = self._build_repair_prompt(
                    original_prompt=prompt,
                    invalid_response=response,
                    error_message=str(error),
                )

        if first_error is not None:
            raise first_error
        raise DecisionOutputError("Decision backend did not return a proposal.")

    def _proposal_from_response(
        self,
        response: RawDecisionResponse,
        search_brief: SearchBrief | None,
    ) -> StrategyProposal:
        payload = self._load_payload(response)
        proposal = self._parse_proposal(payload)
        self._validate_proposal(proposal, search_brief)
        return proposal

    def _build_repair_prompt(
        self,
        *,
        original_prompt: str,
        invalid_response: RawDecisionResponse,
        error_message: str,
    ) -> str:
        return f"""{original_prompt}

The previous DecisionAgent response was rejected by the sandbox contract.

Contract error:
- {error_message}

Repair rules:
- Return JSON only, using exactly the same response shape requested above.
- Preserve the same strategic intent only when it can satisfy the contract.
- Every candidate must include at least one concrete action for every allowed
  ActionSpace category: {", ".join(sorted(self.action_space.allowed_categories))}.
- Do not use pause, skip, no-op, do-nothing, hold, or leave-unchanged language.
- Keep every action inside ActionSpace limits and approved product claims.
- Use only parameter keys listed by ActionSpace. If the rejected output used an
  unlisted numeric key, replace it with a listed key or remove it from
  parameters and describe it qualitatively in summary/reason.
- If a category needs a low-risk move, make it a conservative concrete action,
  not a stopped or empty action.

Rejected response excerpt:
{self._response_excerpt(invalid_response)}
"""

    def _call_backend(self, prompt: str) -> RawDecisionResponse:
        backend_generate = getattr(self._backend, "generate", None)
        if callable(backend_generate):
            return backend_generate(prompt)
        if callable(self._backend):
            return self._backend(prompt)
        raise DecisionInputError("DecisionAgent backend must be callable.")

    @staticmethod
    def _response_excerpt(response: RawDecisionResponse) -> str:
        if isinstance(response, str):
            text = response
        else:
            try:
                text = json.dumps(response, ensure_ascii=False, sort_keys=True)
            except TypeError:
                text = repr(response)
        text = text.strip()
        return text[:4000] if text else "(empty response)"

    def _load_payload(self, response: RawDecisionResponse) -> Mapping[str, Any]:
        if isinstance(response, str):
            try:
                payload = json.loads(response)
            except json.JSONDecodeError as exc:
                raise DecisionOutputError("Decision backend returned invalid JSON.") from exc
        else:
            payload = response

        if not isinstance(payload, Mapping):
            raise DecisionOutputError("Decision backend output must be a JSON object.")
        return payload

    def _parse_proposal(self, payload: Mapping[str, Any]) -> StrategyProposal:
        self._check_keys(
            payload,
            required={"decision_note", "candidates", "next_validation_question"},
            allowed={"decision_note", "candidates", "next_validation_question"},
            label="proposal",
        )
        candidates_raw = self._require_sequence(payload["candidates"], "candidates")
        candidates = tuple(self._parse_strategy(item) for item in candidates_raw)
        return StrategyProposal(
            decision_note=self._require_text(payload["decision_note"], "decision_note"),
            candidates=candidates,
            next_validation_question=self._require_text(
                payload["next_validation_question"], "next_validation_question"
            ),
        )

    def _parse_strategy(self, item: Any) -> Strategy:
        if not isinstance(item, Mapping):
            raise DecisionOutputError("Each candidate must be a JSON object.")
        self._check_keys(
            item,
            required={
                "name",
                "hypothesis",
                "actions",
                "target_consumers",
                "expected_tradeoffs",
            },
            allowed={
                "family_id",
                "family_fit_note",
                "name",
                "hypothesis",
                "actions",
                "target_consumers",
                "expected_tradeoffs",
            },
            label="candidate",
        )
        actions_raw = self._require_sequence(item["actions"], "actions")
        if not actions_raw:
            raise DecisionOutputError("Each candidate needs at least one action.")
        return Strategy(
            name=self._require_text(item["name"], "candidate.name"),
            hypothesis=self._require_text(
                item["hypothesis"], "candidate.hypothesis"
            ),
            actions=tuple(self._parse_action(action) for action in actions_raw),
            target_consumers=self._parse_text_sequence(
                item["target_consumers"], "candidate.target_consumers"
            ),
            expected_tradeoffs=self._parse_text_sequence(
                item["expected_tradeoffs"], "candidate.expected_tradeoffs"
            ),
            family_id=self._parse_optional_text(
                item.get("family_id", ""), "candidate.family_id"
            ),
            family_fit_note=self._parse_optional_text(
                item.get("family_fit_note", ""), "candidate.family_fit_note"
            ),
        )

    def _parse_action(self, item: Any) -> StrategyAction:
        if not isinstance(item, Mapping):
            raise DecisionOutputError("Each action must be a JSON object.")
        self._check_keys(
            item,
            required={"category", "summary", "reason"},
            allowed={"category", "summary", "reason", "parameters", "product_claims"},
            label="action",
        )
        parameters = item.get("parameters", {})
        if not isinstance(parameters, Mapping):
            raise DecisionOutputError("Action parameters must be a JSON object.")
        claims_raw = item.get("product_claims", ())
        return StrategyAction(
            category=self._require_text(item["category"], "action.category"),
            summary=self._require_text(item["summary"], "action.summary"),
            reason=self._require_text(item["reason"], "action.reason"),
            parameters=dict(parameters),
            product_claims=self._parse_text_sequence(
                claims_raw, "action.product_claims", allow_empty=True
            ),
        )

    def _validate_proposal(
        self, proposal: StrategyProposal, search_brief: SearchBrief | None
    ) -> None:
        if not proposal.candidates:
            raise DecisionOutputError("DecisionAgent needs at least one candidate.")
        if len(proposal.candidates) > self.max_candidates:
            raise DecisionOutputError(
                "DecisionAgent backend returned more candidates than allowed."
            )

        self._reject_result_prediction(proposal.decision_note)
        self._reject_result_prediction(proposal.next_validation_question)
        for strategy in proposal.candidates:
            self._reject_result_prediction(strategy.name)
            self._reject_result_prediction(strategy.hypothesis)
            if strategy.family_id:
                self._reject_result_prediction(strategy.family_id)
            if strategy.family_fit_note:
                self._reject_result_prediction(strategy.family_fit_note)
            for item in strategy.target_consumers + strategy.expected_tradeoffs:
                self._reject_result_prediction(item)
            for action in strategy.actions:
                self._reject_result_prediction(action.summary)
                self._reject_result_prediction(action.reason)
                self._reject_predictions_in_parameters(action.parameters)
            try:
                self.action_space.validate_strategy_actions(strategy.actions)
            except ActionSpaceValidationError as error:
                raise DecisionOutputError(str(error)) from error
        if search_brief is not None:
            self._validate_family_coverage(proposal, search_brief)

    def _validate_context(self, context: DecisionContext) -> None:
        if not context.product_facts:
            raise DecisionInputError("DecisionContext needs product facts.")
        if not context.marketing_objectives:
            raise DecisionInputError("DecisionContext needs marketing objectives.")
        if not self.action_space.allowed_categories:
            raise DecisionInputError("DecisionAgent needs a non-empty ActionSpace.")

    def _validate_search_brief(self, search_brief: SearchBrief | None) -> None:
        if search_brief is None:
            return
        if not isinstance(search_brief, SearchBrief):
            raise DecisionInputError("DecisionAgent search_brief must be SearchBrief.")
        if search_brief.expected_strategy_count > self.max_candidates:
            raise DecisionInputError(
                "DecisionAgent max_candidates cannot cover the SearchBrief."
            )

    @staticmethod
    def _format_lines(lines: Sequence[str]) -> str:
        cleaned = [line.strip() for line in lines if line.strip()]
        return "\n".join(f"- {line}" for line in cleaned) or "- none supplied"

    @classmethod
    def _format_evidence(cls, evidence: RoundEvidence | None) -> str:
        if evidence is None:
            return "- no prior round evidence"
        blocks = [
            ("consumer feedback summary", evidence.consumer_feedback_summary),
            ("feedback synthesis", evidence.feedback_synthesis),
            ("critic report", evidence.critique),
        ]
        return "\n".join(
            f"- {label}: {text.strip()}"
            for label, text in blocks
            if text.strip()
        ) or "- no prior round evidence"

    @staticmethod
    def _format_search_brief(search_brief: SearchBrief | None) -> tuple[str, str]:
        if search_brief is None:
            return (
                "- no family search constraint; propose qualitative strategy directions",
                "",
            )
        family_contract = (
            '"family_id": "selected strategy family id",\n'
            '      "family_fit_note": "why this candidate fits that family",'
        )
        return (
            search_brief.describe()
            + "\n- Produce one candidate for each selected family."
            + "\n- Family guidance is not a replacement for ActionSpace boundaries."
            + "\n- Do not output UCB scores, search rewards, or strategy scores.",
            family_contract,
        )

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
            raise DecisionOutputError(f"{label} is missing keys: {rendered}.")
        extra = keys - allowed
        if extra:
            rendered = ", ".join(sorted(extra))
            raise DecisionOutputError(f"{label} has unsupported keys: {rendered}.")

    @staticmethod
    def _require_text(value: Any, label: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise DecisionOutputError(f"{label} must be non-empty text.")
        return value.strip()

    @staticmethod
    def _parse_optional_text(value: Any, label: str) -> str:
        if value == "":
            return ""
        return DecisionAgent._require_text(value, label)

    @staticmethod
    def _require_sequence(value: Any, label: str) -> Sequence[Any]:
        if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
            raise DecisionOutputError(f"{label} must be a list.")
        return value

    def _parse_text_sequence(
        self, value: Any, label: str, *, allow_empty: bool = False
    ) -> tuple[str, ...]:
        sequence = self._require_sequence(value, label)
        parsed = tuple(self._require_text(item, label) for item in sequence)
        if not parsed and not allow_empty:
            raise DecisionOutputError(f"{label} must contain at least one item.")
        return parsed

    @staticmethod
    def _reject_result_prediction(text: str) -> None:
        if FORBIDDEN_RESULT_TERMS.search(text):
            raise DecisionOutputError(
                "DecisionAgent output includes a forbidden market-result prediction."
            )

    @classmethod
    def _reject_predictions_in_parameters(cls, value: Any) -> None:
        if isinstance(value, Mapping):
            for key, nested in value.items():
                cls._reject_result_prediction(str(key).replace("_", " "))
                cls._reject_predictions_in_parameters(nested)
            return
        if isinstance(value, str):
            cls._reject_result_prediction(value)
            return
        if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
            for nested in value:
                cls._reject_predictions_in_parameters(nested)

    @staticmethod
    def _validate_family_coverage(
        proposal: StrategyProposal, search_brief: SearchBrief
    ) -> None:
        family_ids = [strategy.family_id for strategy in proposal.candidates]
        if any(not family_id for family_id in family_ids):
            raise DecisionOutputError(
                "Family-constrained DecisionAgent output needs family_id."
            )
        if any(not strategy.family_fit_note for strategy in proposal.candidates):
            raise DecisionOutputError(
                "Family-constrained DecisionAgent output needs family_fit_note."
            )
        expected = tuple(search_brief.selected_family_ids)
        if len(family_ids) != len(set(family_ids)):
            raise DecisionOutputError(
                "Family-constrained DecisionAgent output repeats a selected family."
            )
        if set(family_ids) != set(expected) or len(family_ids) != len(expected):
            raise DecisionOutputError(
                "Family-constrained DecisionAgent output must cover selected families."
            )
