import { normalizeSandboxEvents } from "./event-schema.js";

export const LIVE_EVENT_ENDPOINT = "/api/sandbox/live-events";

export class LiveEventStreamError extends Error {
  constructor(message, options = {}) {
    super(message || "Live event stream returned an error.");
    this.name = "LiveEventStreamError";
    this.httpStatus = options.httpStatus ?? null;
    this.backendStatus = options.backendStatus || "";
    this.issueKind = options.issueKind || "";
  }
}

export async function loadLiveEventStream(runConfig, options = {}) {
  const events = [];
  for await (const event of iterLiveEventStream(runConfig, options)) {
    events.push(event);
  }

  return normalizeSandboxEvents(events);
}

export async function* iterLiveEventStream(runConfig, options = {}) {
  const endpoint = options.endpoint || LIVE_EVENT_ENDPOINT;
  const fetchImpl = options.fetchImpl || globalThis.fetch;
  const requestHeaders = {
    Accept: "text/event-stream, application/x-ndjson, application/json",
    "Content-Type": "application/json",
  };
  const requestBody = options.runId ? { ...runConfig, runId: options.runId } : runConfig;

  if (options.runId) {
    requestHeaders["X-Sandbox-Run-Id"] = options.runId;
  }

  if (typeof fetchImpl !== "function") {
    throw new TypeError("A fetch implementation is required for live event stream.");
  }

  const response = await fetchImpl(endpoint, {
    method: "POST",
    headers: requestHeaders,
    signal: options.signal,
    body: JSON.stringify(requestBody),
  });
  const contentType = response.headers?.get?.("content-type") || "";

  if (!response.ok) {
    const body = await response.text();
    const errorPayload = readErrorPayload(body, contentType);
    throw new LiveEventStreamError(
      errorPayload.message || `Live event stream failed with HTTP ${response.status}.`,
      {
        httpStatus: response.status,
        backendStatus: errorPayload.status,
        issueKind: errorPayload.issueKind,
      },
    );
  }

  if (canReadIncrementally(response, contentType)) {
    yield* iterIncrementalEvents(response.body, contentType);
    return;
  }

  const body = await response.text();
  for (const event of parseLiveEventStreamPayload(body, contentType)) {
    yield event;
  }
}

export function parseLiveEventStreamPayload(body, contentType = "") {
  const text = requireTextBody(body);
  const normalizedType = contentType.toLowerCase();

  if (normalizedType.includes("json") && !normalizedType.includes("ndjson")) {
    return eventsFromJsonPayload(JSON.parse(text));
  }

  if (normalizedType.includes("event-stream") || text.includes("\ndata:") || text.startsWith("data:")) {
    return normalizeSandboxEvents(parseSseEvents(text));
  }

  if (normalizedType.includes("ndjson")) {
    return normalizeSandboxEvents(parseJsonLineEvents(text));
  }

  try {
    return eventsFromJsonPayload(JSON.parse(text));
  } catch {
    if (text.includes("data:")) {
      return normalizeSandboxEvents(parseSseEvents(text));
    }

    return normalizeSandboxEvents(parseJsonLineEvents(text));
  }
}

export function eventsFromJsonPayload(payload) {
  if (Array.isArray(payload)) {
    return normalizeSandboxEvents(payload);
  }

  if (!payload || typeof payload !== "object") {
    throw new TypeError("Live event response must be an object or event array.");
  }

  if (payload.ok === false) {
    throw new LiveEventStreamError(payload.message, {
      backendStatus: payload.status,
      issueKind: payload.issueKind,
    });
  }

  return normalizeSandboxEvents(payload.events);
}

export function parseSseEvents(body) {
  const events = [];
  for (const block of requireTextBody(body).split(/\r?\n\r?\n/)) {
    const dataLines = block
      .split(/\r?\n/)
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trimStart());
    if (dataLines.length === 0) {
      continue;
    }

    const data = dataLines.join("\n").trim();
    if (!data || data === "[DONE]") {
      continue;
    }

    events.push(JSON.parse(data));
  }

  return events;
}

export function parseJsonLineEvents(body) {
  return requireTextBody(body)
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => JSON.parse(line));
}

function canReadIncrementally(response, contentType) {
  const normalizedType = contentType.toLowerCase();
  return (
    response.body &&
    typeof response.body.getReader === "function" &&
    (normalizedType.includes("event-stream") || normalizedType.includes("ndjson"))
  );
}

async function* iterIncrementalEvents(body, contentType) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  const isSse = contentType.toLowerCase().includes("event-stream");
  let buffer = "";

  for (;;) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const parsed = extractBufferedEvents(buffer, { isSse, flush: false });
    buffer = parsed.remainder;
    for (const event of parsed.events) {
      yield normalizeSandboxEvents([event])[0];
    }
  }

  buffer += decoder.decode();
  const parsed = extractBufferedEvents(buffer, { isSse, flush: true });
  for (const event of parsed.events) {
    yield normalizeSandboxEvents([event])[0];
  }
}

function extractBufferedEvents(buffer, { isSse, flush }) {
  return isSse ? extractSseBuffer(buffer, flush) : extractJsonLineBuffer(buffer, flush);
}

function extractSseBuffer(buffer, flush) {
  const parts = buffer.split(/\r?\n\r?\n/);
  const completeBlocks = flush ? parts : parts.slice(0, -1);
  const remainder = flush ? "" : parts.at(-1) || "";
  const events = [];

  for (const block of completeBlocks) {
    const dataLines = block
      .split(/\r?\n/)
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trimStart());
    const data = dataLines.join("\n").trim();
    if (data && data !== "[DONE]") {
      events.push(JSON.parse(data));
    }
  }

  return { events, remainder };
}

function extractJsonLineBuffer(buffer, flush) {
  const lines = buffer.split(/\r?\n/);
  const completeLines = flush ? lines : lines.slice(0, -1);
  const remainder = flush ? "" : lines.at(-1) || "";
  const events = completeLines
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => JSON.parse(line));

  return { events, remainder };
}

function readErrorPayload(body, contentType) {
  if (!body) {
    return {};
  }

  if (contentType.toLowerCase().includes("json")) {
    try {
      const parsed = JSON.parse(body);
      return parsed && typeof parsed === "object"
        ? {
            message: typeof parsed.message === "string" ? parsed.message : "",
            status: typeof parsed.status === "string" ? parsed.status : "",
            issueKind: typeof parsed.issueKind === "string" ? parsed.issueKind : "",
          }
        : {};
    } catch {
      return {};
    }
  }

  return {
    message: body.trim().slice(0, 300),
  };
}

function requireTextBody(body) {
  if (typeof body !== "string" || body.trim() === "") {
    throw new TypeError("Live event stream response body must be non-empty text.");
  }

  return body.trim();
}
