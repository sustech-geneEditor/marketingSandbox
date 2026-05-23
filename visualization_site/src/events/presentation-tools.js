import { SANDBOX_EVENT_TYPES } from "./event-schema.js";

export const PLAYBACK_PACES = Object.freeze({
  STANDARD: Object.freeze({
    id: "standard",
    label: "标准",
    intervalMs: 2100,
  }),
  CLASSROOM: Object.freeze({
    id: "classroom",
    label: "讲解慢速",
    intervalMs: 4200,
  }),
});

const PLAYBACK_PACE_LIST = Object.freeze(Object.values(PLAYBACK_PACES));

export function playbackPaceFromId(paceId) {
  return PLAYBACK_PACE_LIST.find((pace) => pace.id === paceId) || PLAYBACK_PACES.STANDARD;
}

export function collectStrategySnapshots(events) {
  requireEventArray(events);

  return events.flatMap((event, index) => {
    if (event.type !== SANDBOX_EVENT_TYPES.STRATEGY_PROPOSED || !event.strategy) {
      return [];
    }

    const roundEvents = events.filter((candidate) => candidate.round === event.round);
    const familyEvent = findLatestBefore(
      events,
      index,
      (candidate) => candidate.round === event.round && candidate.family,
    );
    const synthesisEvent = findLatest(roundEvents, (candidate) => candidate.synthesis);
    const critiqueEvent = findLatest(roundEvents, (candidate) => candidate.critique);
    const searchEvent = findLatest(roundEvents, (candidate) => candidate.search);

    return [{
      id: event.id,
      round: event.round,
      label: strategyLabel(event),
      strategy: event.strategy,
      family: familyEvent?.family || familyFallback(event.strategy),
      consumerFeedback: roundEvents
        .filter((candidate) => candidate.type === SANDBOX_EVENT_TYPES.CONSUMER_FEEDBACK_READY)
        .map(toConsumerFeedbackSnapshot),
      synthesis: synthesisEvent?.synthesis || null,
      critique: critiqueEvent?.critique || null,
      search: searchEvent?.search || null,
    }];
  });
}

export function createStrategyComparison(events, leftId, rightId) {
  const strategies = collectStrategySnapshots(events);
  const left = strategies.find((strategy) => strategy.id === leftId) || strategies[0] || null;
  const right =
    strategies.find((strategy) => strategy.id === rightId)
    || strategies.find((strategy) => strategy.id !== left?.id)
    || left
    || null;

  return {
    strategies,
    left,
    right,
    sharedPersonaReactions: sharedPersonaReactions(left, right),
  };
}

export function buildRunSummaryMarkdown(events, options = {}) {
  requireEventArray(events);
  const strategies = collectStrategySnapshots(events);
  const runCompleted = findLatest(events, (event) => event.type === SANDBOX_EVENT_TYPES.RUN_COMPLETED);
  const result = runCompleted?.result || {};
  const completedRounds = uniqueRounds(events, SANDBOX_EVENT_TYPES.ROUND_COMPLETED);
  const productLabel = cleanText(options.productLabel || "未命名产品");
  const sourceLabel = cleanText(options.sourceLabel || "当前事件流");
  const directions = result.directions || strategyDirections(strategies);
  const risks = result.risks || uniqueText(strategies.map((strategy) => strategy.critique?.mainRisk));
  const questions =
    result.validationQuestions
    || uniqueText(events.map((event) => event.proposal?.nextValidationQuestion || event.critique?.next));
  const audienceInsights =
    result.audienceInsights
    || uniqueText(strategies.flatMap((strategy) => strategy.consumerFeedback.map((feedback) => feedback.summary)));
  const searchNotes =
    result.searchNotes
    || uniqueText(strategies.map((strategy) => strategy.search?.note));

  return [
    "# 营销沙盘搜索摘要",
    "",
    `- 产品：${productLabel}`,
    `- 事件来源：${sourceLabel}`,
    `- 已记录事件：${events.length}`,
    `- 已完成轮次：${completedRounds.length ? completedRounds.join(" / ") : "尚无完整轮次"}`,
    "",
    "> 本摘要来自沙盘事件流。reward、mean reward 与 UCB 分数只解释内部搜索过程，不代表真实购买率、复购率或市场预测。",
    "",
    "## 推荐方向",
    ...markdownBullets(directions, "暂无完成轮次形成推荐方向。"),
    "",
    "## 搜索过的策略",
    ...strategyMarkdown(strategies),
    "",
    "## 人群反馈线索",
    ...markdownBullets(audienceInsights, "暂无可导出的人群反馈线索。"),
    "",
    "## 风险",
    ...markdownBullets(risks, "暂无批评者风险摘要。"),
    "",
    "## 待验证问题",
    ...markdownBullets(questions, "暂无待验证问题。"),
    "",
    "## 搜索备注",
    ...markdownBullets(searchNotes, "暂无搜索备注。"),
    "",
  ].join("\n");
}

