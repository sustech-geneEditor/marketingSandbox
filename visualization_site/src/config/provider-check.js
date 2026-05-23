export const PROVIDER_CHECK_ENDPOINT = "/api/sandbox/provider-check";

export const PROVIDER_CHECK_STATUS = Object.freeze({
  UNCHECKED: "unchecked",
  CHECKING: "checking",
  CONNECTED: "connected",
  FAILED: "failed",
});

export function createProviderCheckState(overrides = {}) {
  return {
    status: PROVIDER_CHECK_STATUS.UNCHECKED,
    ok: false,
    message: "还没有做真实 provider 检测。",
    modelStatus: "",
    checkedAt: "",
    ...overrides,
  };
}

export async function requestProviderCheck(runConfig, options = {}) {
  const fetchImpl = options.fetchImpl || globalThis.fetch;
  if (typeof fetchImpl !== "function") {
    return createProviderCheckState({
      status: PROVIDER_CHECK_STATUS.FAILED,
      message: "当前环境没有可用的 fetch，无法检测 provider。",
    });
  }

  const secretValues = providerSecretCandidates(runConfig);
  try {
    const response = await fetchImpl(options.endpoint || PROVIDER_CHECK_ENDPOINT, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        provider: runConfig.provider,
        models: runConfig.models,
      }),
    });
    const payload = await readJsonResponse(response);
    if (!response.ok || payload.ok === false) {
      return createProviderCheckState({
        status: PROVIDER_CHECK_STATUS.FAILED,
        ok: false,
        message: redactText(
          payload.message || `Provider check failed with HTTP ${response.status}.`,
          secretValues,
        ),
        modelStatus: payload.modelStatus || "",
        checkedAt: new Date().toISOString(),
      });
    }

    return createProviderCheckState({
      status: PROVIDER_CHECK_STATUS.CONNECTED,
      ok: true,
      message: payload.modelCheck?.message || payload.message || "Provider 检测通过。",
      modelStatus: payload.modelCheck?.modelStatus || payload.modelStatus || "callable",
      checkedAt: new Date().toISOString(),
    });
  } catch (error) {
    return createProviderCheckState({
      status: PROVIDER_CHECK_STATUS.FAILED,
      ok: false,
      message: redactText(error instanceof Error ? error.message : String(error), secretValues),
      checkedAt: new Date().toISOString(),
    });
  }
}

export function providerCheckAllowsLiveRun(state) {
  return state?.status === PROVIDER_CHECK_STATUS.CONNECTED && state.ok === true;
}

async function readJsonResponse(response) {
  const body = await response.text();
  if (!body) {
    return {};
  }
  try {
    return JSON.parse(body);
  } catch {
    return { message: body.trim().slice(0, 300) };
  }
}

function providerSecretCandidates(runConfig) {
  const key = runConfig?.provider?.apiKey;
  return typeof key === "string" && key.trim() ? [key.trim()] : [];
}

function redactText(text, secretValues) {
  return secretValues.reduce((safeText, secret) => {
    if (!secret) {
      return safeText;
    }
    return safeText.replaceAll(secret, "[redacted]");
  }, String(text || ""));
}
