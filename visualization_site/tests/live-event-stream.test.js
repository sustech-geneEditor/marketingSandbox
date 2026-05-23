import assert from "node:assert/strict";
import test from "node:test";

import { SANDBOX_EVENT_TYPES } from "../src/events/event-schema.js";
import {
  eventsFromJsonPayload,
  iterLiveEventStream,
  LiveEventStreamError,
  loadLiveEventStream,
  parseJsonLineEvents,
  parseLiveEventStreamPayload,
  parseSseEvents,
} from "../src/events/live-event-stream.js";
import { createPlaybackSnapshot } from "../src/events/playback-snapshot.js";

const EVENT_A = {
  id: "live-0001-run_started",
  type: SANDBOX_EVENT_TYPES.RUN_STARTED,
  round: 0,
  actorId: "decision",
  actorRole: "decision",
  headline: "Run started",
  summary: "Live run starts.",
};

const EVENT_B = {
  id: "live-0002-strategy_proposed",
  type: SANDBOX_EVENT_TYPES.STRATEGY_PROPOSED,
  round: 1,
  actorId: "decision",
  actorRole: "decision",
  headline: "Strategy proposed",
  summary: "Decision proposes.",
  strategy: {
    name: "Trust proof",
    familyId: "trust_risk_reduction",
    intent: "Test trust proof.",
    actions: [{ category: "Product", note: "Show proof." }],
  },
};

const EVENT_C = {
  id: "live-0003-consumer_feedback_ready",
  type: SANDBOX_EVENT_TYPES.CONSUMER_FEEDBACK_READY,
  round: 1,
  actorId: "consumer-value-pragmatist",
  actorRole: "consumer",
  actor_name: "Value Pragmatist",
  headline: "Consumer responded",
  summary: "Interested but cautious.",
  feedback: {
    firstImpression: "Clear enough.",
    repeat: "Conditional.",
  },
};

const EVENT_D = {
  id: "live-0004-search_updated",
  type: SANDBOX_EVENT_TYPES.SEARCH_UPDATED,
  round: 1,
  actorId: "decision",
  actorRole: "decision",
  headline: "Search updated",
  summary: "Reward recorded.",
  search: {
    note: "Trust proof helped.",
    internalMetrics: {
      reward: 0.72,
      metricBoundary: "Internal search metric, not market outcomes.",
    },
  },
};

const EVENT_E = {
  id: "live-0005-round_completed",
  type: SANDBOX_EVENT_TYPES.ROUND_COMPLETED,
  round: 1,
  actorId: "decision",
  actorRole: "decision",
  headline: "Round done",
  summary: "Round closes.",
};

function jsonResponse(body, ok = true, status = 200, contentType = "application/json") {
  return {
    ok,
    status,
    headers: {
      get(name) {
        return name.toLowerCase() === "content-type" ? contentType : "";
      },
    },
    async text() {
      return body;
    },
  };
}

function streamResponse(chunks, contentType) {
  const encoder = new TextEncoder();
  return {
    ok: true,
    status: 200,
    headers: {
      get(name) {
        return name.toLowerCase() === "content-type" ? contentType : "";
      },
    },
    body: new ReadableStream({
      start(controller) {
        for (const chunk of chunks) {
          controller.enqueue(encoder.encode(chunk));
        }
        controller.close();
      },
    }),
    async text() {
      return chunks.join("");
    },
  };
}

test("json response object returns normalized live events", () => {
  const events = parseLiveEventStreamPayload(
    JSON.stringify({ ok: true, events: [EVENT_A, EVENT_B] }),
    "application/json",
  );

  assert.deepEqual(events.map((event) => event.id), [EVENT_A.id, EVENT_B.id]);
});

test("plain event array payload is accepted for simple route handlers", () => {
  const events = eventsFromJsonPayload([EVENT_A, EVENT_B]);

  assert.equal(events.length, 2);
});

test("jsonl live stream chunks parse event by event", () => {
  const body = `${JSON.stringify(EVENT_A)}\n${JSON.stringify(EVENT_B)}\n`;

  assert.deepEqual(parseJsonLineEvents(body).map((event) => event.type), [
    SANDBOX_EVENT_TYPES.RUN_STARTED,
    SANDBOX_EVENT_TYPES.STRATEGY_PROPOSED,
  ]);
  assert.equal(parseLiveEventStreamPayload(body, "application/x-ndjson").length, 2);
});

