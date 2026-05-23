import {
  SANDBOX_EVENT_CONTRACT_VERSION,
  SANDBOX_EVENT_TYPES,
  normalizeSandboxEvents,
} from "./event-schema.js";

export const ARCHIVE_SCHEMA_VERSION = "marketing-sandbox-archive/v1";
export const ARCHIVE_FORMAT_VERSION = 2;
export const SANDBOX_CORE_VERSION = "marketing-sandbox-core/v1";
export const STOP_ENDPOINT = "/api/sandbox/runs/stop";
export const ARCHIVE_ENDPOINT = "/api/sandbox/archives";
export const DISCONNECT_TIMEOUT_ENDPOINT_SUFFIX = "api-disconnect-timeout";
const LOCAL_ARCHIVE_KEY = "marketingSandboxArchives";

export function createRunId(prefix = "live") {
  const safePrefix = String(prefix).replace(/[^A-Za-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "") || "live";
  return `${safePrefix}-${Date.now().toString(36)}`;
}

export async function requestLiveRunStop(runId, options = {}) {
  const fetchImpl = options.fetchImpl || globalThis.fetch;
  if (!runId) {
    return { ok: false, status: "missing_run_id", message: "No live run id is active." };
  }

  if (typeof fetchImpl !== "function") {
    return { ok: false, status: "stop_unavailable", message: "Stop endpoint is unavailable." };
  }

  try {
    const response = await fetchImpl(options.endpoint || STOP_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ runId, reason: "user_stop" }),
    });
    const body = await response.text();
    if (!response.ok) {
      return {
        ok: false,
        status: "stop_failed",
        message: readResponseMessage(body) || `Stop failed with HTTP ${response.status}.`,
      };
    }

    return body ? JSON.parse(body) : { ok: true, status: "stop_requested", runId };
  } catch (error) {
    return {
      ok: false,
      status: "stop_unavailable",
      message: error instanceof Error ? error.message : String(error),
    };
  }
}

export function createArchiveCandidate({
  runId,
  runConfig,
  events,
  label = "",
  status = "stopped",
  stopReason = "user_stop",
  createdAt = new Date().toISOString(),
}) {
  const safeEvents = safeArchiveEvents(events);
  const safeConfig = sanitizeRunConfig(runConfig);
  const searchState = recoverArchiveSearchState(safeEvents, safeConfig);
  const canContinue = canContinueFromArchiveParts(searchState, safeEvents, safeConfig, true);
  return {
    schemaVersion: ARCHIVE_SCHEMA_VERSION,
    archiveFormatVersion: ARCHIVE_FORMAT_VERSION,
    sandboxCoreVersion: SANDBOX_CORE_VERSION,
    eventContractVersion: SANDBOX_EVENT_CONTRACT_VERSION,
    archiveId: `${sanitizeToken(runId || "archive")}-${Date.now().toString(36)}`,
    createdAt,
    label: label || runId || "Stopped sandbox run",
    status,
    stopReason,
    sessionSnapshot: {
      source: safeConfig.source,
      config: safeConfig,
      sessionKeyPresent: false,
    },
    playback: {
      source: "browser_archive",
      events: safeEvents.events,
    },
    safeBoundary: {
      completedRounds: safeEvents.completedRounds,
      completedRoundCount: safeEvents.completedRounds.length,
      latestSafeEventId: safeEvents.latestSafeEventId,
      partialEventsDropped: safeEvents.partialEventsDropped,
      safeBoundaryRule: "latest round_completed or run_completed event",
    },
    searchState,
    resume: {
      canReplay: safeEvents.events.length > 0,
      canContinue,
      mode: canContinue ? "continue_from_completed_round" : "replay_only",
      requiresFreshCredentials: true,
      blockedReason: canContinue ? "" : resumeBlockedReason(searchState, safeEvents, safeConfig, true),
    },
    versionCompatibility: {
      status: "compatible",
      canReplay: safeEvents.events.length > 0,
      canContinue,
      resumePolicy: canContinue ? "continue_from_completed_round" : "replay_only",
    },
  };
}

