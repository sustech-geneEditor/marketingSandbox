import assert from "node:assert/strict";
import test from "node:test";

import { SANDBOX_EVENT_TYPES } from "../src/events/event-schema.js";
import {
  ARCHIVE_FORMAT_VERSION,
  createArchiveCandidate,
  createRunId,
  listArchives,
  loadArchive,
  requestApiDisconnectAutoArchive,
  requestArchiveResumePlan,
  requestLiveRunStop,
  safeArchiveEvents,
  saveArchive,
  SANDBOX_CORE_VERSION,
  shouldAutoArchiveDisconnect,
  validateArchive,
} from "../src/events/run-lifecycle.js";

const RUN_STARTED = {
  id: "run-001-start",
  type: SANDBOX_EVENT_TYPES.RUN_STARTED,
  round: 0,
  headline: "Run started",
  summary: "Run starts.",
};

const ROUND_STARTED = {
  id: "run-002-round",
  type: SANDBOX_EVENT_TYPES.ROUND_STARTED,
  round: 1,
  headline: "Round started",
  summary: "Round starts.",
};

const STRATEGY_PROPOSED = {
  id: "run-003-strategy",
  type: SANDBOX_EVENT_TYPES.STRATEGY_PROPOSED,
  round: 1,
  headline: "Strategy proposed",
  summary: "Decision proposes.",
};

const ROUND_COMPLETED = {
  id: "run-004-complete",
  type: SANDBOX_EVENT_TYPES.ROUND_COMPLETED,
  round: 1,
  headline: "Round completed",
  summary: "Round closes.",
};

const SEARCH_UPDATED = {
  id: "run-003-search",
  type: SANDBOX_EVENT_TYPES.SEARCH_UPDATED,
  round: 1,
  headline: "Search updated",
  summary: "UCB state updated.",
  search: {
    internalMetrics: {
      familyId: "trust_risk_reduction",
      reward: 0.72,
      positiveUtility: 0.81,
      riskPenalty: 0.09,
      stateAfter: {
        pullCount: 1,
        rewardSum: 0.72,
        meanReward: 0.72,
        lastSelectedRound: 1,
      },
    },
  },
};

const NEXT_ROUND_PARTIAL = {
  id: "run-005-partial",
  type: SANDBOX_EVENT_TYPES.ROUND_STARTED,
  round: 2,
  headline: "Round 2 started",
  summary: "Partial round should not persist.",
};

function makeRunConfig() {
  return {
    source: "live",
    provider: {
      id: "deepseek-compatible",
      baseUrl: "https://api.example/v1",
      apiKey: "session-secret",
      defaultModel: "deepseek-v4pro",
      useBackendDefaults: false,
    },
    models: {
      decision: "reasoner",
      consumers: "consumer",
      synthesizer: "summary",
      critic: "critic",
    },
    product: {
      name: "课堂新品",
      brand: "品牌事实",
      facts: "产品事实",
      goal: "找营销方向",
    },
    personaIds: ["value-pragmatist"],
    scenarioId: "normal",
    actionCategories: ["Product", "Price"],
    search: {
      useUcb: true,
      rounds: 4,
      candidatesPerRound: 1,
      familyIds: ["trust_risk_reduction"],
    },
  };
}

function createMemoryStorage() {
  const values = new Map();
  return {
    getItem(key) {
      return values.has(key) ? values.get(key) : null;
    },
    setItem(key, value) {
      values.set(key, String(value));
    },
  };
}

test("normal archive candidate strips api key and records safe boundary", () => {
  const archive = createArchiveCandidate({
    runId: "class-run",
    runConfig: makeRunConfig(),
    events: [RUN_STARTED, ROUND_STARTED, STRATEGY_PROPOSED, ROUND_COMPLETED],
    createdAt: "2026-05-23T00:00:00.000Z",
  });

  assert.equal(archive.schemaVersion, "marketing-sandbox-archive/v1");
  assert.equal(archive.archiveFormatVersion, ARCHIVE_FORMAT_VERSION);
  assert.equal(archive.sandboxCoreVersion, SANDBOX_CORE_VERSION);
  assert.equal(archive.safeBoundary.completedRoundCount, 1);
  assert.equal(archive.playback.events.at(-1).type, SANDBOX_EVENT_TYPES.ROUND_COMPLETED);
  assert.equal(JSON.stringify(archive).includes("apiKey"), false);
  assert.equal(JSON.stringify(archive).includes("session-secret"), false);
});

test("normal archive candidate records recoverable UCB state from completed rounds", () => {
  const archive = createArchiveCandidate({
    runId: "ucb-run",
    runConfig: makeRunConfig(),
    events: [RUN_STARTED, ROUND_STARTED, STRATEGY_PROPOSED, SEARCH_UPDATED, ROUND_COMPLETED, NEXT_ROUND_PARTIAL],
  });

  assert.equal(archive.safeBoundary.partialEventsDropped, 1);
  assert.equal(archive.searchState.restoresUcbState, true);
  assert.equal(archive.searchState.familyStates.trust_risk_reduction.pullCount, 1);
  assert.equal(archive.searchState.rewardHistory.length, 1);
  assert.equal(archive.searchState.currentBestFamilyId, "trust_risk_reduction");
  assert.equal(archive.searchState.nextRoundIndex, 2);
  assert.equal(archive.resume.canContinue, true);
});

