"""Minimal web-runner assembly layer for the marketing sandbox."""

from __future__ import annotations

from typing import Any, Callable, Mapping

from .action_space import ActionSpace
from .consumer_agent import ConsumerAgent, Persona, Scenario
from .critic_agent import CriticAgent
from .decision_agent import DecisionAgent
from .feedback_synthesizer import FeedbackSynthesizer
from .llm_backend import openai_compatible_backend_factory
from .marketing_sandbox import MarketingSandbox, SandboxContext, SandboxResult
from .persona_catalog import DEFAULT_CONSUMER_PERSONA_BY_ID
from .reward_mapper import RewardMapper
from .search_models import StrategyFamily, UCBSearchConfig
from .ucb_search_controller import UCBSearchController
from .web_session import ROLE_MODEL_KEYS, WebRunConfig, WebRunSession


WebBackendFactory = Callable[..., Any]


DEFAULT_WEB_SCENARIOS: dict[str, Scenario] = {
    "normal": Scenario(
        name="Normal comparison",
        situation="The selected personas compare the offer in an ordinary market moment.",
    ),
    "competitor-pressure": Scenario(
        name="Competitor pressure",
        situation="A credible competitor is visible during offer comparison.",
        competitor_pressure="The competitor makes its alternative easy to notice.",
    ),
    "trust-pressure": Scenario(
        name="Trust pressure",
        situation="Unfamiliar claims meet a cautious trust-checking moment.",
        trust_pressure="The persona needs evidence and boundaries before acting.",
    ),
}


DEFAULT_WEB_STRATEGY_FAMILIES: dict[str, StrategyFamily] = {
    "trial_value_entry": StrategyFamily(
        family_id="trial_value_entry",
        name="Trial value entry",
        core_barrier="First use feels too costly or too committal.",
        win_mechanism="Create a bounded first step whose value can be understood.",
        generation_guidance=(
            "Use trial access and concrete value without turning every reason into a discount."
        ),
        expected_action_patterns=(
            "clear trial offer",
            "bounded entry value",
            "first-use friction reduction",
        ),
        failure_signals=(
            "promotion hides product fit",
            "repeat reason disappears after trial",
        ),
    ),
    "trust_risk_reduction": StrategyFamily(
        family_id="trust_risk_reduction",
        name="Trust and risk reduction",
        core_barrier="The first choice can feel risky or regrettable.",
        win_mechanism="Make the promise more believable, bounded, and reversible.",
        generation_guidance=(
            "Lead with proof, service reassurance, and product-boundary clarity."
        ),
        expected_action_patterns=(
            "credible evidence cue",
            "risk reassurance",
            "trusted comparison path",
        ),
        failure_signals=(
            "claims outrun supplied facts",
            "trust message becomes noisy promotion",
        ),
    ),
    "retention_habit_defense": StrategyFamily(
        family_id="retention_habit_defense",
        name="Retention habit defense",
        core_barrier="A first try does not yet create a repeat routine.",
        win_mechanism="Connect first use to a believable repeat trigger and switching defense.",
        generation_guidance=(
            "Test repeat cues, convenience, and post-trial value without inventing loyalty."
        ),
        expected_action_patterns=(
            "repeat trigger",
            "retention support",
            "competitor switching defense",
        ),
        failure_signals=(
            "retention promise arrives before product proof",
            "membership adds friction",
        ),
    ),
}

DEFAULT_WEB_PARAMETER_LIMITS: dict[str, dict[str, tuple[float | None, float | None]]] = {
    "positioning": {
        "duration_weeks": (1, 52),
    },
    "product": {
        "duration_weeks": (1, 52),
    },
    "price": {
        "list_price": (0, 10000),
        "price_USD": (0, 10000),
        "discount_rate": (0, 0.95),
        "coupon_value": (0, 10000),
        "duration_weeks": (1, 52),
    },
    "channel": {
        "duration_weeks": (1, 52),
    },
    "promotion": {
        "content_budget": (0, 1000000),
        "discount_rate": (0, 0.95),
        "coupon_value": (0, 10000),
        "duration_weeks": (1, 52),
    },
    "retention": {
        "duration_weeks": (1, 52),
        "discount_rate": (0, 0.95),
        "coupon_value": (0, 10000),
    },
}


