import assert from "node:assert/strict";
import test from "node:test";

import {
  createLiveRunIssue,
  LIVE_RUN_ISSUE_KINDS,
} from "../src/events/live-run-issue.js";
import { LiveEventStreamError } from "../src/events/live-event-stream.js";

test("backend contract errors become a paused contract explanation", () => {
  const error = new LiveEventStreamError("Consumer output contract rejected.", {
    backendStatus: "run_failed",
    issueKind: LIVE_RUN_ISSUE_KINDS.CONTRACT,
  });

  const issue = createLiveRunIssue(error);

  assert.equal(issue.kind, LIVE_RUN_ISSUE_KINDS.CONTRACT);
  assert.match(issue.title, /契约/);
  assert.match(issue.explanation, /最后一条校验通过/);
});

test("runtime issue message redacts the current session key before the page shows it", () => {
  const issue = createLiveRunIssue(
    new Error("provider failed for secret-session-key"),
    { secretValues: ["secret-session-key"] },
  );

  assert.equal(issue.kind, LIVE_RUN_ISSUE_KINDS.RUNTIME);
  assert.doesNotMatch(issue.message, /secret-session-key/);
  assert.match(issue.message, /\[redacted\]/);
});

test("invalid request status explains setup failure instead of a consumer response", () => {
  const issue = createLiveRunIssue(
    new LiveEventStreamError("live session needed", {
      backendStatus: "invalid_request",
    }),
  );

  assert.equal(issue.kind, LIVE_RUN_ISSUE_KINDS.REQUEST);
  assert.match(issue.explanation, /请求配置/);
});