test("boundary safeArchiveEvents drops partial events after last completed round", () => {
  const safe = safeArchiveEvents([
    RUN_STARTED,
    ROUND_STARTED,
    STRATEGY_PROPOSED,
    ROUND_COMPLETED,
    NEXT_ROUND_PARTIAL,
  ]);

  assert.deepEqual(safe.completedRounds, [1]);
  assert.equal(safe.partialEventsDropped, 1);
  assert.equal(safe.events.at(-1).id, ROUND_COMPLETED.id);
});

test("boundary safeArchiveEvents keeps only run start before first completed round", () => {
  const safe = safeArchiveEvents([RUN_STARTED, ROUND_STARTED, STRATEGY_PROPOSED]);

  assert.deepEqual(safe.events.map((event) => event.type), [SANDBOX_EVENT_TYPES.RUN_STARTED]);
  assert.equal(safe.completedRounds.length, 0);
  assert.equal(safe.partialEventsDropped, 2);
});

test("special requestLiveRunStop posts the active run id", async () => {
  const seen = {};
  const result = await requestLiveRunStop("run-stop", {
    endpoint: "/stop-test",
    async fetchImpl(url, options) {
      seen.url = url;
      seen.method = options.method;
      seen.body = JSON.parse(options.body);
      return {
        ok: true,
        async text() {
          return JSON.stringify({ ok: true, status: "stop_requested" });
        },
      };
    },
  });

  assert.equal(result.status, "stop_requested");
  assert.equal(seen.url, "/stop-test");
  assert.equal(seen.method, "POST");
  assert.deepEqual(seen.body, { runId: "run-stop", reason: "user_stop" });
});

test("special local archive store saves lists and loads a browser archive", async () => {
  const storage = createMemoryStorage();
  const archive = createArchiveCandidate({
    runId: "local-run",
    runConfig: makeRunConfig(),
    events: [RUN_STARTED, ROUND_COMPLETED],
  });

  await saveArchive(archive, { preferLocal: true, storage });
  const summaries = await listArchives({ preferLocal: true, storage });
  const restored = await loadArchive(archive.archiveId, { preferLocal: true, storage });

  assert.equal(summaries.length, 1);
  assert.equal(summaries[0].archiveId, archive.archiveId);
  assert.equal(summaries[0].storage, "local");
  assert.equal(restored.playback.events.length, 2);
});

test("special backend save is preferred when the endpoint succeeds", async () => {
  const storage = createMemoryStorage();
  const archive = createArchiveCandidate({
    runId: "backend-run",
    runConfig: makeRunConfig(),
    events: [RUN_STARTED, ROUND_COMPLETED],
  });
  const result = await saveArchive(archive, {
    storage,
    async fetchImpl() {
      return {
        ok: true,
        async text() {
          return JSON.stringify({ ok: true, archive: { archiveId: "server-copy" } });
        },
      };
    },
  });

  assert.equal(result.archive.archiveId, "server-copy");
  assert.equal(result.storage, "backend");
  assert.deepEqual(await listArchives({ preferLocal: true, storage }), []);
});

test("special backend archive list marks summaries as backend", async () => {
  const summaries = await listArchives({
    async fetchImpl() {
      return {
        ok: true,
        async json() {
          return {
            archives: [
              {
                archiveId: "server-archive",
                label: "Server archive",
                completedRoundCount: 2,
                canContinue: true,
              },
            ],
          };
        },
      };
    },
  });

  assert.equal(summaries.length, 1);
  assert.equal(summaries[0].storage, "backend");
});

test("special backend archive list also keeps local classroom archives visible", async () => {
  const storage = createMemoryStorage();
  const localArchive = createArchiveCandidate({
    runId: "local-classroom-run",
    runConfig: makeRunConfig(),
    events: [RUN_STARTED, ROUND_COMPLETED],
  });
  await saveArchive(localArchive, { preferLocal: true, storage });

  const summaries = await listArchives({
    storage,
    async fetchImpl() {
      return {
        ok: true,
        async json() {
          return {
            archives: [
              {
                archiveId: "server-archive",
                label: "Server archive",
                completedRoundCount: 2,
                canContinue: true,
              },
            ],
          };
        },
      };
    },
  });

  assert.deepEqual(
    summaries.map((archive) => [archive.archiveId, archive.storage]),
    [
      ["server-archive", "backend"],
      [localArchive.archiveId, "local"],
    ],
  );
});