test("sse chunks parse data lines and ignore done marker", () => {
  const body = [
    `id: ${EVENT_A.id}`,
    "event: run_started",
    `data: ${JSON.stringify(EVENT_A)}`,
    "",
    "event: done",
    "data: [DONE]",
    "",
  ].join("\n");

  assert.deepEqual(parseSseEvents(body).map((event) => event.id), [EVENT_A.id]);
  assert.equal(parseLiveEventStreamPayload(body, "text/event-stream")[0].type, "run_started");
});

test("loadLiveEventStream posts config and reads response events", async () => {
  const seen = {};
  const controller = new AbortController();
  const events = await loadLiveEventStream(
    { source: "live", provider: { apiKey: "session-secret" } },
    {
      endpoint: "/test-live",
      runId: "run-abc",
      signal: controller.signal,
      async fetchImpl(url, options) {
        seen.url = url;
        seen.method = options.method;
        seen.headers = options.headers;
        seen.signal = options.signal;
        seen.body = JSON.parse(options.body);
        return jsonResponse(JSON.stringify({ ok: true, events: [EVENT_A] }));
      },
    },
  );

  assert.equal(seen.url, "/test-live");
  assert.equal(seen.method, "POST");
  assert.equal(seen.headers["X-Sandbox-Run-Id"], "run-abc");
  assert.equal(seen.signal, controller.signal);
  assert.equal(seen.body.runId, "run-abc");
  assert.equal(seen.body.provider.apiKey, "session-secret");
  assert.equal(events[0].id, EVENT_A.id);
});

test("iterLiveEventStream yields ndjson chunks incrementally", async () => {
  const seen = [];

  for await (const event of iterLiveEventStream(
    { source: "live" },
    {
      fetchImpl: async () =>
        streamResponse(
          [`${JSON.stringify(EVENT_A)}\n`, `${JSON.stringify(EVENT_B)}\n`],
          "application/x-ndjson",
        ),
    },
  )) {
    seen.push(event.id);
  }

  assert.deepEqual(seen, [EVENT_A.id, EVENT_B.id]);
});

test("loadLiveEventStream surfaces backend error messages", async () => {
  await assert.rejects(
    () =>
      loadLiveEventStream(
        { source: "live" },
        {
          fetchImpl: async () =>
            jsonResponse(
              JSON.stringify({ ok: false, message: "Provider unavailable." }),
              false,
              502,
            ),
        },
      ),
    /Provider unavailable/,
  );
});

test("backend error metadata keeps contract errors distinguishable for the page", async () => {
  await assert.rejects(
    () =>
      loadLiveEventStream(
        { source: "live" },
        {
          fetchImpl: async () =>
            jsonResponse(
              JSON.stringify({
                ok: false,
                status: "run_failed",
                issueKind: "contract_error",
                message: "Decision output contract rejected.",
              }),
              false,
              500,
            ),
        },
      ),
    (error) => {
      assert.ok(error instanceof LiveEventStreamError);
      assert.equal(error.httpStatus, 500);
      assert.equal(error.backendStatus, "run_failed");
      assert.equal(error.issueKind, "contract_error");
      return true;
    },
  );
});

test("empty live response is rejected before playback starts", () => {
  assert.throws(() => parseLiveEventStreamPayload("", "application/json"), /non-empty/);
});

test("invalid event shape is rejected by the shared schema", () => {
  assert.throws(
    () => eventsFromJsonPayload({ ok: true, events: [{ id: "bad" }] }),
    /missing text field/,
  );
});

test("playback snapshot maps live events back to panels", () => {
  const snapshot = createPlaybackSnapshot([EVENT_A, EVENT_B, EVENT_C, EVENT_D, EVENT_E], 4);

  assert.equal(snapshot.currentEvent.id, EVENT_E.id);
  assert.equal(snapshot.strategy.name, "Trust proof");
  assert.equal(snapshot.search.internalMetrics.reward, 0.72);
  assert.equal(snapshot.feedbackEvent.actor_name, "Value Pragmatist");
  assert.deepEqual(snapshot.completedRounds, [1]);
});

test("idle playback snapshot keeps panels empty without crashing", () => {
  const snapshot = createPlaybackSnapshot([EVENT_A], -1);

  assert.equal(snapshot.currentEvent, null);
  assert.equal(snapshot.strategy, null);
  assert.deepEqual(snapshot.visitedEvents, []);
});

test("large live snapshot keeps completed round order stable", () => {
  const manyRounds = Array.from({ length: 24 }, (_, index) => ({
    ...EVENT_E,
    id: `live-round-${index + 1}`,
    round: index + 1,
  }));
  const snapshot = createPlaybackSnapshot(manyRounds, manyRounds.length - 1);

  assert.equal(snapshot.completedRounds.length, 24);
  assert.equal(snapshot.completedRounds.at(-1), 24);
});