export function safeArchiveEvents(events) {
  const normalizedEvents = normalizeSandboxEvents(events);
  let lastSafeIndex = -1;
  const completedRounds = [];

  normalizedEvents.forEach((event, index) => {
    if (event.type === "round_completed" || event.type === "run_completed") {
      lastSafeIndex = index;
    }
    if (event.type === "round_completed" && !completedRounds.includes(event.round)) {
      completedRounds.push(event.round);
    }
  });

  const safeEvents =
    lastSafeIndex >= 0
      ? normalizedEvents.slice(0, lastSafeIndex + 1)
      : normalizedEvents.filter((event) => event.type === "run_started");

  return {
    events: safeEvents,
    completedRounds,
    latestSafeEventId: safeEvents.at(-1)?.id || "",
    partialEventsDropped: normalizedEvents.length - safeEvents.length,
  };
}

export async function saveArchive(archive, options = {}) {
  const cleanArchive = validateArchive(archive);
  const fetchImpl = options.fetchImpl || globalThis.fetch;

  if (!options.preferLocal && typeof fetchImpl === "function") {
    try {
      const response = await fetchImpl(options.endpoint || ARCHIVE_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ archive: cleanArchive }),
      });
      if (response.ok) {
        const body = await response.text();
        const payload = body ? JSON.parse(body) : { ok: true, archive: archiveSummary(cleanArchive) };
        return {
          ...payload,
          storage: payload.storage || "backend",
        };
      }
    } catch {
      // Fall through to local archive storage for classroom demos without a backend.
    }
  }

  const storage = archiveStorage(options.storage);
  const archives = readLocalArchives(storage);
  archives[cleanArchive.archiveId] = cleanArchive;
  storage.setItem(LOCAL_ARCHIVE_KEY, JSON.stringify(archives));
  return { ok: true, archive: archiveSummary(cleanArchive), storage: "local" };
}

export async function listArchives(options = {}) {
  const fetchImpl = options.fetchImpl || globalThis.fetch;
  const localSummaries = () => {
    try {
      return Object.values(readLocalArchives(archiveStorage(options.storage)))
        .map((archive) => ({ ...archiveSummary(archive), storage: "local" }));
    } catch (error) {
      if (error instanceof TypeError && String(error.message).includes("Archive storage is unavailable")) {
        return [];
      }
      throw error;
    }
  };

  if (!options.preferLocal && typeof fetchImpl === "function") {
    try {
      const response = await fetchImpl(options.endpoint || ARCHIVE_ENDPOINT, {
        method: "GET",
        headers: { Accept: "application/json" },
      });
      if (response.ok) {
        const body = await response.json();
        const backendSummaries = Array.isArray(body.archives)
          ? body.archives.map((archive) => ({ ...archive, storage: archive.storage || "backend" }))
          : [];
        const seen = new Set(backendSummaries.map((archive) => archive.archiveId));
        return [
          ...backendSummaries,
          ...localSummaries().filter((archive) => !seen.has(archive.archiveId)),
        ];
      }
    } catch {
      // Fall through to local archive storage.
    }
  }

  return localSummaries();
}

export async function loadArchive(archiveId, options = {}) {
  const fetchImpl = options.fetchImpl || globalThis.fetch;
  if (!options.preferLocal && typeof fetchImpl === "function") {
    try {
      const response = await fetchImpl(`${options.endpoint || ARCHIVE_ENDPOINT}/${encodeURIComponent(archiveId)}`, {
        method: "GET",
        headers: { Accept: "application/json" },
      });
      if (response.ok) {
        const payload = await response.json();
        return validateArchive(payload.archive || payload);
      }
    } catch {
      // Fall through to local archive storage.
    }
  }

  const archive = readLocalArchives(archiveStorage(options.storage))[archiveId];
  if (!archive) {
    throw new Error(`Archive "${archiveId}" was not found.`);
  }

  return validateArchive(archive);
}

