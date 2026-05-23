import assert from "node:assert/strict";
import test from "node:test";

import {
  CLASSROOM_DEMO_ARCHIVE_ID,
  createClassroomDemoArchive,
  createClassroomDemoConfig,
} from "../src/demo/classroom-demo-pack.js";
import { RUN_SOURCES } from "../src/config/run-config.js";
import { SANDBOX_EVENT_TYPES } from "../src/events/event-schema.js";

test("normal classroom pack keeps a full fixture config for a ten-person demo", () => {
  const config = createClassroomDemoConfig();

  assert.equal(config.source, RUN_SOURCES.FIXTURE);
  assert.equal(config.product.name, "轻行补给包");
  assert.equal(config.personaIds.length, 10);
  assert.equal(config.scenarioId, "competitor-pressure");
  assert.equal(config.search.familyIds.length, 3);
});

test("boundary classroom archive is stable safe and credential free", () => {
  const archive = createClassroomDemoArchive();
  const serialized = JSON.stringify(archive);

  assert.equal(archive.archiveId, CLASSROOM_DEMO_ARCHIVE_ID);
  assert.equal(archive.safeBoundary.completedRoundCount, 1);
  assert.equal(archive.playback.events.at(-1).type, SANDBOX_EVENT_TYPES.RUN_COMPLETED);
  assert.doesNotMatch(serialized, /apiKey|Authorization|session key/i);
});

test("special classroom archive keeps visible role boundaries and internal metric wording", () => {
  const archive = createClassroomDemoArchive();
  const eventTypes = archive.playback.events.map((event) => event.type);
  const serialized = JSON.stringify(archive);

  assert.ok(eventTypes.includes(SANDBOX_EVENT_TYPES.STRATEGY_PROPOSED));
  assert.ok(eventTypes.includes(SANDBOX_EVENT_TYPES.CONSUMER_FEEDBACK_READY));
  assert.ok(eventTypes.includes(SANDBOX_EVENT_TYPES.FEEDBACK_SUMMARY_READY));
  assert.ok(eventTypes.includes(SANDBOX_EVENT_TYPES.CRITIQUE_READY));
  assert.match(serialized, /不是购买率|not market forecasts/);
});