function strategyMarkdown(strategies) {
  if (strategies.length === 0) {
    return ["- 暂无策略提案。"];
  }

  return strategies.flatMap((snapshot) => {
    const reward = snapshot.search?.internalMetrics?.reward;
    const actions = snapshot.strategy.actions || [];
    const actionText = actions.length
      ? actions.map((action) => `${cleanText(action.category)}：${cleanText(action.note)}`).join("；")
      : "本轮未记录动作拆解";
    const rewardText = reward === null || reward === undefined ? "" : `；内部 reward：${cleanText(reward)}`;
    return [
      `- Round ${snapshot.round} · ${cleanText(snapshot.strategy.name || "未命名策略")} · ${cleanText(snapshot.family?.id || snapshot.strategy.familyId || "未标 family")}`,
      `  - 意图：${cleanText(snapshot.strategy.intent || "未记录")}`,
      `  - 动作：${actionText}${rewardText}`,
    ];
  });
}

function markdownBullets(values, emptyText) {
  const cleaned = uniqueText(Array.isArray(values) ? values : []);
  return cleaned.length ? cleaned.map((value) => `- ${cleanText(value)}`) : [`- ${emptyText}`];
}

function strategyDirections(strategies) {
  return uniqueText(
    strategies.map((strategy) => {
      const name = strategy.strategy.name || "未命名策略";
      const intent = strategy.strategy.intent || strategy.synthesis?.next || "";
      return intent ? `${name}：${intent}` : name;
    }),
  );
}

function sharedPersonaReactions(left, right) {
  if (!left || !right) {
    return [];
  }

  const rightByActor = new Map(right.consumerFeedback.map((feedback) => [feedback.actorId, feedback]));
  return left.consumerFeedback.flatMap((feedback) => {
    const pair = rightByActor.get(feedback.actorId);
    return pair
      ? [{
          actorId: feedback.actorId,
          actorName: feedback.actorName || pair.actorName || feedback.actorId,
          left: feedback,
          right: pair,
        }]
      : [];
  });
}

function toConsumerFeedbackSnapshot(event) {
  return {
    actorId: event.actorId || event.actor_id || "consumer",
    actorName: event.actorName || event.actor_name || event.headline || "消费者",
    summary: event.summary || event.feedback?.firstImpression || "",
    feedback: event.feedback || {},
  };
}

function strategyLabel(event) {
  return `Round ${event.round} · ${event.strategy.name || event.headline}`;
}

function familyFallback(strategy) {
  return strategy.familyId
    ? {
        id: strategy.familyId,
        name: strategy.familyId,
        state: "from strategy",
      }
    : null;
}

function uniqueRounds(events, type) {
  return [...new Set(events.filter((event) => event.type === type).map((event) => event.round))];
}

function uniqueText(values) {
  return [...new Set(values.filter((value) => typeof value === "string" && value.trim()).map(cleanText))];
}

function cleanText(value) {
  return String(value)
    .replace(/\s+/g, " ")
    .replace(/[<>]/g, "")
    .trim();
}

function requireEventArray(events) {
  if (!Array.isArray(events)) {
    throw new TypeError("Presentation tools need an event array.");
  }
}

function findLatestBefore(events, endIndex, predicate) {
  for (let index = endIndex; index >= 0; index -= 1) {
    if (predicate(events[index])) {
      return events[index];
    }
  }

  return null;
}

function findLatest(events, predicate) {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    if (predicate(events[index])) {
      return events[index];
    }
  }

  return null;
}