export async function requestArchiveResumePlan(archiveId, options = {}) {
  const fetchImpl = options.fetchImpl || globalThis.fetch;
  if (!archiveId) {
    return { ok: false, status: "missing_archive_id", message: "No archive is selected." };
  }
  if (typeof fetchImpl !== "function") {
    return { ok: false, status: "resume_unavailable", message: "Resume endpoint is unavailable." };
  }

  try {
    const response = await fetchImpl(`${options.endpoint || ARCHIVE_ENDPOINT}/${encodeURIComponent(archiveId)}/resume`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(options.payload || {}),
    });
    const body = await response.text();
    const payload = body ? JSON.parse(body) : {};
    if (!response.ok || payload.ok === false) {
      return {
        ok: false,
        status: payload.status || "resume_failed",
        message: payload.message || `Resume failed with HTTP ${response.status}.`,
      };
    }

    return { ...payload, storage: payload.storage || "backend" };
  } catch (error) {
    return {
      ok: false,
      status: "resume_unavailable",
      message: error instanceof Error ? error.message : String(error),
    };
  }
}

export async function requestApiDisconnectAutoArchive({
  runId,
  disconnectedSeconds,
  timeoutSeconds,
  message = "",
}, options = {}) {
  const fetchImpl = options.fetchImpl || globalThis.fetch;
  if (!runId) {
    return { ok: false, status: "missing_run_id", message: "No live run id is active." };
  }
  if (typeof fetchImpl !== "function") {
    return { ok: false, status: "disconnect_endpoint_unavailable", message: "Disconnect archive endpoint is unavailable." };
  }

  try {
    const response = await fetchImpl(
      `${options.runsEndpoint || "/api/sandbox/runs"}/${encodeURIComponent(runId)}/${DISCONNECT_TIMEOUT_ENDPOINT_SUFFIX}`,
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          disconnectedSeconds,
          timeoutSeconds,
          message,
        }),
      },
    );
    const body = await response.text();
    const payload = body ? JSON.parse(body) : {};
    if (!response.ok || payload.ok === false) {
      return {
        ok: false,
        status: payload.status || "disconnect_archive_failed",
        message: payload.message || `Disconnect auto-archive failed with HTTP ${response.status}.`,
      };
    }

    return { ...payload, storage: payload.storage || "backend" };
  } catch (error) {
    return {
      ok: false,
      status: "disconnect_endpoint_unavailable",
      message: error instanceof Error ? error.message : String(error),
    };
  }
}

export function shouldAutoArchiveDisconnect({ disconnectedMs, timeoutMs }) {
  return Number.isFinite(disconnectedMs) && Number.isFinite(timeoutMs) && disconnectedMs >= timeoutMs;
}

export function validateArchive(archive) {
  if (!archive || typeof archive !== "object") {
    throw new TypeError("Archive must be an object.");
  }
  if (!archive.archiveId || typeof archive.archiveId !== "string") {
    throw new TypeError("Archive needs an archiveId.");
  }
  const events = normalizeSandboxEvents(archive.playback?.events || []);
  const serialized = JSON.stringify(archive);
  if (serialized.includes("apiKey") || serialized.includes("Authorization")) {
    throw new TypeError("Archive must not contain API key fields.");
  }
  const schemaSupported = archive.schemaVersion === ARCHIVE_SCHEMA_VERSION;
  const explicitCoreVersion = typeof archive.sandboxCoreVersion === "string";
  const sandboxCoreVersion = explicitCoreVersion ? archive.sandboxCoreVersion : SANDBOX_CORE_VERSION;
  const versionCompatible = schemaSupported && (!explicitCoreVersion || sandboxCoreVersion === SANDBOX_CORE_VERSION);
  const safeEvents = safeArchiveEvents(events);
  const safeConfig = sanitizeRunConfig(archive.sessionSnapshot?.config || {});
  const searchState = archive.searchState?.familyStates
    ? archive.searchState
    : recoverArchiveSearchState(safeEvents, safeConfig);
  const canContinue = Boolean(
    archive.resume?.canContinue &&
      canContinueFromArchiveParts(searchState, safeEvents, safeConfig, versionCompatible),
  );
  return {
    ...archive,
    schemaVersion: archive.schemaVersion || "unknown",
    archiveFormatVersion: archive.archiveFormatVersion || ARCHIVE_FORMAT_VERSION,
    sandboxCoreVersion,
    eventContractVersion: archive.eventContractVersion || SANDBOX_EVENT_CONTRACT_VERSION,
    playback: {
      ...(archive.playback || {}),
      events,
    },
    safeBoundary: {
      ...(archive.safeBoundary || {}),
      completedRounds: safeEvents.completedRounds,
      completedRoundCount: safeEvents.completedRounds.length,
      latestSafeEventId: safeEvents.latestSafeEventId,
      partialEventsDropped: safeEvents.partialEventsDropped,
      safeBoundaryRule: "latest round_completed or run_completed event",
    },
    searchState,
    resume: {
      ...(archive.resume || {}),
      canReplay: events.length > 0,
      canContinue,
      mode: canContinue ? "continue_from_completed_round" : "replay_only",
      requiresFreshCredentials: true,
      blockedReason: canContinue
        ? ""
        : resumeBlockedReason(searchState, safeEvents, safeConfig, versionCompatible),
    },
    versionCompatibility: {
      status: versionCompatibilityStatus(schemaSupported, explicitCoreVersion, sandboxCoreVersion),
      canReplay: events.length > 0,
      canContinue,
      resumePolicy: canContinue ? "continue_from_completed_round" : "replay_only",
      schemaVersion: archive.schemaVersion || "unknown",
      sandboxCoreVersion,
      eventContractVersion: archive.eventContractVersion || SANDBOX_EVENT_CONTRACT_VERSION,
    },
  };
}

