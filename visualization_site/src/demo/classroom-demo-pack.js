import {
  ACTION_CATEGORIES,
  PERSONA_PRESETS,
  RUN_SOURCES,
  STRATEGY_FAMILY_PRESETS,
} from "../config/run-config.js";
import { createArchiveCandidate } from "../events/run-lifecycle.js";
import { SAMPLE_RUN_EVENTS } from "../events/sample-run.js";

export const CLASSROOM_DEMO_ARCHIVE_ID = "classroom-demo-safe-rounds";
export const CLASSROOM_DEMO_CREATED_AT = "2026-05-23T00:00:00.000Z";

export function createClassroomDemoConfig() {
  return {
    source: RUN_SOURCES.FIXTURE,
    provider: {
      id: "deepseek-compatible",
      baseUrl: "",
      apiKey: "",
      useBackendDefaults: false,
      defaultModel: "",
    },
    models: {
      decision: "",
      consumers: "",
      synthesizer: "",
      critic: "",
    },
    product: {
      name: "轻行补给包",
      brand: "课堂演示品牌，主打清楚、低承诺、能复盘。",
      facts: "演示产品是日常随身护理补给包，可测试试用装、常规装、使用说明、客服和退换承诺；不得承诺医疗效果、未给出的认证或真实销量。",
      goal: "比较低门槛试用、信任缓释和复购防守三类营销赢法，给课堂展示留下策略选择理由。",
    },
    personaIds: PERSONA_PRESETS.map((persona) => persona.id),
    scenarioId: "competitor-pressure",
    actionCategories: [...ACTION_CATEGORIES],
    search: {
      useUcb: true,
      rounds: 4,
      candidatesPerRound: 1,
      familyIds: STRATEGY_FAMILY_PRESETS.map((family) => family.id),
    },
  };
}

export function createClassroomDemoArchive() {
  const archive = createArchiveCandidate({
    runId: "classroom-demo",
    runConfig: createClassroomDemoConfig(),
    events: SAMPLE_RUN_EVENTS,
    label: "课堂演示包 · 两轮安全回看",
    status: "demo_archive",
    stopReason: "prepared_fixture",
    createdAt: CLASSROOM_DEMO_CREATED_AT,
  });

  return {
    ...archive,
    archiveId: CLASSROOM_DEMO_ARCHIVE_ID,
  };
}
