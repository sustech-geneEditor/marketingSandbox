export const LIVE_RUN_ISSUE_KINDS = Object.freeze({
  CONTRACT: "contract_error",
  RUNTIME: "runtime_error",
  REQUEST: "invalid_request",
});

const CONTRACT_HINTS = [
  "contract",
  "outputcontract",
  "sandbox event",
  "schema",
  "missing text field",
  "unknown type",
  "越界",
  "契约",
];

export function createLiveRunIssue(error, options = {}) {
  const message = redactText(messageFromError(error), options.secretValues || []);
  const issueKind = issueKindFromError(error, message);

  if (issueKind === LIVE_RUN_ISSUE_KINDS.CONTRACT) {
    return {
      kind: issueKind,
      title: "输出契约被拦住",
      explanation: "模型输出或事件形状越过了沙盘契约，页面已停在最后一条校验通过的事件，不会把它误当成正常消费者反馈。",
      message,
    };
  }

  if (issueKind === LIVE_RUN_ISSUE_KINDS.REQUEST) {
    return {
      kind: issueKind,
      title: "真实运行还没准备好",
      explanation: "请求配置没有通过 live 运行边界。补齐配置后重新开始，不需要把这次失败写进搜索结论。",
      message,
    };
  }

  return {
    kind: LIVE_RUN_ISSUE_KINDS.RUNTIME,
    title: "真实运行中断",
    explanation: "模型调用、网络连接或本地 runner 在运行时失败。页面已暂停，当前画面只保留已收到并通过校验的事件。",
    message,
  };
}

function issueKindFromError(error, message) {
  const explicitKind = error && typeof error === "object" ? error.issueKind : "";
  if (Object.values(LIVE_RUN_ISSUE_KINDS).includes(explicitKind)) {
    return explicitKind;
  }

  const backendStatus = error && typeof error === "object" ? error.backendStatus : "";
  if (backendStatus === "invalid_request") {
    return LIVE_RUN_ISSUE_KINDS.REQUEST;
  }

  const normalized = `${error?.name || ""} ${message}`.toLowerCase();
  return CONTRACT_HINTS.some((hint) => normalized.includes(hint))
    ? LIVE_RUN_ISSUE_KINDS.CONTRACT
    : LIVE_RUN_ISSUE_KINDS.RUNTIME;
}

function messageFromError(error) {
  if (error instanceof Error && error.message) {
    return error.message;
  }

  if (typeof error === "string" && error.trim()) {
    return error;
  }

  return "未收到可展示的错误细节。";
}

function redactText(text, secretValues) {
  return secretValues.reduce((safeText, secret) => {
    if (typeof secret !== "string" || !secret) {
      return safeText;
    }
    return safeText.replaceAll(secret, "[redacted]");
  }, text);
}