export function sanitizeRunConfig(runConfig) {
  const cloned = JSON.parse(JSON.stringify(runConfig || {}));
  if (cloned.provider) {
    delete cloned.provider.apiKey;
  }
  return cloned;
}

function archiveSummary(archive) {
  return {
    archiveId: archive.archiveId,
    createdAt: archive.createdAt,
    label: archive.label,
    status: archive.status,
    stopReason: archive.stopReason,
    eventCount: archive.playback.events.length,
    completedRoundCount: archive.safeBoundary?.completedRoundCount || 0,
    canContinue: Boolean(archive.resume?.canContinue),
    schemaVersion: archive.schemaVersion,
    sandboxCoreVersion: archive.sandboxCoreVersion,
    versionCompatibility: archive.versionCompatibility,
  };
}

export function recoverArchiveSearchState(safeEvents, runConfig = {}) {
  const familyStates = {};
  const rewardHistory = [];
  const latestStrategyByFamily = {};
  for (const [order, event] of safeEvents.events.entries()) {
    if (event.type === SANDBOX_EVENT_TYPES.STRATEGY_PROPOSED && event.strategy?.familyId) {
      latestStrategyByFamily[event.strategy.familyId] = {
        familyId: event.strategy.familyId,
        strategyName: event.strategy.name || "",
        intent: event.strategy.intent || "",
        familyFit: event.strategy.familyFit || "",
        round: event.round,
        eventId: event.id,
      };
    }
    if (event.type !== SANDBOX_EVENT_TYPES.SEARCH_UPDATED) {
      continue;
    }
    const metrics = event.search?.internalMetrics || {};
    const familyId = metrics.familyId || event.search?.families?.[0]?.id;
    if (!familyId) {
      continue;
    }
    const stateAfter = metrics.stateAfter || {};
    const signals = event.search?.signals || {};
    const reward = typeof metrics.reward === "number" ? metrics.reward : null;
    const previous = familyStates[familyId] || {};
    const pullCount = Number.isInteger(stateAfter.pullCount)
      ? stateAfter.pullCount
      : (previous.pullCount || 0) + (reward === null ? 0 : 1);
    const rewardSum = typeof stateAfter.rewardSum === "number"
      ? stateAfter.rewardSum
      : (previous.rewardSum || 0) + (reward || 0);
    const meanReward = typeof stateAfter.meanReward === "number"
      ? stateAfter.meanReward
      : (pullCount ? rewardSum / pullCount : 0);
    const strategyName =
      signals.strategyName ||
      latestStrategyByFamily[familyId]?.strategyName ||
      `${familyId} strategy`;
    if (reward !== null) {
      rewardHistory.push({
        order,
        eventId: event.id,
        round: event.round,
        familyId,
        strategyName,
        reward,
        positiveUtility: metrics.positiveUtility,
        riskPenalty: metrics.riskPenalty,
        positiveComponents: metrics.positiveComponents || {},
        riskComponents: metrics.riskComponents || {},
        appliedCaps: metrics.appliedCaps || [],
        mappingNote: metrics.mappingNote || "",
        summaryNote: signals.summaryLabels?.signal_note || signals.summary || "",
        riskNote: signals.riskLabels?.risk_note || signals.risk || "",
      });
    }
    familyStates[familyId] = {
      familyId,
      pullCount,
      rewardSum,
      meanReward,
      lastSelectedRound: stateAfter.lastSelectedRound || event.round,
      latestStrategy: latestStrategyByFamily[familyId] || {
        familyId,
        strategyName,
        round: event.round,
      },
      latestRewardEventId: event.id,
    };
  }
  const currentBestFamilyId = Object.values(familyStates)
    .sort((left, right) => (right.meanReward || 0) - (left.meanReward || 0))[0]?.familyId || "";
  return {
    source: "completed_round_events",
    ucbStateIncludesCompletedRoundsOnly: true,
    metricBoundary: "Archived reward and UCB values are internal search trace, not market forecasts.",
    completedRoundCount: safeEvents.completedRounds.length,
    completedRounds: safeEvents.completedRounds,
    partialEventsDropped: safeEvents.partialEventsDropped,
    nextRoundIndex: safeEvents.completedRounds.length ? Math.max(...safeEvents.completedRounds) + 1 : 1,
    usesUcb: Boolean(runConfig.search?.useUcb),
    restoresUcbState: rewardHistory.length > 0,
    familyStates,
    rewardHistory,
    currentBestFamilyId,
    currentBestStrategy: familyStates[currentBestFamilyId]?.latestStrategy || {},
    recoveryRule:
      "Only search_updated events before the latest safe round_completed or run_completed boundary are used for UCB recovery.",
  };
}