test("special backend archive list wins over local archive when ids collide", async () => {
  const storage = createMemoryStorage();
  const localArchive = createArchiveCandidate({
    runId: "server-archive",
    runConfig: makeRunConfig(),
    events: [RUN_STARTED, ROUND_COMPLETED],
  });
  const collidingArchive = { ...localArchive, archiveId: "server-archive" };
  storage.setItem("marketingSandboxArchives", JSON.stringify({ "server-archive": collidingArchive }));

  const summaries = await listArchives({
    storage,
    async fetchImpl() {
      return {
        ok: true,
        async json() {
          return {
            archives: [
              {
                archiveId: "server-archive",
                label: "Server archive",
                completedRoundCount: 2,
                canContinue: true,
              },
            ],
          };
        },
      };
    },
  });

  assert.equal(summaries.length, 1);
  assert.equal(summaries[0].storage, "backend");
  assert.equal(summaries[0].completedRoundCount, 2);
});

test("special archive resume plan posts selected backend archive id", async () => {
  const seen = {};
  const result = await requestArchiveResumePlan("server-archive", {
    endpoint: "/archives",
    async fetchImpl(url, options) {
      seen.url = url;
      seen.method = options.method;
      return {
        ok: true,
        async text() {
          return JSON.stringify({
            ok: true,
            archiveId: "server-archive",
            safeBoundary: { completedRoundCount: 2 },
          });
        },
      };
    },
  });

  assert.equal(seen.url, "/archives/server-archive/resume");
  assert.equal(seen.method, "POST");
  assert.equal(result.storage, "backend");
  assert.equal(result.safeBoundary.completedRoundCount, 2);
});

test("special api disconnect auto archive posts timeout payload", async () => {
  const seen = {};
  const result = await requestApiDisconnectAutoArchive(
    {
      runId: "live-run",
      disconnectedSeconds: 61,
      timeoutSeconds: 60,
      message: "provider timeout",
    },
    {
      runsEndpoint: "/runs",
      async fetchImpl(url, options) {
        seen.url = url;
        seen.method = options.method;
        seen.body = JSON.parse(options.body);
        return {
          ok: true,
          async text() {
            return JSON.stringify({
              ok: true,
              status: "auto_archived",
              archive: { archiveId: "auto-archive" },
            });
          },
        };
      },
    },
  );

  assert.equal(seen.url, "/runs/live-run/api-disconnect-timeout");
  assert.equal(seen.method, "POST");
  assert.deepEqual(seen.body, {
    disconnectedSeconds: 61,
    timeoutSeconds: 60,
    message: "provider timeout",
  });
  assert.equal(result.storage, "backend");
  assert.equal(result.archive.archiveId, "auto-archive");
});

test("counterexample loadArchive rejects missing local archives", async () => {
  await assert.rejects(
    () => loadArchive("missing", { preferLocal: true, storage: createMemoryStorage() }),
    /was not found/,
  );
});

test("counterexample validateArchive rejects plaintext api key fields", () => {
  const archive = createArchiveCandidate({
    runId: "bad-key-run",
    runConfig: makeRunConfig(),
    events: [RUN_STARTED, ROUND_COMPLETED],
  });

  assert.throws(() => validateArchive({ ...archive, apiKey: "plain" }), /API key/);
});

test("counterexample incompatible core archive is replayable but not resumable", () => {
  const archive = createArchiveCandidate({
    runId: "old-core-run",
    runConfig: makeRunConfig(),
    events: [RUN_STARTED, ROUND_STARTED, STRATEGY_PROPOSED, SEARCH_UPDATED, ROUND_COMPLETED],
  });

  const validated = validateArchive({
    ...archive,
    sandboxCoreVersion: "marketing-sandbox-core/v0",
  });

  assert.equal(validated.versionCompatibility.status, "incompatible_core_replay_only");
  assert.equal(validated.resume.canReplay, true);
  assert.equal(validated.resume.canContinue, false);
  assert.match(validated.resume.blockedReason, /version/i);
});

test("limit createRunId keeps unsafe prefixes route-safe", () => {
  const runId = createRunId("课堂 run !@#");

  assert.match(runId, /^run-[a-z0-9]+$/i);
});

test("limit large archive keeps only completed safe prefix", () => {
  const manyEvents = [RUN_STARTED];
  for (let index = 1; index <= 40; index += 1) {
    manyEvents.push({
      ...ROUND_COMPLETED,
      id: `round-${index}`,
      round: index,
    });
  }
  manyEvents.push({
    ...NEXT_ROUND_PARTIAL,
    id: "partial-41",
    round: 41,
  });

  const archive = createArchiveCandidate({
    runId: "large-run",
    runConfig: makeRunConfig(),
    events: manyEvents,
  });

  assert.equal(archive.safeBoundary.completedRoundCount, 40);
  assert.equal(archive.safeBoundary.partialEventsDropped, 1);
  assert.equal(archive.playback.events.at(-1).round, 40);
});

test("boundary disconnect timeout only triggers after tolerated window", () => {
  assert.equal(shouldAutoArchiveDisconnect({ disconnectedMs: 59_999, timeoutMs: 60_000 }), false);
  assert.equal(shouldAutoArchiveDisconnect({ disconnectedMs: 60_000, timeoutMs: 60_000 }), true);
});
