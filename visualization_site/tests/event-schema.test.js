import assert from "node:assert/strict";
import test from "node:test";

import {
  SANDBOX_EVENT_CONTRACT,
  SANDBOX_EVENT_CONTRACT_VERSION,
  SANDBOX_EVENT_TYPES,
  eventContractFor,
  validateSandboxEvent,
} from "../src/events/event-schema.js";

test("normal event contract covers every sandbox event type", () => {
  for (const type of Object.values(SANDBOX_EVENT_TYPES)) {
    const contract = eventContractFor(type);
    assert.ok(contract, `${type} should have a contract`);
    assert.ok(contract.category);
    assert.ok(contract.purpose);
    assert.ok(contract.requiredFields.includes("id"));
    assert.ok(contract.requiredFields.includes("type"));
  }

  assert.equal(Object.keys(SANDBOX_EVENT_CONTRACT).length, Object.keys(SANDBOX_EVENT_TYPES).length);
});

test("counterexample event contract rejects unsupported contract versions", () => {
  assert.throws(
    () =>
      validateSandboxEvent({
        id: "event-1",
        type: SANDBOX_EVENT_TYPES.RUN_STARTED,
        round: 0,
        headline: "Run",
        summary: "Starts.",
        contractVersion: "marketing-sandbox-web-events/v0",
      }),
    /unsupported contract version/,
  );
});

test("boundary event contract accepts the current version", () => {
  const event = validateSandboxEvent({
    id: "event-2",
    type: SANDBOX_EVENT_TYPES.RUN_STARTED,
    round: 0,
    headline: "Run",
    summary: "Starts.",
    contractVersion: SANDBOX_EVENT_CONTRACT_VERSION,
  });

  assert.equal(event.contractVersion, SANDBOX_EVENT_CONTRACT_VERSION);
});
