export const RUN_SOURCES = Object.freeze({
  FIXTURE: "fixture",
  LIVE: "live",
});

export const PROVIDER_OPTIONS = Object.freeze([
  { id: "openai-compatible", label: "OpenAI-compatible" },
  { id: "deepseek-compatible", label: "DeepSeek-compatible" },
]);

export const PERSONA_PRESETS = Object.freeze([
  {
    id: "value-pragmatist",
    name: "预算价值务实者",
    motive: "先确认这笔钱是否真的解决问题。",
    barrier: "像一笔可省掉的额外开销。",
  },
  {
    id: "deal-explorer",
    name: "优惠触发尝鲜者",
    motive: "需要一个轻承诺入口才愿意试新。",
    barrier: "优惠退场后，价值理由容易变薄。",
  },
  {
    id: "trust-first",
    name: "信任风险谨慎者",
    motive: "需要证据、保障和更稳的承诺。",
    barrier: "陌生品牌的口头保证说服力不够。",
  },
  {
    id: "convenience-saver",
    name: "便利省时行动者",
    motive: "想把找、买、等和学的步骤压短。",
    barrier: "多一步注册或等待都可能劝退。",
  },
  {
    id: "habit-repeat",
    name: "习惯锚定复购者",
    motive: "在熟悉路径里追求省心和连续体验。",
    barrier: "没有明确切换理由就会留在旧选择里。",
  },
  {
    id: "outcome-optimizer",
    name: "结果表现优化者",
    motive: "会追问这套方案对具体任务有没有更好结果。",
    barrier: "卖点泛泛，证据和任务不贴。",
  },
  {
    id: "novelty-seeker",
    name: "新鲜体验探索者",
    motive: "会为清楚的新体验停下来。",
    barrier: "新只是包装，不是体验。",
  },
  {
    id: "social-proof-comparer",
    name: "口碑比较依赖者",
    motive: "需要相似人群的可信验证。",
    barrier: "评价太薄、太假或参照人群不对。",
  },
  {
    id: "identity-expresser",
    name: "身份意义表达者",
    motive: "想选和自我形象、价值或群体归属一致的东西。",
    barrier: "品牌表达看起来空泛或不真诚。",
  },
  {
    id: "occasion-buyer",
    name: "场合关系购买者",
    motive: "要让礼物、共享或社交场合不出错。",
    barrier: "时机、呈现和信号都不够稳。",
  },
]);

export const SCENARIO_PRESETS = Object.freeze([
  {
    id: "normal",
    name: "正常比较",
    note: "看基础吸引力和解释力。",
  },
  {
    id: "competitor-pressure",
    name: "竞品压力",
    note: "看竞品出现后还剩什么理由。",
  },
  {
    id: "trust-pressure",
    name: "信任压力",
    note: "看证据和风险缓释够不够。",
  },
]);

export const ACTION_CATEGORIES = Object.freeze([
  "Positioning",
  "Product",
  "Price",
  "Channel",
  "Promotion",
  "Retention",
]);

export const STRATEGY_FAMILY_PRESETS = Object.freeze([
  { id: "trial_value_entry", name: "试用价值入口" },
  { id: "trust_risk_reduction", name: "信任与风险缓释" },
  { id: "retention_habit_defense", name: "复购习惯防守" },
]);

const ACTION_CATEGORY_SET = new Set(ACTION_CATEGORIES);
const PERSONA_ID_SET = new Set(PERSONA_PRESETS.map((persona) => persona.id));
const SCENARIO_ID_SET = new Set(SCENARIO_PRESETS.map((scenario) => scenario.id));
const FAMILY_ID_SET = new Set(STRATEGY_FAMILY_PRESETS.map((family) => family.id));

