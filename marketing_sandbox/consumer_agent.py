"""Consumer agent contracts for the marketing sandbox."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Callable, Mapping, Protocol, Sequence

from .decision_agent import Strategy


RawConsumerResponse = str | Mapping[str, Any]

FORBIDDEN_CONSUMER_TERMS = re.compile(
    r"(?i)("
    r"purchase probability|repurchase probability|repeat purchase probability|"
    r"market share|market percentage|strategy score|dimension score|"
    r"acceptance rate|conversion rate|acceptable price|willingness to pay|"
    r"购买概率|复购概率|市场份额|市场占比|策略分数|维度分|转化率|"
    r"可接受价格|愿付价格"
    r")"
)

FORBIDDEN_CONSUMER_KEYS = re.compile(
    r"(?i)("
    r"score|probability|purchase[_ ]rate|repurchase[_ ]rate|conversion[_ ]rate|"
    r"market[_ ]share|market[_ ]percentage|acceptable[_ ]price|"
    r"分数|概率|购买率|复购率|转化率|市场份额|市场占比|可接受价格"
    r")"
)


class ConsumerAgentError(Exception):
    """Base error for ConsumerAgent failures."""


class ConsumerInputError(ConsumerAgentError):
    """Raised when a consumer reaction lacks required context."""


class ConsumerOutputError(ConsumerAgentError):
    """Raised when a consumer backend violates its qualitative contract."""


class ConsumerBackend(Protocol):
    """Minimal interface expected from a ConsumerAgent model adapter."""

    def generate(self, prompt: str) -> RawConsumerResponse:
        """Return a JSON string or an already parsed mapping."""


@dataclass(frozen=True)
class Persona:
    """Stable segment archetype assigned to one ConsumerAgent."""

    name: str
    core_need: str
    purchase_motivation: str
    current_alternative: str
    price_sensitivity: str
    trust_sensitivity: str
    promotion_sensitivity: str
    channel_preference: str
    social_influence: str
    main_barrier: str
    repeat_trigger: str
    switching_threshold: str


@dataclass(frozen=True)
class Scenario:
    """Market situation used when a ConsumerAgent reacts to a strategy."""

    name: str
    situation: str
    competitor_pressure: str = ""
    trust_pressure: str = ""
    friction_pressure: str = ""


@dataclass(frozen=True)
class ProductContext:
    """Product facts the consumer may use while reacting."""

    facts: tuple[str, ...]
    brand_facts: tuple[str, ...] = ()
    competitor_facts: tuple[str, ...] = ()


@dataclass(frozen=True)
class BehaviorDiagnosis:
    """Behavioral mechanism hints visible in a qualitative consumer reaction."""

    first_signal: str
    reference_point: str
    perceived_risk: str
    action_friction: str
    dominant_driver: str


@dataclass(frozen=True)
class RepeatPurchaseReaction:
    """Qualitative repeat-purchase reaction."""

    feeling: str
    condition: str
    habit_or_inertia: str


@dataclass(frozen=True)
class CompetitorReaction:
    """Qualitative reaction under competitor pressure."""

    likely_shift: str
    reason: str
    retention_condition: str


@dataclass(frozen=True)
class AdvocacyReaction:
    """Qualitative sharing and recommendation reaction."""

    recommendation_feeling: str
    sharing_feeling: str
    friend_description: str


@dataclass(frozen=True)
class ConsumerFeedback:
    """Structured qualitative feedback from one ConsumerAgent."""

    persona_name: str
    scenario_name: str
    first_impression: str
    understood_offer: str
    perceived_positioning: str
    strongest_pull: str
    strongest_rejection: str
    current_attitude: str
    behavior_diagnosis: BehaviorDiagnosis
    repeat_purchase: RepeatPurchaseReaction
    competitor_reaction: CompetitorReaction
    advocacy: AdvocacyReaction
    behavior_notes: tuple[str, ...]


class ConsumerAgent:
    """Persona-bound qualitative consumer reactor."""

    def __init__(
        self,
        backend: ConsumerBackend | Callable[[str], RawConsumerResponse],
        persona: Persona,
    ) -> None:
        self._backend = backend
        self.persona = persona
        self.last_prompt: str | None = None
        self._validate_persona(persona)

    def react_to_strategy(
        self,
        strategy: Strategy,
        scenario: Scenario,
        product_context: ProductContext,
    ) -> ConsumerFeedback:
        """Return qualitative consumer feedback for one strategy and scenario."""

        prompt = self.build_prompt(strategy, scenario, product_context)
        self.last_prompt = prompt
        response = self._call_backend(prompt)
        payload = self._load_payload(response)
        feedback = self._parse_feedback(payload, scenario)
        self._validate_feedback(feedback)
        return feedback

    def build_prompt(
        self,
        strategy: Strategy,
        scenario: Scenario,
        product_context: ProductContext,
    ) -> str:
        """Build the qualitative consumer prompt without calling a backend."""

        self._validate_strategy(strategy)
        self._validate_scenario(scenario)
        self._validate_product_context(product_context)
        return f"""You are a ConsumerAgent in an AI marketing sandbox.

