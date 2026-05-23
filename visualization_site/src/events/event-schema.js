export const SANDBOX_EVENT_TYPES = Object.freeze({
  RUN_STARTED: "run_started",
  ROUND_PROGRESS: "round_progress",
  ROUND_STARTED: "round_started",
  FAMILY_SELECTED: "family_selected",
  STRATEGY_PROPOSED: "strategy_proposed",
  CONSUMER_FEEDBACK_READY: "consumer_feedback_ready",
  FEEDBACK_SUMMARY_READY: "feedback_summary_ready",
  CRITIQUE_READY: "critique_ready",
  SEARCH_UPDATED: "search_updated",
  ROUND_COMPLETED: "round_completed",
  RUN_FAILED: "run_failed",
  RUN_COMPLETED: "run_completed",
});

export const SANDBOX_EVENT_CONTRACT_VERSION = "marketing-sandbox-web-events/v1";

export const SANDBOX_EVENT_CONTRACT = Object.freeze({
  [SANDBOX_EVENT_TYPES.RUN_STARTED]: Object.freeze({
    category: "lifecycle",
    requiredFields: ["id", "type", "round", "headline", "summary"],
    purpose: "Marks the beginning of a live or replayed sandbox run.",
  }),
  [SANDBOX_EVENT_TYPES.ROUND_PROGRESS]: Object.freeze({
    category: "lifecycle",
    requiredFields: ["id", "type", "round", "progress", "headline", "summary"],
    purpose: "Shows a live round is calling model agents before completed round data exists.",
  }),
  [SANDBOX_EVENT_TYPES.ROUND_STARTED]: Object.freeze({
    category: "lifecycle",
    requiredFields: ["id", "type", "round", "proposal", "headline", "summary"],
    purpose: "Opens a completed round payload for playback.",
  }),
  [SANDBOX_EVENT_TYPES.FAMILY_SELECTED]: Object.freeze({
    category: "ucb",
    requiredFields: ["id", "type", "round", "family", "internalSearch", "headline", "summary"],
    purpose: "Shows the selected strategy family and internal UCB audit fields.",
  }),
  [SANDBOX_EVENT_TYPES.STRATEGY_PROPOSED]: Object.freeze({
    category: "strategy_proposal",
    requiredFields: ["id", "type", "round", "strategy", "headline", "summary"],
    purpose: "Shows a DecisionAgent strategy candidate.",
  }),
  [SANDBOX_EVENT_TYPES.CONSUMER_FEEDBACK_READY]: Object.freeze({
    category: "role_speech",
    requiredFields: ["id", "type", "round", "feedback", "headline", "summary"],
    purpose: "Shows one consumer persona's qualitative reaction.",
  }),
  [SANDBOX_EVENT_TYPES.FEEDBACK_SUMMARY_READY]: Object.freeze({
    category: "synthesis",
    requiredFields: ["id", "type", "round", "synthesis", "headline", "summary"],
    purpose: "Shows the feedback synthesizer's qualitative summary.",
  }),
  [SANDBOX_EVENT_TYPES.CRITIQUE_READY]: Object.freeze({
    category: "critique",
    requiredFields: ["id", "type", "round", "critique", "headline", "summary"],
    purpose: "Shows the critic's risk review.",
  }),
  [SANDBOX_EVENT_TYPES.SEARCH_UPDATED]: Object.freeze({
    category: "reward_ucb",
    requiredFields: ["id", "type", "round", "search", "headline", "summary"],
    purpose: "Carries internal reward and UCB state updates.",
  }),
  [SANDBOX_EVENT_TYPES.ROUND_COMPLETED]: Object.freeze({
    category: "safe_boundary",
    requiredFields: ["id", "type", "round", "headline", "summary"],
    purpose: "Marks a safe archive boundary after a complete round.",
  }),
  [SANDBOX_EVENT_TYPES.RUN_FAILED]: Object.freeze({
    category: "lifecycle",
    requiredFields: ["id", "type", "round", "issue", "headline", "summary"],
    purpose: "Marks a failed live run with a redacted diagnostic detail.",
  }),
  [SANDBOX_EVENT_TYPES.RUN_COMPLETED]: Object.freeze({
    category: "lifecycle",
    requiredFields: ["id", "type", "round", "result", "headline", "summary"],
    purpose: "Marks normal completion of the run.",
  }),
});

const REQUIRED_TEXT_FIELDS = ["id", "type", "headline", "summary"];
const EVENT_TYPE_SET = new Set(Object.values(SANDBOX_EVENT_TYPES));

export function validateSandboxEvent(event, index = 0) {
  if (!event || typeof event !== "object") {
    throw new TypeError(`Sandbox event ${index} must be an object.`);
  }

  for (const field of REQUIRED_TEXT_FIELDS) {
    if (typeof event[field] !== "string" || event[field].trim() === "") {
      throw new TypeError(`Sandbox event ${index} is missing text field "${field}".`);
    }
  }

  if (!EVENT_TYPE_SET.has(event.type)) {
    throw new TypeError(`Sandbox event ${index} has unknown type "${event.type}".`);
  }

  if (
    event.contractVersion &&
    event.contractVersion !== SANDBOX_EVENT_CONTRACT_VERSION
  ) {
    throw new TypeError(`Sandbox event ${index} has unsupported contract version.`);
  }

  if (!Number.isInteger(event.round) || event.round < 0) {
    throw new TypeError(`Sandbox event ${index} has an invalid round.`);
  }

  return event;
}

export function normalizeSandboxEvents(events) {
  if (!Array.isArray(events) || events.length === 0) {
    throw new TypeError("Sandbox event list must contain at least one event.");
  }

  const seenIds = new Set();
  return events.map((event, index) => {
    const validEvent = validateSandboxEvent(event, index);
    if (seenIds.has(validEvent.id)) {
      throw new TypeError(`Sandbox event id "${validEvent.id}" is duplicated.`);
    }

    seenIds.add(validEvent.id);
    return validEvent;
  });
}

export function eventContractFor(type) {
  return SANDBOX_EVENT_CONTRACT[type] || null;
}