class WebRunnerError(Exception):
    """Raised when a website session cannot be assembled into a sandbox."""


class WebSandboxRunner:
    """Assemble existing sandbox objects from one validated web run session.

    The runner exists because browser/session concerns do not belong inside
    ``MarketingSandbox``. Event streaming, stopping, and archives stay outside
    this first assembly boundary and can build on the returned sandbox later.
    """

    def __init__(
        self,
        backend_factory: WebBackendFactory | None = None,
        *,
        persona_catalog: Mapping[str, Persona] | None = None,
        scenario_catalog: Mapping[str, Scenario] | None = None,
        family_catalog: Mapping[str, StrategyFamily] | None = None,
    ) -> None:
        resolved_factory = backend_factory or openai_compatible_backend_factory
        if not callable(resolved_factory):
            raise WebRunnerError("WebSandboxRunner backend_factory must be callable.")
        self._backend_factory = resolved_factory
        self._persona_catalog = self._copy_catalog(
            persona_catalog or DEFAULT_CONSUMER_PERSONA_BY_ID,
            Persona,
            "persona catalog",
        )
        self._scenario_catalog = self._copy_catalog(
            scenario_catalog or DEFAULT_WEB_SCENARIOS,
            Scenario,
            "scenario catalog",
        )
        self._family_catalog = self._copy_catalog(
            family_catalog or DEFAULT_WEB_STRATEGY_FAMILIES,
            StrategyFamily,
            "strategy family catalog",
        )

    def build_sandbox(self, session: WebRunSession) -> MarketingSandbox:
        """Return a core sandbox assembled from a live web session."""

        config = self._require_live_session(session)
        action_space = self._build_action_space(config)
        personas = self._select_personas(config)
        scenario = self._select_scenario(config)
        decision_agent = DecisionAgent(
            self._make_backend("decision", session),
            action_space,
            max_candidates=config.candidates_per_round,
        )
        consumer_agents = tuple(
            ConsumerAgent(
                self._make_backend("consumers", session, persona=persona),
                persona,
            )
            for persona in personas
        )
        feedback_synthesizer = FeedbackSynthesizer(
            self._make_backend("synthesizer", session)
        )
        critic_agent = CriticAgent(self._make_backend("critic", session))
        search_controller, reward_mapper = self._build_search_layer(config)
        return MarketingSandbox(
            context=self._build_context(config, personas),
            action_space=action_space,
            decision_agent=decision_agent,
            consumer_agents=consumer_agents,
            feedback_synthesizer=feedback_synthesizer,
            critic_agent=critic_agent,
            scenarios=(scenario,),
            search_controller=search_controller,
            reward_mapper=reward_mapper,
        )

    def run(
        self,
        session: WebRunSession,
        *,
        round_count: int | None = None,
    ) -> SandboxResult:
        """Build a sandbox and run the requested number of complete rounds."""

        sandbox = self.build_sandbox(session)
        rounds = session.config.rounds if round_count is None else round_count
        return sandbox.run(round_count=rounds)

    def _make_backend(
        self,
        role: str,
        session: WebRunSession,
        *,
        persona: Persona | None = None,
    ) -> Any:
        if role not in ROLE_MODEL_KEYS:
            raise WebRunnerError(f"Unknown web model role: {role}.")
        try:
            return self._backend_factory(
                role=role,
                model=self._model_for(session.config, role),
                session=session,
                persona=persona,
            )
        except WebRunnerError:
            raise
        except Exception as error:  # noqa: BLE001 - adapter factories vary.
            raise WebRunnerError(f"Backend factory failed for {role}.") from error

    @staticmethod
    def _model_for(config: WebRunConfig, role: str) -> str:
        model = config.provider.role_models.get(role) or config.provider.default_model
        if not model:
            raise WebRunnerError(f"No model route is available for {role}.")
        return model

    @staticmethod
    def _require_live_session(session: WebRunSession) -> WebRunConfig:
        if not isinstance(session, WebRunSession):
            raise WebRunnerError("WebSandboxRunner needs a WebRunSession.")
        if session.config.source != "live":
            raise WebRunnerError("Fixture playback does not use the live web runner.")
        return session.config

    @staticmethod
    def _build_action_space(config: WebRunConfig) -> ActionSpace:
        categories = frozenset(category.lower() for category in config.action_categories)
        parameter_limits = {
            category: limits
            for category, limits in DEFAULT_WEB_PARAMETER_LIMITS.items()
            if category in categories
        }
        return ActionSpace(
            allowed_categories=categories,
            parameter_limits=parameter_limits,
        )

    def _select_personas(self, config: WebRunConfig) -> tuple[Persona, ...]:
        try:
            return tuple(self._persona_catalog[persona_id] for persona_id in config.persona_ids)
        except KeyError as error:
            raise WebRunnerError(f"Unknown persona id for web runner: {error.args[0]}.") from error

    def _select_scenario(self, config: WebRunConfig) -> Scenario:
        try:
            return self._scenario_catalog[config.scenario_id]
        except KeyError as error:
            raise WebRunnerError(
                f"Unknown scenario id for web runner: {config.scenario_id}."
            ) from error

    def _build_search_layer(
        self,
        config: WebRunConfig,
    ) -> tuple[UCBSearchController | None, RewardMapper | None]:
        if not config.use_ucb:
            return None, None
        families: list[StrategyFamily] = []
        for family_id in config.family_ids:
            try:
                families.append(self._family_catalog[family_id])
            except KeyError as error:
                raise WebRunnerError(
                    f"Unknown strategy family id for web runner: {family_id}."
                ) from error
        try:
            return (
                UCBSearchController(
                    tuple(families),
                    UCBSearchConfig(
                        candidate_slots_per_round=config.candidates_per_round
                    ),
                ),
                RewardMapper(),
            )
        except Exception as error:  # noqa: BLE001 - normalize assembly failure.
            raise WebRunnerError("Web search layer could not be assembled.") from error

    @staticmethod
    def _build_context(
        config: WebRunConfig,
        personas: tuple[Persona, ...],
    ) -> SandboxContext:
        persona_names = ", ".join(persona.name for persona in personas)
        brand_boundary = (
            config.brand_facts
            or "Do not invent brand facts beyond the website input."
        )
        return SandboxContext(
            product_facts=(config.product_facts,),
            marketing_objectives=(config.marketing_goal,),
            core_target=f"Selected website persona cards: {persona_names}.",
            product_boundaries=(config.product_facts,),
            brand_boundaries=(brand_boundary,),
            brand_facts=(config.brand_facts,) if config.brand_facts else (),
            known_facts=(f"Website product name: {config.product_name}.",),
        )

    @staticmethod
    def _copy_catalog(
        catalog: Mapping[str, Any],
        expected_type: type,
        label: str,
    ) -> dict[str, Any]:
        if not isinstance(catalog, Mapping) or not catalog:
            raise WebRunnerError(f"WebSandboxRunner {label} must be a mapping.")
        copied: dict[str, Any] = {}
        for item_id, item in catalog.items():
            if not isinstance(item_id, str) or not item_id.strip():
                raise WebRunnerError(f"WebSandboxRunner {label} ids must be text.")
            if not isinstance(item, expected_type):
                raise WebRunnerError(
                    f"WebSandboxRunner {label} entries must be {expected_type.__name__}."
                )
            copied[item_id.strip()] = item
        return copied