function canContinueFromArchiveParts(searchState, safeEvents, runConfig, versionCompatible) {
  if (!versionCompatible || safeEvents.completedRounds.length === 0) {
    return false;
  }
  return runConfig.search?.useUcb ? Boolean(searchState.restoresUcbState) : true;
}

function resumeBlockedReason(searchState, safeEvents, runConfig, versionCompatible) {
  if (!versionCompatible) {
    return "Archive version is replay-only and cannot be resumed blindly.";
  }
  if (safeEvents.completedRounds.length === 0) {
    return "Archive has no completed round to continue from.";
  }
  if (runConfig.search?.useUcb && !searchState.restoresUcbState) {
    return "UCB archive has no recoverable completed reward history.";
  }
  return "Archive can be replayed but cannot be safely resumed.";
}

function versionCompatibilityStatus(schemaSupported, explicitCoreVersion, sandboxCoreVersion) {
  if (!schemaSupported) {
    return "unsupported_schema_replay_only";
  }
  if (explicitCoreVersion && sandboxCoreVersion !== SANDBOX_CORE_VERSION) {
    return "incompatible_core_replay_only";
  }
  if (!explicitCoreVersion) {
    return "migrated_current_core";
  }
  return "compatible";
}

function readLocalArchives(storage) {
  try {
    return JSON.parse(storage.getItem(LOCAL_ARCHIVE_KEY) || "{}");
  } catch {
    return {};
  }
}

function archiveStorage(storage) {
  if (storage) {
    return storage;
  }
  if (!globalThis.localStorage) {
    throw new TypeError("Archive storage is unavailable.");
  }
  return globalThis.localStorage;
}

function sanitizeToken(value) {
  return String(value).replace(/[^A-Za-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "") || "archive";
}

function readResponseMessage(body) {
  try {
    const parsed = JSON.parse(body);
    return parsed.message || "";
  } catch {
    return body;
  }
}