You are not a market survey or a scoring judge. React as the assigned persona
inside the supplied scenario.

Do:
- Give qualitative first-impression, purchase hesitation, repeat-purchase,
  competitor-pressure, and advocacy feedback.
- Ground the reaction in the assigned persona, product facts, strategy, and scenario.
- Mention behavioral mechanisms that genuinely matter in this case.

Do not:
- Output purchase probability, repurchase probability, conversion rate, market
  share, market percentage, strategy score, dimension score, or market forecast.
- Invent product facts, competitor facts, or changed persona traits.
- Turn the response into advice from the brand manager point of view.

Assigned persona:
{self._render_persona(self.persona)}

Product and brand facts:
{self._format_lines(product_context.facts)}

Brand facts:
{self._format_lines(product_context.brand_facts)}

Competitor facts:
{self._format_lines(product_context.competitor_facts)}

Scenario:
{self._render_scenario(scenario)}

Strategy under test:
{self._render_strategy(strategy)}

Behavioral priors:
1. Attention is limited; react to the most visible and relevant cues first.
2. Under uncertainty, heuristics such as familiarity, social proof, perceived
   professionalism, price cues, and current alternatives may matter.
3. Compare value against reference points: expectations, current habits,
   competitor alternatives, and the assigned persona's budget feeling.
4. Perceived loss, risk, regret, hassle, and trust uncertainty can outweigh a
   similar-sized promised benefit.
5. Immediate friction matters: money now, waiting, registration, learning, and
   switching effort can reduce action.
6. Social influence sensitivity depends on the assigned persona.
7. Satisfaction alone does not guarantee repeat purchase; habit, reminders,
   convenience, and repeat triggers matter.
8. For prices, offers, memberships, and bundles, consider the persona's mental
   accounting without reporting an invented acceptable-price number.

