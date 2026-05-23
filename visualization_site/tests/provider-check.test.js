import assert from "node:assert/strict";
import test from "node:test";

import { createRunConfig, RUN_SOURCES } from "../src/config/run-config.js";
import {
  createProviderCheckState,
  PROVIDER_CHECK_STATUS,
  providerCheckAllowsLiveRun,
  requestProviderCheck,
} from "../src/config/provider-check.js";

function makeLiveConfig() {
  const config = createRunConfig();
  config.source = RUN_SOURCES.LIVE;
  config.provider.baseUrl = "https://provider.example/v1";
  config.provider.apiKey = "session-secret";
  config.provider.defaultModel = "tiny-model";
  return config;
}

test("normal provider check posts provider and model routes", async () => {
  const seen = {};
  const result = await requestProviderCheck(makeLiveConfig(), {
    endpoint: "/provider-check-test",
    async fetchImpl(url, options) {
      seen.url = url;
      seen.method = options.method;
      seen.body = JSON.parse(options.body);
      return {
        ok: true,
        async text() {
          return JSON.stringify({
            ok: true,
            message: "connected",
            modelCheck: { modelStatus: "callable", message: "model ok" },
          });
        },
      };
    },
  });

  assert.equal(result.status, PROVIDER_CHECK_STATUS.CONNECTED);
  assert.equal(result.ok, true);
  assert.equal(providerCheckAllowsLiveRun(result), true);
  assert.equal(seen.url, "/provider-check-test");
  assert.equal(seen.method, "POST");
  assert.equal(seen.body.provider.defaultModel, "tiny-model");
});

test("boundary missing fetch returns failed state", async () => {
  const result = await requestProviderCheck(makeLiveConfig(), { fetchImpl: null });

  assert.equal(result.status, PROVIDER_CHECK_STATUS.FAILED);
  assert.equal(providerCheckAllowsLiveRun(result), false);
});

test("special backend provider failure keeps short message", async () => {
  const result = await requestProviderCheck(makeLiveConfig(), {
    async fetchImpl() {
      return {
        ok: false,
        status: 502,
        async text() {
          return JSON.stringify({ ok: false, message: "model not callable", modelStatus: "not_callable" });
        },
      };
    },
  });

  assert.equal(result.status, PROVIDER_CHECK_STATUS.FAILED);
  assert.equal(result.modelStatus, "not_callable");
  assert.match(result.message, /model not callable/);
});

test("special provider success can use top-level backend message", async () => {
  const result = await requestProviderCheck(makeLiveConfig(), {
    async fetchImpl() {
      return {
        ok: true,
        async text() {
          return JSON.stringify({ ok: true, message: "provider route ok", modelStatus: "callable" });
        },
      };
    },
  });

  assert.equal(result.status, PROVIDER_CHECK_STATUS.CONNECTED);
  assert.equal(result.message, "provider route ok");
  assert.equal(result.modelStatus, "callable");
});

test("boundary plain-text backend failure is converted into failed state", async () => {
  const result = await requestProviderCheck(makeLiveConfig(), {
    async fetchImpl() {
      return {
        ok: false,
        status: 500,
        async text() {
          return "provider gateway unavailable";
        },
      };
    },
  });

  assert.equal(result.status, PROVIDER_CHECK_STATUS.FAILED);
  assert.match(result.message, /provider gateway unavailable/);
});

test("counterexample http failure message redacts session key", async () => {
  const result = await requestProviderCheck(makeLiveConfig(), {
    async fetchImpl() {
      return {
        ok: false,
        status: 401,
        async text() {
          return JSON.stringify({ ok: false, message: "bad key session-secret" });
        },
      };
    },
  });

  assert.equal(result.status, PROVIDER_CHECK_STATUS.FAILED);
  assert.doesNotMatch(result.message, /session-secret/);
});

test("counterexample thrown secret-bearing error is redacted", async () => {
  const result = await requestProviderCheck(makeLiveConfig(), {
    async fetchImpl() {
      throw new Error("transport leaked session-secret");
    },
  });

  assert.equal(result.status, PROVIDER_CHECK_STATUS.FAILED);
  assert.doesNotMatch(result.message, /session-secret/);
  assert.match(result.message, /\[redacted\]/);
});

test("limit live run is allowed only after connected ok state", () => {
  assert.equal(providerCheckAllowsLiveRun(createProviderCheckState()), false);
  assert.equal(
    providerCheckAllowsLiveRun(createProviderCheckState({ status: PROVIDER_CHECK_STATUS.CONNECTED, ok: false })),
    false,
  );
  assert.equal(
    providerCheckAllowsLiveRun(createProviderCheckState({ status: PROVIDER_CHECK_STATUS.CONNECTED, ok: true })),
    true,
  );
});
