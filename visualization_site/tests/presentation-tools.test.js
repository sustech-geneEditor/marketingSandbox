import assert from "node:assert/strict";
import test from "node:test";

import {
  buildRunSummaryMarkdown,
  collectStrategySnapshots,
  createStrategyComparison,
  PLAYBACK_PACES,
  playbackPaceFromId,
} from "../src/events/presentation-tools.js";
import { SANDBOX_EVENT_TYPES } from "../src/events/event-schema.js";
import { SAMPLE_RUN_EVENTS } from "../src/events/sample-run.js";

test("comparison snapshots keep round strategy family reactions and search reward together", () => {
  const snapshots = collectStrategySnapshots(SAMPLE_RUN_EVENTS);

  assert.equal(snapshots.length, 2);
  assert.equal(snapshots[0].round, 1);
  assert.equal(snapshots[0].family.id, "trial_value_entry");
  assert.equal(snapshots[0].consumerFeedback.length, 2);
  assert.equal(snapshots[0].critique.mainRisk, "过度依赖首购激励。");
  assert.equal(snapshots[0].search.internalMetrics.reward, 0.62);
});

test("comparison lists shared persona reactions when the same consumer answers two strategies", () => {
  const secondRoundReaction = {
    ...SAMPLE_RUN_EVENTS.find((event) => event.id === "round-1-value-feedback"),
    id: "round-2-value-feedback",
    round: 2,
    summary: "Second plan feels steadier.",
  };
  const comparison = createStrategyComparison(
    [...SAMPLE_RUN_EVENTS, secondRoundReaction],
    "round-1-strategy",
    "round-2-strategy",
  );

  assert.equal(comparison.left.strategy.name, "轻试用入口方案");
  assert.equal(comparison.right.strategy.name, "信任缓释方案");
  assert.equal(comparison.sharedPersonaReactions.length, 1);
  assert.equal(comparison.sharedPersonaReactions[0].right.summary, "Second plan feels steadier.");
});

test("summary export uses completed result directions risks and validation questions", () => {
  const events = [
    ...SAMPLE_RUN_EVENTS,
    {
      id: "completed-with-result",
      type: SANDBOX_EVENT_TYPES.RUN_COMPLETED,
      round: 2,
      headline: "Done",
      summary: "Result ready.",
      result: {
        directions: ["证据先行的信任方案"],
        risks: ["不要把内部 reward 当成销量预测"],
        validationQuestions: ["真实渠道里证据是否足够？"],
        audienceInsights: ["谨慎型先看保障。"],
        searchNotes: ["UCB 仍需继续探索复购家族。"],
      },
    },
  ];

  const markdown = buildRunSummaryMarkdown(events, {
    productLabel: "课堂新品",
    sourceLabel: "真实搜索",
  });

  assert.match(markdown, /课堂新品/);
  assert.match(markdown, /证据先行的信任方案/);
  assert.match(markdown, /真实渠道里证据是否足够/);
  assert.match(markdown, /reward、mean reward 与 UCB 分数只解释内部搜索过程/);
});

test("playback pace defaults to standard and exposes a classroom slow rhythm", () => {
  assert.equal(playbackPaceFromId("missing"), PLAYBACK_PACES.STANDARD);
  assert.ok(PLAYBACK_PACES.CLASSROOM.intervalMs > PLAYBACK_PACES.STANDARD.intervalMs);
});