Return JSON only with exactly this shape:
{{
  "first_impression": "first reaction",
  "understood_offer": "what this persona thinks is being offered",
  "perceived_positioning": "what brand or product role is perceived",
  "strongest_pull": "main attraction",
  "strongest_rejection": "main hesitation or rejection",
  "current_attitude": "qualitative attitude such as willing to try, hesitating, or uninterested",
  "behavior_diagnosis": {{
    "first_signal": "first cue noticed",
    "reference_point": "main comparison point",
    "perceived_risk": "largest risk or regret",
    "action_friction": "largest immediate friction",
    "dominant_driver": "most important behavioral driver this time"
  }},
  "repeat_purchase": {{
    "feeling": "repeat-purchase feeling",
    "condition": "what would make repeat purchase feel natural",
    "habit_or_inertia": "how habits or inertia matter"
  }},
  "competitor_reaction": {{
    "likely_shift": "qualitative reaction under competitor pressure",
    "reason": "why competitor pressure matters or does not",
    "retention_condition": "what would keep this persona with the strategy"
  }},
  "advocacy": {{
    "recommendation_feeling": "recommendation feeling",
    "sharing_feeling": "sharing feeling",
    "friend_description": "how this persona would describe it to a friend"
  }},
  "behavior_notes": ["which behavioral prior mattered", "which did not clearly matter"]
}}
"""

    def _call_backend(self, prompt: str) -> RawConsumerResponse:
        backend_generate = getattr(self._backend, "generate", None)
        if callable(backend_generate):
            return backend_generate(prompt)
        if callable(self._backend):
            return self._backend(prompt)
        raise ConsumerInputError("ConsumerAgent backend must be callable.")

    def _load_payload(self, response: RawConsumerResponse) -> Mapping[str, Any]:
        if isinstance(response, str):
            try:
                payload = json.loads(response)
            except json.JSONDecodeError as exc:
                raise ConsumerOutputError("Consumer backend returned invalid JSON.") from exc
        else:
            payload = response
        if not isinstance(payload, Mapping):
            raise ConsumerOutputError("Consumer backend output must be a JSON object.")
        self._reject_forbidden_payload(payload)
        return payload

    def _parse_feedback(
        self, payload: Mapping[str, Any], scenario: Scenario
    ) -> ConsumerFeedback:
        self._check_keys(
            payload,
            required={
                "first_impression",
                "understood_offer",
                "perceived_positioning",
                "strongest_pull",
                "strongest_rejection",
                "current_attitude",
                "behavior_diagnosis",
                "repeat_purchase",
                "competitor_reaction",
                "advocacy",
                "behavior_notes",
            },
            allowed={
                "first_impression",
                "understood_offer",
                "perceived_positioning",
                "strongest_pull",
                "strongest_rejection",
                "current_attitude",
                "behavior_diagnosis",
                "repeat_purchase",
                "competitor_reaction",
                "advocacy",
                "behavior_notes",
            },
            label="consumer feedback",
        )
        return ConsumerFeedback(
            persona_name=self.persona.name,
            scenario_name=scenario.name,
            first_impression=self._require_text(
                payload["first_impression"], "first_impression"
            ),
            understood_offer=self._require_text(
                payload["understood_offer"], "understood_offer"
            ),
            perceived_positioning=self._require_text(
                payload["perceived_positioning"], "perceived_positioning"
            ),
            strongest_pull=self._require_text(
                payload["strongest_pull"], "strongest_pull"
            ),
            strongest_rejection=self._require_text(
                payload["strongest_rejection"], "strongest_rejection"
            ),
            current_attitude=self._require_text(
                payload["current_attitude"], "current_attitude"
            ),
            behavior_diagnosis=self._parse_behavior_diagnosis(
                payload["behavior_diagnosis"]
            ),
            repeat_purchase=self._parse_repeat_purchase(payload["repeat_purchase"]),
            competitor_reaction=self._parse_competitor_reaction(
                payload["competitor_reaction"]
            ),
            advocacy=self._parse_advocacy(payload["advocacy"]),
            behavior_notes=self._parse_text_sequence(
                payload["behavior_notes"], "behavior_notes"
            ),
        )

    def _parse_behavior_diagnosis(self, item: Any) -> BehaviorDiagnosis:
        mapping = self._require_mapping(item, "behavior_diagnosis")
        self._check_keys(
            mapping,
            required={
                "first_signal",
                "reference_point",
                "perceived_risk",
                "action_friction",
                "dominant_driver",
            },
            allowed={
                "first_signal",
                "reference_point",
                "perceived_risk",
                "action_friction",
                "dominant_driver",
            },
            label="behavior_diagnosis",
        )
        return BehaviorDiagnosis(
            first_signal=self._require_text(mapping["first_signal"], "first_signal"),
            reference_point=self._require_text(
                mapping["reference_point"], "reference_point"
            ),
            perceived_risk=self._require_text(
                mapping["perceived_risk"], "perceived_risk"
            ),
            action_friction=self._require_text(
                mapping["action_friction"], "action_friction"
            ),
            dominant_driver=self._require_text(
                mapping["dominant_driver"], "dominant_driver"
            ),
        )

    def _parse_repeat_purchase(self, item: Any) -> RepeatPurchaseReaction:
        mapping = self._require_mapping(item, "repeat_purchase")
        self._check_keys(
            mapping,
            required={"feeling", "condition", "habit_or_inertia"},
            allowed={"feeling", "condition", "habit_or_inertia"},
            label="repeat_purchase",
        )
        return RepeatPurchaseReaction(
            feeling=self._require_text(mapping["feeling"], "repeat_purchase.feeling"),
            condition=self._require_text(
                mapping["condition"], "repeat_purchase.condition"
            ),
            habit_or_inertia=self._require_text(
                mapping["habit_or_inertia"], "repeat_purchase.habit_or_inertia"
            ),
        )

    def _parse_competitor_reaction(self, item: Any) -> CompetitorReaction:
        mapping = self._require_mapping(item, "competitor_reaction")
        self._check_keys(
            mapping,
            required={"likely_shift", "reason", "retention_condition"},
            allowed={"likely_shift", "reason", "retention_condition"},
            label="competitor_reaction",
        )
        return CompetitorReaction(
            likely_shift=self._require_text(
                mapping["likely_shift"], "competitor_reaction.likely_shift"
            ),
            reason=self._require_text(mapping["reason"], "competitor_reaction.reason"),
            retention_condition=self._require_text(
                mapping["retention_condition"], "competitor_reaction.retention_condition"
            ),
        )

    def _parse_advocacy(self, item: Any) -> AdvocacyReaction:
        mapping = self._require_mapping(item, "advocacy")
        self._check_keys(
            mapping,
            required={"recommendation_feeling", "sharing_feeling", "friend_description"},
            allowed={"recommendation_feeling", "sharing_feeling", "friend_description"},
            label="advocacy",
        )
        return AdvocacyReaction(
            recommendation_feeling=self._require_text(
                mapping["recommendation_feeling"], "advocacy.recommendation_feeling"
            ),
            sharing_feeling=self._require_text(
                mapping["sharing_feeling"], "advocacy.sharing_feeling"
            ),
            friend_description=self._require_text(
                mapping["friend_description"], "advocacy.friend_description"
            ),
        )

    def _validate_feedback(self, feedback: ConsumerFeedback) -> None:
        self._reject_forbidden_terms(feedback.first_impression)
        self._reject_forbidden_terms(feedback.understood_offer)
        self._reject_forbidden_terms(feedback.perceived_positioning)
        self._reject_forbidden_terms(feedback.strongest_pull)
        self._reject_forbidden_terms(feedback.strongest_rejection)
        self._reject_forbidden_terms(feedback.current_attitude)
        diagnosis = feedback.behavior_diagnosis
        for text in (
            diagnosis.first_signal,
            diagnosis.reference_point,
            diagnosis.perceived_risk,
            diagnosis.action_friction,
            diagnosis.dominant_driver,
            feedback.repeat_purchase.feeling,
            feedback.repeat_purchase.condition,
            feedback.repeat_purchase.habit_or_inertia,
            feedback.competitor_reaction.likely_shift,
            feedback.competitor_reaction.reason,
            feedback.competitor_reaction.retention_condition,
            feedback.advocacy.recommendation_feeling,
            feedback.advocacy.sharing_feeling,
            feedback.advocacy.friend_description,
            *feedback.behavior_notes,
        ):
            self._reject_forbidden_terms(text)

    @staticmethod
    def _validate_persona(persona: Persona) -> None:
        for field_name, value in persona.__dict__.items():
            if not isinstance(value, str) or not value.strip():
                raise ConsumerInputError(f"Persona field '{field_name}' must be text.")

    @staticmethod
    def _validate_strategy(strategy: Strategy) -> None:
        if not strategy.name.strip() or not strategy.actions:
            raise ConsumerInputError("ConsumerAgent needs a named strategy with actions.")

    @staticmethod
    def _validate_scenario(scenario: Scenario) -> None:
        if not scenario.name.strip() or not scenario.situation.strip():
            raise ConsumerInputError("Scenario needs a name and situation.")

    @staticmethod
    def _validate_product_context(product_context: ProductContext) -> None:
        if not product_context.facts:
            raise ConsumerInputError("ProductContext needs product facts.")
        if not any(item.strip() for item in product_context.facts):
            raise ConsumerInputError("ProductContext product facts cannot be blank.")

    @classmethod
    def _reject_forbidden_payload(cls, value: Any) -> None:
        if isinstance(value, Mapping):
            for key, nested in value.items():
                normalized_key = str(key).replace("_", " ")
                if FORBIDDEN_CONSUMER_KEYS.search(normalized_key):
                    raise ConsumerOutputError(
                        "ConsumerAgent output includes a forbidden numeric judgement field."
                    )
                cls._reject_forbidden_payload(nested)
        elif isinstance(value, str):
            cls._reject_forbidden_terms(value)
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            for nested in value:
                cls._reject_forbidden_payload(nested)

    @staticmethod
    def _reject_forbidden_terms(text: str) -> None:
        if FORBIDDEN_CONSUMER_TERMS.search(text):
            raise ConsumerOutputError(
                "ConsumerAgent output includes a forbidden probability, score, or market judgement."
            )

    @staticmethod
    def _render_persona(persona: Persona) -> str:
        lines = [
            ("name", persona.name),
            ("core need", persona.core_need),
            ("purchase motivation", persona.purchase_motivation),
            ("current alternative", persona.current_alternative),
            ("price sensitivity", persona.price_sensitivity),
            ("trust sensitivity", persona.trust_sensitivity),
            ("promotion sensitivity", persona.promotion_sensitivity),
            ("channel preference", persona.channel_preference),
            ("social influence", persona.social_influence),
            ("main barrier", persona.main_barrier),
            ("repeat trigger", persona.repeat_trigger),
            ("switching threshold", persona.switching_threshold),
        ]
        return "\n".join(f"- {label}: {value}" for label, value in lines)

    @staticmethod
    def _render_scenario(scenario: Scenario) -> str:
        lines = [
            ("name", scenario.name),
            ("situation", scenario.situation),
            ("competitor pressure", scenario.competitor_pressure or "none supplied"),
            ("trust pressure", scenario.trust_pressure or "none supplied"),
            ("friction pressure", scenario.friction_pressure or "none supplied"),
        ]
        return "\n".join(f"- {label}: {value}" for label, value in lines)

    @staticmethod
    def _render_strategy(strategy: Strategy) -> str:
        action_lines = []
        for action in strategy.actions:
            rendered_parameters = json.dumps(
                dict(action.parameters), ensure_ascii=True, sort_keys=True
            )
            rendered_claims = ", ".join(action.product_claims) or "none"
            action_lines.append(
                f"- {action.category}: {action.summary} "
                f"| reason: {action.reason} "
                f"| parameters: {rendered_parameters} "
                f"| product claims: {rendered_claims}"
            )
        targets = ", ".join(strategy.target_consumers)
        tradeoffs = ", ".join(strategy.expected_tradeoffs)
        actions = "\n".join(action_lines)
        return (
            f"- name: {strategy.name}\n"
            f"- hypothesis: {strategy.hypothesis}\n"
            f"- target consumers: {targets}\n"
            f"- expected tradeoffs: {tradeoffs}\n"
            f"- actions:\n{actions}"
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
            raise ConsumerOutputError(f"{label} is missing keys: {rendered}.")
        extra = keys - allowed
        if extra:
            rendered = ", ".join(sorted(extra))
            raise ConsumerOutputError(f"{label} has unsupported keys: {rendered}.")

    @staticmethod
    def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
        if not isinstance(value, Mapping):
            raise ConsumerOutputError(f"{label} must be a JSON object.")
        return value

    @staticmethod
    def _require_text(value: Any, label: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ConsumerOutputError(f"{label} must be non-empty text.")
        return value.strip()

    def _parse_text_sequence(self, value: Any, label: str) -> tuple[str, ...]:
        if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
            raise ConsumerOutputError(f"{label} must be a list.")
        parsed = tuple(self._require_text(item, label) for item in value)
        if not parsed:
            raise ConsumerOutputError(f"{label} must contain at least one item.")
        return parsed
