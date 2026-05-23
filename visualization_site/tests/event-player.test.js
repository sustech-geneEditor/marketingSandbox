import assert from "node:assert/strict";
import test from "node:test";

import {
  createPlaybackState,
  currentPlaybackEvent,
  PLAYBACK_STATUS,
  reducePlayback,
  visitedPlaybackEvents,
} from "../src/events/event-player.js";
import { SANDBOX_EVENT_TYPES } from "../src/events/event-schema.js";
import { SAMPLE_RUN_EVENTS } from "../src/events/sample-run.js";

const EVENTS = [
  {
    id: "run",
    type: SANDBOX_EVENT_TYPES.RUN_STARTED,
    round: 0,
    headline: "Run",
    summary: "Run begins.",
  },
  {
    id: "strategy",
    type: SANDBOX_EVENT_TYPES.STRATEGY_PROPOSED,
    round: 1,
    headline: "Strategy",
    summary: "Decision proposes a strategy.",
  },
];

test("step exposes the next sandbox event without skipping history", () => {
  let state = createPlaybackState(EVENTS);

  assert.equal(currentPlaybackEvent(state), null);
  state = reducePlayback(state, { type: "step" });

  assert.equal(state.status, PLAYBACK_STATUS.PAUSED);
  assert.equal(currentPlaybackEvent(state).id, "run");
  assert.deepEqual(visitedPlaybackEvents(state).map((event) => event.id), ["run"]);
});

test("playing through the final event marks the playback complete", () => {
  let state = createPlaybackState(EVENTS);
  state = reducePlayback(state, { type: "play" });
  state = reducePlayback(state, { type: "step" });
  state = reducePlayback(state, { type: "step" });

  assert.equal(state.status, PLAYBACK_STATUS.COMPLETE);
  assert.equal(currentPlaybackEvent(state).id, "strategy");
});

test("duplicate fixture ids are rejected before playback begins", () => {
  assert.throws(
    () => createPlaybackState([EVENTS[0], EVENTS[0]]),
    /duplicated/,
  );
});

test("sample search events expose labeled internal UCB and reward metrics", () => {
  const familyEvent = SAMPLE_RUN_EVENTS.find(
    (event) => event.type === SANDBOX_EVENT_TYPES.FAMILY_SELECTED,
  );
  const searchEvent = SAMPLE_RUN_EVENTS.find(
    (event) => event.type === SANDBOX_EVENT_TYPES.SEARCH_UPDATED,
  );

  assert.equal(familyEvent.internalSearch.ucbScore.display, "cold start infinity");
  assert.match(familyEvent.internalSearch.metricBoundary, /不是购买率/);
  assert.equal(searchEvent.search.internalMetrics.reward, 0.62);
  assert.equal(searchEvent.search.internalMetrics.stateAfter.meanReward, 0.62);
  assert.match(searchEvent.search.internalMetrics.metricBoundary, /不代表真实市场结果/);
});