export function createRunConfig() {
  return {
    source: RUN_SOURCES.FIXTURE,
    provider: {
      id: "openai-compatible",
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
      name: "课堂新品",
      brand: "品牌事实待补",
      facts: "核心能力、不可越界的产品边界和可验证证据。",
      goal: "找出能被不同人群解释清楚、也经得住竞品压力的营销方向。",
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

export function validateRunConfig(config) {
  const errors = [];
  const notices = [];

  if (!config || typeof config !== "object") {
    throw new TypeError("Run config must be an object.");
  }

  validateSandboxFacts(config, errors);
  validateSearchConfig(config, errors);

  if (config.source === RUN_SOURCES.FIXTURE) {
    notices.push("示例回放已就绪，真实 API 配置不会参与这次播放。");
  } else if (config.source === RUN_SOURCES.LIVE) {
    validateProviderConfig(config, errors);
  } else {
    errors.push("运行来源无法识别。");
  }

  return {
    ready: errors.length === 0,
    errors,
    notices,
  };
}

export function buildRunConfigPreview(config) {
  const selectedPersonas = PERSONA_PRESETS
    .filter((persona) => config.personaIds.includes(persona.id))
    .map((persona) => persona.name);
  const selectedFamilies = STRATEGY_FAMILY_PRESETS
    .filter((family) => config.search.familyIds.includes(family.id))
    .map((family) => family.name);

  return {
    sourceLabel: config.source === RUN_SOURCES.LIVE ? "真实搜索预检" : "示例回放",
    providerLabel: PROVIDER_OPTIONS.find((provider) => provider.id === config.provider.id)?.label || "未知 Provider",
    credentialLabel: config.provider.useBackendDefaults
      ? "后端默认配置"
      : config.provider.apiKey.trim()
        ? "临时 session 密钥已填"
        : "密钥未填",
    modelLabel: config.provider.defaultModel.trim() || "角色单独映射",
    productLabel: config.product.name.trim() || "产品未命名",
    personaLabel: summarizePersonaSelection(selectedPersonas),
    scenarioLabel: SCENARIO_PRESETS.find((scenario) => scenario.id === config.scenarioId)?.name || "未选场景",
    actionLabel: config.actionCategories.join(" / ") || "未开放动作",
    searchLabel: config.search.useUcb
      ? `UCB · ${config.search.rounds} 轮 · ${selectedFamilies.join(" / ") || "未选 family"}`
      : `定序搜索 · ${config.search.rounds} 轮`,
  };
}

function validateProviderConfig(config, errors) {
  if (!PROVIDER_OPTIONS.some((provider) => provider.id === config.provider.id)) {
    errors.push("请选择可识别的 Provider。");
  }

  if (!config.provider.useBackendDefaults && !isNonEmptyText(config.provider.baseUrl)) {
    errors.push("真实搜索需要 Base URL，或改用后端默认配置。");
  }

  if (!config.provider.useBackendDefaults && !isNonEmptyText(config.provider.apiKey)) {
    errors.push("真实搜索需要临时 API Key，或改用后端默认配置。");
  }

  if (!hasModelRoute(config)) {
    errors.push("请填写默认模型，或把四类角色模型都映射清楚。");
  }
}

function summarizePersonaSelection(selectedPersonas) {
  if (selectedPersonas.length === 0) {
    return "未选人群";
  }

  if (selectedPersonas.length <= 4) {
    return selectedPersonas.join(" / ");
  }

  return `${selectedPersonas.length} 张覆盖卡 · ${selectedPersonas.slice(0, 3).join(" / ")} / ...`;
}

function validateSandboxFacts(config, errors) {
  if (!isNonEmptyText(config.product?.name)) {
    errors.push("请给本轮沙盘写一个产品名。");
  }

  if (!isNonEmptyText(config.product?.facts)) {
    errors.push("请补产品事实和产品边界。");
  }

  if (!isNonEmptyText(config.product?.goal)) {
    errors.push("请补本轮营销目标。");
  }

  if (!Array.isArray(config.personaIds) || config.personaIds.length === 0) {
    errors.push("至少选择一张消费者人群卡。");
  } else if (config.personaIds.some((personaId) => !PERSONA_ID_SET.has(personaId))) {
    errors.push("消费者人群卡里有未知项。");
  }

  if (!SCENARIO_ID_SET.has(config.scenarioId)) {
    errors.push("请选择一个可识别的场景卡。");
  }

  if (!Array.isArray(config.actionCategories) || config.actionCategories.length === 0) {
    errors.push("动作集至少开放一个营销动作大类。");
  } else if (config.actionCategories.some((category) => !ACTION_CATEGORY_SET.has(category))) {
    errors.push("动作集中有未知营销动作大类。");
  }
}

function validateSearchConfig(config, errors) {
  if (!Number.isInteger(config.search?.rounds) || config.search.rounds < 1 || config.search.rounds > 24) {
    errors.push("搜索轮次要落在 1 到 24 之间。");
  }

  if (
    !Number.isInteger(config.search?.candidatesPerRound)
    || config.search.candidatesPerRound < 1
    || config.search.candidatesPerRound > 4
  ) {
    errors.push("每轮候选数要落在 1 到 4 之间。");
  }

  if (config.search?.useUcb) {
    if (!Array.isArray(config.search.familyIds) || config.search.familyIds.length === 0) {
      errors.push("开启 UCB 时至少保留一个策略 family。");
    } else if (config.search.familyIds.some((familyId) => !FAMILY_ID_SET.has(familyId))) {
      errors.push("UCB family 列表里有未知项。");
    }
  }
}

function hasModelRoute(config) {
  if (isNonEmptyText(config.provider.defaultModel)) {
    return true;
  }

  return ["decision", "consumers", "synthesizer", "critic"].every((role) => isNonEmptyText(config.models[role]));
}

function isNonEmptyText(value) {
  return typeof value === "string" && value.trim() !== "";
}
