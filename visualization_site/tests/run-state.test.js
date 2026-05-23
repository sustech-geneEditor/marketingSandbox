import assert from "node:assert/strict";
import test from "node:test";

import {
  RUN_STATUSES,
  canStopRun,
  isRunBusyStatus,
  isRunTerminalStatus,
  normalizeRunStatus,
} from "../src/events/run-state.js";

test("normal run state machine exposes the expected canonical states", () => {
  assert.deepEqual(Object.values(RUN_STATUSES), [
    "idle",
    "checking_provider",
    "starting",
    "running",
    "stop_requested",
    "stopped_safe",
    "archived",
    "resuming",
    "completed",
    "failed",
  ]);
});

test("boundary run state helpers classify busy and stoppable states", () => {
  assert.equal(isRunBusyStatus(RUN_STATUSES.CHECKING_PROVIDER), true);
  assert.equal(isRunBusyStatus(RUN_STATUSES.RUNNING), true);
  assert.equal(isRunBusyStatus(RUN_STATUSES.STOP_REQUESTED), true);
  assert.equal(canStopRun(RUN_STATUSES.STARTING), true);
  assert.equal(canStopRun(RUN_STATUSES.RUNNING), true);
  assert.equal(canStopRun(RUN_STATUSES.STOP_REQUESTED), false);
});

test("counterexample unknown run states normalize to idle", () => {
  assert.equal(normalizeRunStatus("loading"), RUN_STATUSES.IDLE);
  assert.equal(isRunBusyStatus("loading"), false);
  assert.equal(isRunTerminalStatus("ready"), false);
});

test("special terminal states include safe stop archive completion and failure", () => {
  assert.equal(isRunTerminalStatus(RUN_STATUSES.STOPPED_SAFE), true);
  assert.equal(isRunTerminalStatus(RUN_STATUSES.ARCHIVED), true);
  assert.equal(isRunTerminalStatus(RUN_STATUSES.COMPLETED), true);
  assert.equal(isRunTerminalStatus(RUN_STATUSES.FAILED), true);
});
