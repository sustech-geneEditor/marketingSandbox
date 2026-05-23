import assert from "node:assert/strict";
import test from "node:test";

import {
  buildRunConfigPreview,
  createRunConfig,
  PERSONA_PRESETS,
  RUN_SOURCES,
  validateRunConfig,
} from "../src/config/run-config.js";

test("fixture config is ready before any live provider fields are filled", () => {
  const config = createRunConfig();
  const result = validateRunConfig(config);

  assert.equal(result.ready, true);
  assert.deepEqual(result.errors, []);
  assert.match(result.notices[0], /示例回放/);
  assert.equal(PERSONA_PRESETS.length, 10);
  assert.equal(config.personaIds.length, 10);
});

test("live config reports missing provider and sandbox preparation fields", () => {
  const config = createRunConfig();
  config.source = RUN_SOURCES.LIVE;
  config.personaIds = [];
  config.actionCategories = [];
  config.product.name = "";
  config.product.facts = "";
  config.product.goal = "";
  config.search.familyIds = [];

  const result = validateRunConfig(config);

  assert.equal(result.ready, false);
  assert.match(result.errors.join(" "), /Base URL/);
  assert.match(result.errors.join(" "), /API Key/);
  assert.match(result.errors.join(" "), /默认模型/);
  assert.match(result.errors.join(" "), /产品名/);
  assert.match(result.errors.join(" "), /人群卡/);
  assert.match(result.errors.join(" "), /动作集/);
  assert.match(result.errors.join(" "), /family/);
});

test("preview never echoes the plaintext session key", () => {
  const config = createRunConfig();
  config.source = RUN_SOURCES.LIVE;
  config.provider.baseUrl = "https://provider.example/v1";
  config.provider.apiKey = "secret-session-key";
  config.provider.defaultModel = "reasoning-model";

  const preview = buildRunConfigPreview(config);
  const serializedPreview = JSON.stringify(preview);

  assert.equal(validateRunConfig(config).ready, true);
  assert.doesNotMatch(serializedPreview, /secret-session-key/);
  assert.match(preview.credentialLabel, /session/);
});
