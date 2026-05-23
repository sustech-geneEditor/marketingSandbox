import "./styles.css";
import {
  ACTION_CATEGORIES,
  buildRunConfigPreview,
  createRunConfig,
  PERSONA_PRESETS,
  PROVIDER_OPTIONS,
  RUN_SOURCES,
  SCENARIO_PRESETS,
  STRATEGY_FAMILY_PRESETS,
  validateRunConfig,
} from "./config/run-config.js";
import {
  createProviderCheckState,
  PROVIDER_CHECK_STATUS,
  providerCheckAllowsLiveRun,
  requestProviderCheck,
} from "./config/provider-check.js";
import { createPlaybackState, PLAYBACK_STATUS, reducePlayback } from "./events/event-player.js";
import { iterLiveEventStream } from "./events/live-event-stream.js";
import { LIVE_RUN_ISSUE_KINDS, createLiveRunIssue } from "./events/live-run-issue.js";
import {
  createArchiveCandidate,
  createRunId,
  listArchives,
  loadArchive,
  requestApiDisconnectAutoArchive,
  requestArchiveResumePlan,
  requestLiveRunStop,
  saveArchive,
  shouldAutoArchiveDisconnect,
} from "./events/run-lifecycle.js";
import { RUN_STATUSES, canStopRun, isRunBusyStatus } from "./events/run-state.js";
import { createPlaybackSnapshot } from "./events/playback-snapshot.js";
import { SANDBOX_EVENT_TYPES } from "./events/event-schema.js";
import {
  buildRunSummaryMarkdown,
  createStrategyComparison,
  PLAYBACK_PACES,
  playbackPaceFromId,
} from "./events/presentation-tools.js";
import { SAMPLE_AGENTS, SAMPLE_RUN_EVENTS } from "./events/sample-run.js";
import {
  createClassroomDemoArchive,
  createClassroomDemoConfig,
} from "./demo/classroom-demo-pack.js";
import { SandboxScene } from "./scene/sandbox-scene.js";

const API_DISCONNECT_RECONNECT_ATTEMPTS = 8;
const API_DISCONNECT_FINAL_WAIT_MS = 60_000;
const PROVIDER_CHECK_INPUT_IDS = new Set([
  "provider-select",
  "base-url-input",
  "api-key-input",
  "backend-defaults-input",
  "default-model-input",
  "decision-model-input",
  "consumer-model-input",
  "synthesizer-model-input",
  "critic-model-input",
]);
const app = document.querySelector("#app");
const providerOptionsMarkup = PROVIDER_OPTIONS
  .map((provider) => `<option value="${provider.id}">${provider.label}</option>`)
  .join("");
const personaCardsMarkup = PERSONA_PRESETS
  .map(
    (persona) => `
      <label class="choice-card">
        <input name="persona-choice" type="checkbox" value="${persona.id}" />
        <span>
          <strong>${persona.name}</strong>
          <small>${persona.motive}</small>
        </span>
      </label>
    `,
  )
  .join("");
const scenarioCardsMarkup = SCENARIO_PRESETS
  .map(
    (scenario) => `
      <label class="choice-card">
        <input name="scenario-choice" type="radio" value="${scenario.id}" />
        <span>
          <strong>${scenario.name}</strong>
          <small>${scenario.note}</small>
        </span>
      </label>
    `,
  )
  .join("");
const actionChoicesMarkup = ACTION_CATEGORIES
  .map(
    (category) => `
      <label class="action-choice">
        <input name="action-category" type="checkbox" value="${category}" />
        <span>${category}</span>
      </label>
    `,
  )
  .join("");
const familyChoicesMarkup = STRATEGY_FAMILY_PRESETS
  .map(
    (family) => `
      <label class="family-choice">
        <input name="family-choice" type="checkbox" value="${family.id}" />
        <span>${family.name}</span>
      </label>
    `,
  )
  .join("");

app.innerHTML = `
  <main class="workbench">
    <header class="topbar">
      <div class="brand">
        <span class="brand-mark" aria-hidden="true"></span>
        <div>
          <h1>营销多智能体沙盘</h1>
          <p id="brand-subtitle">示例事件回放</p>
        </div>
      </div>
      <div class="status-strip" aria-live="polite">
        <span class="status-pill" id="api-status">API 未连接</span>
        <span class="status-pill" id="round-status">待机</span>
        <span class="status-pill status-signal">搜索信号不是市场预测</span>
      </div>
      <nav class="playback-controls" aria-label="回放控制">
        <button id="play-button" type="button">播放</button>
        <button id="pause-button" type="button">暂停</button>
        <button id="step-button" type="button">单步</button>
        <button id="reset-button" type="button">重置</button>
        <div class="pace-switch" role="radiogroup" aria-label="演示节奏">
          <label title="按正常演示节奏播放">
            <input name="playback-pace" type="radio" value="${PLAYBACK_PACES.STANDARD.id}" />
            <span>${PLAYBACK_PACES.STANDARD.label}</span>
          </label>
          <label title="给课堂讲解留出停顿">
            <input name="playback-pace" type="radio" value="${PLAYBACK_PACES.CLASSROOM.id}" />
            <span>${PLAYBACK_PACES.CLASSROOM.label}</span>
          </label>
        </div>
        <button id="live-run-button" type="button">真实运行</button>
        <button id="stop-run-button" type="button">停止</button>
      </nav>
    </header>

    <section class="main-grid">
      <aside class="config-rail" aria-label="沙盘配置">
        <section class="rail-section">
          <div class="section-title">
            <h2>API 与模型</h2>
            <span id="run-source-badge">fixture</span>
          </div>
          <div class="mode-switch" role="radiogroup" aria-label="运行来源">
            <label>
              <input name="run-source" type="radio" value="${RUN_SOURCES.FIXTURE}" />
              <span>示例回放</span>
            </label>
            <label>
              <input name="run-source" type="radio" value="${RUN_SOURCES.LIVE}" />
              <span>真实搜索</span>
            </label>
          </div>
          <div class="source-actions">
            <button id="load-fixture-button" type="button">载入稳定样例</button>
            <button id="load-classroom-pack-button" type="button">载入课堂数据包</button>
            <small>课堂可以先播样例，再切到真实运行。</small>
          </div>
          <label>
            Provider
            <select id="provider-select">${providerOptionsMarkup}</select>
          </label>
          <label>
            Base URL
            <input id="base-url-input" placeholder="https://provider.example/v1" />
          </label>
          <label>
            API Key
            <input id="api-key-input" type="password" placeholder="session key" autocomplete="off" />
          </label>
          <label class="inline-check">
            <input id="backend-defaults-input" type="checkbox" />
            <span>使用后端默认配置</span>
          </label>
          <label>
            Default Model
            <input id="default-model-input" placeholder="留空时使用角色级映射" />
          </label>
          <div class="model-grid">
            <label>
              Decision
              <input id="decision-model-input" placeholder="reasoning model" />
            </label>
            <label>
              Consumers
              <input id="consumer-model-input" placeholder="consumer model" />
            </label>
            <label>
              Synthesizer
              <input id="synthesizer-model-input" placeholder="summary model" />
            </label>
            <label>
              Critic
              <input id="critic-model-input" placeholder="critic model" />
            </label>
          </div>
          <button id="check-config-button" class="primary-button" type="button">配置预检</button>
          <div id="config-readiness" class="config-readiness" aria-live="polite"></div>
        </section>

        <section class="rail-section">
          <div class="section-title">
            <h2>产品与目标</h2>
            <span>facts</span>
          </div>
          <label>
            产品名
            <input id="product-name-input" />
          </label>
          <label>
            品牌事实
            <input id="brand-input" />
          </label>
          <label>
            产品事实与边界
            <textarea id="product-facts-input" rows="3"></textarea>
          </label>
          <label>
            本轮目标
            <textarea id="goal-input" rows="3"></textarea>
          </label>
        </section>

        <section class="rail-section">
          <div class="section-title">
            <h2>人群卡</h2>
            <span id="persona-count">0 selected</span>
          </div>
          <div class="choice-list" id="persona-choices">${personaCardsMarkup}</div>
        </section>

        <section class="rail-section">
          <div class="section-title">
            <h2>场景卡</h2>
            <span>Scenario</span>
          </div>
          <div class="choice-list" id="scenario-choices">${scenarioCardsMarkup}</div>
        </section>

        <section class="rail-section action-space">
          <div class="section-title">
            <h2>动作边界</h2>
            <span>ActionSpace</span>
          </div>
          <div class="action-choice-grid" id="action-choices">${actionChoicesMarkup}</div>
        </section>

        <section class="rail-section">
          <div class="section-title">
            <h2>搜索设置</h2>
            <span>UCB</span>
          </div>
          <label class="inline-check">
            <input id="ucb-toggle" type="checkbox" />
            <span>开启 family 搜索</span>
          </label>
          <div class="number-grid">
            <label>
              轮次
              <input id="rounds-input" type="number" min="1" max="24" />
            </label>
            <label>
              每轮候选
              <input id="candidates-input" type="number" min="1" max="4" />
            </label>
          </div>
          <div class="choice-list compact-choice-list" id="family-choices">${familyChoicesMarkup}</div>
        </section>

        <section class="rail-section config-preview-panel">
          <div class="section-title">
            <h2>运行快照</h2>
            <span>safe preview</span>
          </div>
          <dl id="config-preview" class="config-preview"></dl>
        </section>

        <section class="rail-section archive-panel">
          <div class="section-title">
            <h2>停止与存档</h2>
            <span id="archive-state-badge">idle</span>
          </div>
          <p id="archive-status" class="archive-status">暂无待存档内容。</p>
          <label>
            存档名称
            <input id="archive-label-input" placeholder="例如：课堂演示第 1 轮" />
          </label>
          <div class="archive-actions">
            <button id="save-archive-button" type="button">存档</button>
            <button id="discard-archive-button" type="button">不存档</button>
          </div>
          <label>
            导入存档
            <select id="archive-select">
              <option value="">暂无存档</option>
            </select>
          </label>
          <div class="archive-actions">
            <button id="import-archive-button" type="button">导入回看</button>
            <button id="continue-archive-button" type="button">安全续跑</button>
          </div>
          <p id="archive-resume-note" class="archive-note"></p>
        </section>
      </aside>

      <section class="stage-column" aria-label="三维沙盘">
        <div class="scene-shell">
          <div class="stage-hud">
            <span id="event-kind">待机</span>
            <strong id="stage-headline">等待回放开始</strong>
          </div>
          <div id="scene-host" class="scene-host" data-testid="scene-host"></div>
        </div>
      </section>

      <aside class="insight-rail" aria-label="实时解释">
        <section class="rail-section issue-panel" id="run-issue-panel" data-state="idle" hidden>
          <div class="section-title">
            <h2>运行暂停说明</h2>
            <span id="run-issue-kind">issue</span>
          </div>
          <h3 id="run-issue-title"></h3>
          <p id="run-issue-explanation"></p>
          <p class="issue-message" id="run-issue-message"></p>
        </section>

        <section class="rail-section event-panel">
          <div class="section-title">
            <h2>当前事件</h2>
            <span id="event-round">Round -</span>
          </div>
          <h3 id="event-headline">准备就绪</h3>
          <p id="event-summary">点击播放或单步，查看 agent 如何围着策略搜索互动。</p>
          <p class="event-detail" id="event-detail"></p>
        </section>

        <section class="rail-section strategy-panel">
          <div class="section-title">
            <h2>当前策略</h2>
            <span id="family-state">未选择</span>
          </div>
          <h3 id="strategy-name">等待 DecisionAgent 出招</h3>
          <p id="strategy-intent">策略动作会在这里落回动作集边界。</p>
          <div id="action-list" class="action-list"></div>
        </section>

        <section class="rail-section feedback-panel">
          <div class="section-title">
            <h2>反馈与风险</h2>
            <span id="speaker-role">待机</span>
          </div>
          <dl id="feedback-details" class="feedback-details"></dl>
        </section>

        <section class="rail-section search-panel">
          <div class="section-title">
            <h2>Family 轨迹</h2>
            <span>qualitative</span>
          </div>
          <p id="search-note">还没有搜索更新。</p>
          <div id="family-track" class="family-track"></div>
          <dl id="search-metrics" class="search-metrics"></dl>
        </section>

        <section class="rail-section compare-panel">
          <div class="section-title">
            <h2>策略对比</h2>
            <span>round / family</span>
          </div>
          <div class="compare-selectors">
            <label>
              方案 A
              <select id="compare-left-select"></select>
            </label>
            <label>
              方案 B
              <select id="compare-right-select"></select>
            </label>
          </div>
          <div id="comparison-output" class="comparison-output"></div>
        </section>

        <section class="rail-section export-panel">
          <div class="section-title">
            <h2>课堂摘要</h2>
            <span>Markdown</span>
          </div>
          <p>导出当前事件流里的策略、风险、问题和内部搜索说明。</p>
          <button id="export-summary-button" class="primary-button" type="button">导出摘要</button>
          <p id="export-status" class="export-status" aria-live="polite"></p>
        </section>
      </aside>
    </section>

    <footer class="timeline-panel">
      <div class="timeline-heading">
        <h2>搜索时间线</h2>
        <span id="playback-state">idle</span>
      </div>
      <div id="timeline" class="timeline" aria-label="事件时间线"></div>
    </footer>
  </main>
`;

const elements = {
  brandSubtitle: document.querySelector("#brand-subtitle"),
  playButton: document.querySelector("#play-button"),
  pauseButton: document.querySelector("#pause-button"),
  stepButton: document.querySelector("#step-button"),
  resetButton: document.querySelector("#reset-button"),
  loadFixtureButton: document.querySelector("#load-fixture-button"),
  loadClassroomPackButton: document.querySelector("#load-classroom-pack-button"),
  liveRunButton: document.querySelector("#live-run-button"),
  stopRunButton: document.querySelector("#stop-run-button"),
  apiStatus: document.querySelector("#api-status"),
  roundStatus: document.querySelector("#round-status"),
  playbackState: document.querySelector("#playback-state"),
  eventKind: document.querySelector("#event-kind"),
  stageHeadline: document.querySelector("#stage-headline"),
  eventRound: document.querySelector("#event-round"),
  eventHeadline: document.querySelector("#event-headline"),
  eventSummary: document.querySelector("#event-summary"),
  eventDetail: document.querySelector("#event-detail"),
  familyState: document.querySelector("#family-state"),
  strategyName: document.querySelector("#strategy-name"),
  strategyIntent: document.querySelector("#strategy-intent"),
  actionList: document.querySelector("#action-list"),
  feedbackDetails: document.querySelector("#feedback-details"),
  speakerRole: document.querySelector("#speaker-role"),
  searchNote: document.querySelector("#search-note"),
  familyTrack: document.querySelector("#family-track"),
  searchMetrics: document.querySelector("#search-metrics"),
  timeline: document.querySelector("#timeline"),
  runSourceBadge: document.querySelector("#run-source-badge"),
  providerSelect: document.querySelector("#provider-select"),
  baseUrlInput: document.querySelector("#base-url-input"),
  apiKeyInput: document.querySelector("#api-key-input"),
  backendDefaultsInput: document.querySelector("#backend-defaults-input"),
  defaultModelInput: document.querySelector("#default-model-input"),
  decisionModelInput: document.querySelector("#decision-model-input"),
  consumerModelInput: document.querySelector("#consumer-model-input"),
  synthesizerModelInput: document.querySelector("#synthesizer-model-input"),
  criticModelInput: document.querySelector("#critic-model-input"),
  checkConfigButton: document.querySelector("#check-config-button"),
  configReadiness: document.querySelector("#config-readiness"),
  productNameInput: document.querySelector("#product-name-input"),
  brandInput: document.querySelector("#brand-input"),
  productFactsInput: document.querySelector("#product-facts-input"),
  goalInput: document.querySelector("#goal-input"),
  personaCount: document.querySelector("#persona-count"),
  ucbToggle: document.querySelector("#ucb-toggle"),
  roundsInput: document.querySelector("#rounds-input"),
  candidatesInput: document.querySelector("#candidates-input"),
  configPreview: document.querySelector("#config-preview"),
  archiveStateBadge: document.querySelector("#archive-state-badge"),
  archiveStatus: document.querySelector("#archive-status"),
  archiveLabelInput: document.querySelector("#archive-label-input"),
  saveArchiveButton: document.querySelector("#save-archive-button"),
  discardArchiveButton: document.querySelector("#discard-archive-button"),
  archiveSelect: document.querySelector("#archive-select"),
  importArchiveButton: document.querySelector("#import-archive-button"),
  continueArchiveButton: document.querySelector("#continue-archive-button"),
  archiveResumeNote: document.querySelector("#archive-resume-note"),
  runIssuePanel: document.querySelector("#run-issue-panel"),
  runIssueKind: document.querySelector("#run-issue-kind"),
  runIssueTitle: document.querySelector("#run-issue-title"),
  runIssueExplanation: document.querySelector("#run-issue-explanation"),
  runIssueMessage: document.querySelector("#run-issue-message"),
  compareLeftSelect: document.querySelector("#compare-left-select"),
  compareRightSelect: document.querySelector("#compare-right-select"),
  comparisonOutput: document.querySelector("#comparison-output"),
  exportSummaryButton: document.querySelector("#export-summary-button"),
  exportStatus: document.querySelector("#export-status"),
};

const scene = new SandboxScene(document.querySelector("#scene-host"), SAMPLE_AGENTS);
let playback = createPlaybackState(SAMPLE_RUN_EVENTS);
let playbackSource = RUN_SOURCES.FIXTURE;
let runConfig = createRunConfig();
let configCheckRequested = false;
let providerCheckState = createProviderCheckState();
let liveStreamState = {
  status: RUN_STATUSES.IDLE,
  message: "Fixture playback is loaded.",
};
let archiveState = {
  status: "idle",
  message: "暂无待存档内容。",
};
let currentRunId = "";
let stopRequestedRunId = "";
let activeLiveAbortController = null;
let currentLiveEvents = [];
let pendingArchive = null;
let savedArchives = [];
let selectedArchiveId = "";
let disconnectArchiveTimer = null;
let autoplayTimer = null;
let playbackPace = PLAYBACK_PACES.STANDARD;
let liveRunIssue = null;
let comparisonSelection = {
  leftId: "",
  rightId: "",
};

elements.playButton.addEventListener("click", () => {
  dispatch({ type: "play" });
  startAutoplay();
});
elements.pauseButton.addEventListener("click", () => {
  dispatch({ type: "pause" });
  stopAutoplay();
});
elements.stepButton.addEventListener("click", () => {
  stopAutoplay();
  dispatch({ type: "step" });
});
elements.resetButton.addEventListener("click", () => {
  stopAutoplay();
  dispatch({ type: "reset" });
});
elements.loadFixtureButton.addEventListener("click", () => {
  stopAutoplay();
  resetFixturePlayback();
  runConfig.source = RUN_SOURCES.FIXTURE;
  writeRunConfigToInputs(runConfig);
  render();
});
elements.loadClassroomPackButton.addEventListener("click", () => {
  void loadClassroomDemoPack();
});
elements.liveRunButton.addEventListener("click", () => {
  void loadLiveRunEvents();
});
elements.stopRunButton.addEventListener("click", () => {
  void stopLiveRun();
});
elements.saveArchiveButton.addEventListener("click", () => {
  void savePendingArchive();
});
elements.discardArchiveButton.addEventListener("click", () => {
  discardPendingArchive();
});
elements.archiveSelect.addEventListener("change", () => {
  selectedArchiveId = elements.archiveSelect.value;
  renderArchivePanel();
});
elements.importArchiveButton.addEventListener("click", () => {
  void importSelectedArchive({ continueSearch: false });
});
elements.continueArchiveButton.addEventListener("click", () => {
  void importSelectedArchive({ continueSearch: true });
});
elements.compareLeftSelect.addEventListener("change", () => {
  comparisonSelection.leftId = elements.compareLeftSelect.value;
  render();
});
elements.compareRightSelect.addEventListener("change", () => {
  comparisonSelection.rightId = elements.compareRightSelect.value;
  render();
});
elements.exportSummaryButton.addEventListener("click", () => {
  exportRunSummary();
});
document.querySelector(".playback-controls").addEventListener("change", (event) => {
  if (event.target.name !== "playback-pace") {
    return;
  }
  playbackPace = playbackPaceFromId(event.target.value);
  if (autoplayTimer) {
    startAutoplay();
  }
  render();
});
document.querySelector(".config-rail").addEventListener("input", handleConfigInput);
document.querySelector(".config-rail").addEventListener("change", handleConfigInput);
elements.checkConfigButton.addEventListener("click", () => {
  void checkProviderConnection();
});

writeRunConfigToInputs(runConfig);
checkNamedValue("playback-pace", playbackPace.id);
render();
void refreshArchiveList();

function startAutoplay() {
  stopAutoplay();
  autoplayTimer = window.setInterval(() => {
    dispatch({ type: "step" });
    if (playback.status === PLAYBACK_STATUS.COMPLETE) {
      stopAutoplay();
    }
  }, playbackPace.intervalMs);
}

function stopAutoplay() {
  if (autoplayTimer) {
    window.clearInterval(autoplayTimer);
    autoplayTimer = null;
  }
}

function dispatch(action) {
  playback = reducePlayback(playback, action);
  render();
}

function replacePlaybackEvents(events, source) {
  playback = createPlaybackState(events);
  playbackSource = source;
}

function resetFixturePlayback() {
  clearDisconnectAutoArchiveTimer();
  if (activeLiveAbortController) {
    activeLiveAbortController.abort();
    activeLiveAbortController = null;
  }
  replacePlaybackEvents(SAMPLE_RUN_EVENTS, RUN_SOURCES.FIXTURE);
  currentRunId = "";
  stopRequestedRunId = "";
  currentLiveEvents = [];
  pendingArchive = null;
  liveRunIssue = null;
  comparisonSelection = {
    leftId: "",
    rightId: "",
  };
  liveStreamState = {
    status: RUN_STATUSES.IDLE,
    message: "Fixture playback is loaded.",
  };
  providerCheckState = createProviderCheckState();
  archiveState = {
    status: "idle",
    message: "暂无待存档内容。",
  };
}

async function loadClassroomDemoPack() {
  stopAutoplay();
  resetFixturePlayback();
  runConfig = createClassroomDemoConfig();
  writeRunConfigToInputs(runConfig);
  const demoArchive = createClassroomDemoArchive();

  try {
    await saveArchive(demoArchive, { preferLocal: true });
    selectedArchiveId = demoArchive.archiveId;
    archiveState = {
      status: "saved",
      message: "课堂数据包已载入：产品、人群、场景、family、样例回放和安全回看存档都可用。",
    };
    await refreshArchiveList();
  } catch (error) {
    archiveState = {
      status: "error",
      message: error instanceof Error ? error.message : String(error),
    };
    render();
  }
}

async function checkProviderConnection() {
  configCheckRequested = true;
  runConfig = readRunConfigFromInputs();
  const validation = validateRunConfig(runConfig);

  if (runConfig.source !== RUN_SOURCES.LIVE) {
    providerCheckState = createProviderCheckState({
      status: PROVIDER_CHECK_STATUS.CONNECTED,
      ok: true,
      message: "Demo playback does not need a live provider check.",
      modelStatus: "fixture",
      checkedAt: new Date().toISOString(),
    });
    liveStreamState = {
      status: RUN_STATUSES.IDLE,
      message: "Fixture playback is loaded.",
    };
    render();
    return;
  }

  if (!validation.ready) {
    providerCheckState = createProviderCheckState({
      status: PROVIDER_CHECK_STATUS.FAILED,
      ok: false,
      message: "Complete the live run config before provider-check.",
      checkedAt: new Date().toISOString(),
    });
    liveStreamState = {
      status: RUN_STATUSES.FAILED,
      message: providerCheckState.message,
    };
    render();
    return;
  }

  providerCheckState = createProviderCheckState({
    status: PROVIDER_CHECK_STATUS.CHECKING,
    ok: false,
    message: "Checking provider through the local backend...",
  });
  liveStreamState = {
    status: RUN_STATUSES.CHECKING_PROVIDER,
    message: "Checking provider through the local backend...",
  };
  render();

  providerCheckState = await requestProviderCheck(runConfig);
  liveStreamState = {
    status: providerCheckAllowsLiveRun(providerCheckState) ? RUN_STATUSES.IDLE : RUN_STATUSES.FAILED,
    message: providerCheckState.message,
  };
  render();
}

async function loadLiveRunEvents() {
  stopAutoplay();
  clearDisconnectAutoArchiveTimer();
  liveRunIssue = null;
  configCheckRequested = true;
  runConfig = readRunConfigFromInputs();
  const validation = validateRunConfig(runConfig);

  if (runConfig.source !== RUN_SOURCES.LIVE) {
    liveStreamState = {
      status: RUN_STATUSES.FAILED,
      message: "Switch the source to live search before loading a live stream.",
    };
    render();
    return;
  }

  if (!validation.ready) {
    liveStreamState = {
      status: RUN_STATUSES.FAILED,
      message: "Live stream is waiting for a complete run configuration.",
    };
    render();
    return;
  }

  if (!providerCheckAllowsLiveRun(providerCheckState)) {
    liveStreamState = {
      status: RUN_STATUSES.FAILED,
      message: "Run provider-check successfully before starting a real live search.",
    };
    render();
    return;
  }

  if (activeLiveAbortController) {
    activeLiveAbortController.abort();
  }

  const runId = createRunId("live");
  const abortController = new AbortController();
  currentRunId = runId;
  stopRequestedRunId = "";
  currentLiveEvents = [];
  activeLiveAbortController = abortController;
  pendingArchive = null;
  liveStreamState = {
    status: RUN_STATUSES.STARTING,
    message: `正在连接 live event stream：${runId}`,
  };
  archiveState = {
    status: "running",
    message: "本轮真实搜索进行中；暂停只会暂停回放，停止才会结束本地搜索。",
  };
  render();

  try {
    const events = [];
    for await (const event of iterLiveEventStream(runConfig, { runId, signal: abortController.signal })) {
      events.push(event);
      currentLiveEvents = [...events];
      replacePlaybackEvents(events, RUN_SOURCES.LIVE);
      playback = reducePlayback(playback, { type: "seek", index: events.length - 1 });
      const isStopRequested = stopRequestedRunId === runId;
      liveStreamState = {
        status: isStopRequested ? RUN_STATUSES.STOP_REQUESTED : RUN_STATUSES.RUNNING,
        message: isStopRequested
          ? `已请求停止，正在收束第 ${events.length} 条安全边界事件...`
          : `正在接收第 ${events.length} 条事件...`,
      };
      render();
    }

    if (events.length === 0) {
      throw new Error("Live event stream returned no events.");
    }

    currentLiveEvents = [...events];
    const stoppedBeforeCompletion =
      abortController.signal.aborted ||
      stopRequestedRunId === runId ||
      liveStreamState.status === RUN_STATUSES.STOP_REQUESTED ||
      liveStreamState.status === RUN_STATUSES.STOPPED_SAFE;
    const finalEvent = events.at(-1);
    const runFailedEvent =
      finalEvent?.type === SANDBOX_EVENT_TYPES.RUN_FAILED ? finalEvent : null;
    if (
      !stoppedBeforeCompletion &&
      !runFailedEvent &&
      finalEvent?.type !== SANDBOX_EVENT_TYPES.RUN_COMPLETED
    ) {
      throw new Error(
        `Live event stream ended before run_completed; last event was ${finalEvent?.type || "unknown"}.`,
      );
    }
    if (
      stopRequestedRunId === runId ||
      liveStreamState.status === RUN_STATUSES.STOP_REQUESTED ||
      liveStreamState.status === RUN_STATUSES.STOPPED_SAFE
    ) {
      pendingArchive = buildPendingArchive({
        runId,
        status: RUN_STATUSES.STOPPED_SAFE,
        stopReason: "user_stop",
      });
      liveStreamState = {
        status: RUN_STATUSES.STOPPED_SAFE,
        message: "Backend stopped at a safe boundary; you can save this run now.",
      };
      archiveState = pendingArchive
        ? {
            status: "pending",
            message: `Safe archive candidate ready: ${pendingArchive.safeBoundary.completedRoundCount} completed round(s).`,
          }
        : {
            status: "idle",
            message: "Stop completed, but there is no replayable safe event to archive.",
          };
    } else if (runFailedEvent) {
      handleLiveRunFailedEvent(runFailedEvent, { runId, runConfig });
    } else if (!stoppedBeforeCompletion) {
      liveStreamState = {
        status: RUN_STATUSES.COMPLETED,
        message: `Live event stream 已载入 ${events.length} 条事件。`,
      };
      archiveState = {
        status: "idle",
        message: "本轮已正常完成；如需保留，请后续使用摘要导出或手动停止存档。",
      };
    }
  } catch (error) {
    const stoppedBeforeCompletion =
      abortController.signal.aborted ||
      liveStreamState.status === RUN_STATUSES.STOP_REQUESTED ||
      liveStreamState.status === RUN_STATUSES.STOPPED_SAFE;
    if (isAbortError(error) && stoppedBeforeCompletion) {
      if (pendingArchive) {
        archiveState = {
          status: "pending",
          message: "本地搜索已停止，可以选择存档或不存档。",
        };
      }
    } else {
      const message = error instanceof Error ? error.message : String(error);
      liveRunIssue = createLiveRunIssue(error, {
        secretValues: [runConfig.provider.apiKey],
      });
      playback = {
        ...playback,
        status: PLAYBACK_STATUS.PAUSED,
      };
      stopAutoplay();
      liveStreamState = {
        status: RUN_STATUSES.FAILED,
        message: liveRunIssue.message,
      };
      scheduleDisconnectAutoArchive({ runId, message: liveRunIssue.message });
    }
  } finally {
    if (activeLiveAbortController === abortController) {
      activeLiveAbortController = null;
    }
  }

  render();
}

function handleLiveRunFailedEvent(event, { runId, runConfig: failedRunConfig }) {
  const issue = event?.issue && typeof event.issue === "object" ? event.issue : {};
  const message =
    issue.message || event?.detail || event?.summary || "Live run failed before completion.";
  const error = new Error(message);
  error.name = "LiveRunFailedEvent";
  error.backendStatus = "run_failed";
  error.issueKind = typeof issue.kind === "string" ? issue.kind : "";

  liveRunIssue = createLiveRunIssue(error, {
    secretValues: [failedRunConfig.provider?.apiKey],
  });
  playback = {
    ...playback,
    status: PLAYBACK_STATUS.PAUSED,
  };
  stopAutoplay();
  liveStreamState = {
    status: RUN_STATUSES.FAILED,
    message: liveRunIssue.message,
  };
  archiveState = {
    status: "idle",
    message:
      "Live run failed before the next safe completed-round boundary; only completed rounds can be archived.",
  };

  if (liveRunIssue.kind === LIVE_RUN_ISSUE_KINDS.RUNTIME) {
    scheduleDisconnectAutoArchive({ runId, message: liveRunIssue.message });
  }
}

async function stopLiveRun() {
  stopAutoplay();
  clearDisconnectAutoArchiveTimer();

  if (!currentRunId || !activeLiveAbortController) {
    archiveState = {
      status: "idle",
      message: "当前没有正在搜索的 live run；暂停按钮只控制回放。",
    };
    render();
    return;
  }

  const runId = currentRunId;
  liveStreamState = {
    status: RUN_STATUSES.STOP_REQUESTED,
    message: "正在请求本地 runner 停在最近的安全边界...",
  };
  archiveState = {
    status: "stopping",
    message: "停止不是暂停回放：它会结束本地搜索，并只允许保存安全边界。",
  };
  render();

  const stopResult = await requestLiveRunStop(runId);
  if (!stopResult.ok) {
    activeLiveAbortController.abort();
    pendingArchive = buildPendingArchive({
      runId,
      status: RUN_STATUSES.STOPPED_SAFE,
      stopReason: "user_stop",
    });
    liveStreamState = {
      status: RUN_STATUSES.STOPPED_SAFE,
      message: `Stop request failed; the browser stopped reading as a fallback: ${stopResult.message}`,
    };
    archiveState = pendingArchive
      ? {
          status: "pending",
          message: `Fallback archive candidate ready: ${pendingArchive.safeBoundary.completedRoundCount} completed round(s).`,
        }
      : {
          status: "error",
          message: "Stop request failed and no safe replay event is available for archiving.",
        };
    render();
    return;
  }

  stopRequestedRunId = runId;
  liveStreamState = {
    status: RUN_STATUSES.STOP_REQUESTED,
    message: "Stop request accepted; waiting for the backend to finish the current safe boundary.",
  };
  archiveState = {
    status: "stopping",
    message: "The backend is still collecting the current complete round before archive is offered.",
  };
  render();
}

async function savePendingArchive() {
  if (!pendingArchive) {
    archiveState = {
      status: "idle",
      message: "当前没有等待确认的存档。",
    };
    render();
    return;
  }

  const label = elements.archiveLabelInput.value.trim();
  const archive = {
    ...pendingArchive,
    label: label || pendingArchive.label,
  };
  try {
    const result = await saveArchive(archive);
    pendingArchive = null;
    selectedArchiveId = result.archive?.archiveId || archive.archiveId;
    elements.archiveLabelInput.value = "";
    liveStreamState = {
      status: RUN_STATUSES.ARCHIVED,
      message: "Archive saved; this run can be replayed or resumed from its safe boundary.",
    };
    archiveState = {
      status: "saved",
      message: `已保存${archiveStorageLabel(result)}存档：${result.archive?.label || archive.label}`,
    };
    await refreshArchiveList();
  } catch (error) {
    archiveState = {
      status: "error",
      message: error instanceof Error ? error.message : String(error),
    };
    render();
  }
}

function discardPendingArchive() {
  pendingArchive = null;
  archiveState = {
    status: "discarded",
    message: "已放弃本轮存档，当前回放仍保留在页面里。",
  };
  render();
}

async function refreshArchiveList() {
  try {
    savedArchives = await listArchives();
    if (selectedArchiveId && !savedArchives.some((archive) => archive.archiveId === selectedArchiveId)) {
      selectedArchiveId = "";
    }
  } catch (error) {
    savedArchives = [];
    selectedArchiveId = "";
    archiveState = {
      status: "error",
      message: error instanceof Error ? error.message : String(error),
    };
  }
  render();
}

async function importSelectedArchive({ continueSearch }) {
  const archiveId = selectedArchiveId || elements.archiveSelect.value;
  const selectedSummary = savedArchives.find((archive) => archive.archiveId === archiveId);
  if (!archiveId) {
    archiveState = {
      status: "idle",
      message: "请先选择一个存档。",
    };
    render();
    return;
  }

  try {
    const archive = await loadArchive(archiveId);
    restoreArchivePlayback(archive);
    if (continueSearch) {
      let resumePlan = null;
      if (selectedSummary?.storage === "backend") {
        archiveState = {
          status: "checking",
          message: "正在向后端确认这个存档的安全续跑边界...",
        };
        render();
        resumePlan = await requestArchiveResumePlan(archiveId);
        if (!resumePlan.ok) {
          throw new Error(resumePlan.message || "Backend resume plan failed.");
        }
      } else {
        resumePlan = {
          ok: true,
          storage: selectedSummary?.storage || "local",
          safeBoundary: archive.safeBoundary,
          requiresFreshCredentials: true,
        };
      }
      const restoredConfig = normalizeArchiveRunConfig(archive.sessionSnapshot?.config);
      if (restoredConfig) {
        runConfig = restoredConfig;
        writeRunConfigToInputs(runConfig);
        configCheckRequested = true;
        providerCheckState = createProviderCheckState();
      }
      archiveState = {
        status: archive.resume?.canContinue ? "continue_ready" : "replay_only",
        message: archive.resume?.canContinue
          ? `${archiveStorageLabel(resumePlan)}存档已确认安全边界：${resumePlan.safeBoundary?.completedRoundCount ?? archive.safeBoundary?.completedRoundCount ?? 0} 个完整轮次。请重新做 provider-check 后继续真实运行。`
          : "这个存档没有完整轮次，只适合回看。",
      };
      liveStreamState = {
        status: RUN_STATUSES.RESUMING,
        message:
          selectedSummary?.storage === "backend"
            ? "Backend resume plan is ready; fresh credentials are still required."
            : "Local demo archive is ready for replay; backend archive is required for strict resume.",
      };
    } else {
      archiveState = {
        status: RUN_STATUSES.ARCHIVED,
        message: `已导入回看：${archive.label || archive.archiveId}`,
      };
      liveStreamState = {
        status: "restored",
        message: `已从存档恢复 ${archive.playback.events.length} 条事件。`,
      };
    }
  } catch (error) {
    archiveState = {
      status: "error",
      message: error instanceof Error ? error.message : String(error),
    };
  }
  render();
}

function restoreArchivePlayback(archive) {
  replacePlaybackEvents(archive.playback.events, RUN_SOURCES.LIVE);
  currentLiveEvents = [...archive.playback.events];
  if (archive.playback.events.length > 0) {
    playback = reducePlayback(playback, {
      type: "seek",
      index: archive.playback.events.length - 1,
    });
  }
  playbackSource = RUN_SOURCES.LIVE;
  pendingArchive = null;
  liveRunIssue = null;
}

function buildPendingArchive({ runId, status, stopReason }) {
  if (currentLiveEvents.length === 0) {
    return null;
  }
  try {
    return createArchiveCandidate({
      runId,
      runConfig,
      events: currentLiveEvents,
      label: `${runConfig.product.name || "沙盘"} · ${new Date().toLocaleString()}`,
      status,
      stopReason,
    });
  } catch (error) {
    archiveState = {
      status: "error",
      message: error instanceof Error ? error.message : String(error),
    };
    return null;
  }
}

function archiveStorageLabel(archiveLike) {
  const storage = archiveLike?.storage;
  if (storage === "backend") {
    return "后端真实";
  }
  if (storage === "local") {
    return "本地演示";
  }
  return "来源未知";
}

function scheduleDisconnectAutoArchive({ runId, message }) {
  clearDisconnectAutoArchiveTimer();
  const disconnectedAt = Date.now();
  const disconnectedRunConfig = JSON.parse(JSON.stringify(runConfig));
  archiveState = {
    status: "disconnect_waiting",
    message: `API disconnected after ${API_DISCONNECT_RECONNECT_ATTEMPTS} provider retry attempts: ${message}. Waiting ${API_DISCONNECT_FINAL_WAIT_MS / 1000} seconds before the final safe-boundary archive check.`,
  };
  disconnectArchiveTimer = window.setTimeout(() => {
    const disconnectedMs = Date.now() - disconnectedAt;
    if (!shouldAutoArchiveDisconnect({ disconnectedMs, timeoutMs: API_DISCONNECT_FINAL_WAIT_MS })) {
      return;
    }
    void confirmProviderThenArchiveDisconnect({
      runId,
      runConfig: disconnectedRunConfig,
      disconnectedMs,
      message,
    });
  }, API_DISCONNECT_FINAL_WAIT_MS);
  render();
}

async function confirmProviderThenArchiveDisconnect({ runId, runConfig, disconnectedMs, message }) {
  providerCheckState = createProviderCheckState({
    status: PROVIDER_CHECK_STATUS.CHECKING,
    ok: false,
    message: "Rechecking provider before disconnect auto-archive...",
  });
  archiveState = {
    status: "disconnect_waiting",
    message: "Final provider check is running before safe-boundary archive.",
  };
  render();

  providerCheckState = await requestProviderCheck(runConfig);
  if (providerCheckAllowsLiveRun(providerCheckState)) {
    archiveState = {
      status: "idle",
      message: "Provider responded after the final wait. The interrupted stream was not auto-archived.",
    };
    liveStreamState = {
      status: RUN_STATUSES.FAILED,
      message: "Provider is reachable again, but the prior live stream already ended. Start a new run or continue from a saved boundary.",
    };
    render();
    return;
  }

  await autoArchiveAfterDisconnect({
    runId,
    disconnectedMs,
    message: `${message}; final provider check failed: ${providerCheckState.message}`,
  });
}

async function autoArchiveAfterDisconnect({ runId, disconnectedMs, message }) {
  try {
    const backendResult = await requestApiDisconnectAutoArchive({
      runId,
      disconnectedSeconds: disconnectedMs / 1000,
      timeoutSeconds: API_DISCONNECT_FINAL_WAIT_MS / 1000,
      message,
    });

    if (backendResult.ok && backendResult.status === "auto_archived" && backendResult.archive) {
      pendingArchive = null;
      selectedArchiveId = backendResult.archive.archiveId;
      archiveState = {
        status: "saved",
        message: `API disconnected; backend auto-archived the latest safe boundary as ${backendResult.archive.label || backendResult.archive.archiveId}.`,
      };
      await refreshArchiveList();
      return;
    }

    const archive = buildPendingArchive({
      runId,
      status: "auto_archived",
      stopReason: "api_disconnect_timeout",
    });
    if (!archive) {
      archiveState = {
        status: "idle",
        message: backendResult.message || "API disconnected, but no safe event boundary is available for archiving.",
      };
      render();
      return;
    }

    pendingArchive = archive;
    const fallbackResult = await saveArchive(archive);
    pendingArchive = null;
    selectedArchiveId = fallbackResult.archive?.archiveId || archive.archiveId;
    archiveState = {
      status: "saved",
      message: `API disconnected; saved ${archiveStorageLabel(fallbackResult)} fallback archive at the latest safe boundary.`,
    };
    await refreshArchiveList();
  } catch (error) {
    archiveState = {
      status: "error",
      message: error instanceof Error ? error.message : String(error),
    };
    render();
  }
}

function clearDisconnectAutoArchiveTimer() {
  if (disconnectArchiveTimer) {
    window.clearTimeout(disconnectArchiveTimer);
    disconnectArchiveTimer = null;
  }
}

function isAbortError(error) {
  return error instanceof DOMException
    ? error.name === "AbortError"
    : error instanceof Error && error.name === "AbortError";
}

function apiStatusText(validation) {
  if (runConfig.source === RUN_SOURCES.FIXTURE) {
    return "API 示例模式";
  }

  if (liveStreamState.status === RUN_STATUSES.CHECKING_PROVIDER) {
    return "Provider 检测中";
  }

  if (liveStreamState.status === RUN_STATUSES.STARTING) {
    return "Live stream 连接中";
  }

  if (liveStreamState.status === RUN_STATUSES.RUNNING) {
    return "Live stream 接收中";
  }

  if (liveStreamState.status === RUN_STATUSES.STOP_REQUESTED) {
    return "Live stream 停止中";
  }

  if (liveStreamState.status === RUN_STATUSES.STOPPED_SAFE) {
    return "Live stream 已安全停止";
  }

  if (liveStreamState.status === RUN_STATUSES.COMPLETED) {
    return "Live stream 已完成";
  }

  if (liveStreamState.status === RUN_STATUSES.ARCHIVED) {
    return "存档已导入或保存";
  }

  if (liveStreamState.status === RUN_STATUSES.RESUMING) {
    return "续跑待检测";
  }

  if (liveStreamState.status === RUN_STATUSES.FAILED) {
    return "Live stream 出错";
  }

  if (providerCheckState.status === PROVIDER_CHECK_STATUS.CHECKING) {
    return "Provider 检测中";
  }

  if (providerCheckState.status === PROVIDER_CHECK_STATUS.CONNECTED) {
    return "API 已连接";
  }

  if (providerCheckState.status === PROVIDER_CHECK_STATUS.FAILED) {
    return "API 检测失败";
  }

  return validation.ready ? "API 待检测" : "API 配置待补";
}

function render() {
  const snapshot = createPlaybackSnapshot(playback.events, playback.index);
  const currentEvent = snapshot.currentEvent;
  const currentStrategy = snapshot.strategy;
  const currentFamily = snapshot.family;
  const currentSearch = snapshot.search;
  const currentInternalSearch = snapshot.internalSearch;
  const configValidation = validateRunConfig(runConfig);
  const configPreview = buildRunConfigPreview(runConfig);

  elements.playbackState.textContent = playback.status;
  elements.brandSubtitle.textContent = configPreview.sourceLabel;
  elements.apiStatus.textContent = apiStatusText(configValidation);
  elements.roundStatus.textContent = currentEvent?.round ? `Round ${currentEvent.round}` : "待机";
  elements.eventRound.textContent = currentEvent?.round ? `Round ${currentEvent.round}` : "Round -";
  elements.eventKind.textContent = currentEvent ? labelForEvent(currentEvent.type) : "待机";
  elements.stageHeadline.textContent = currentEvent?.headline || "等待回放开始";
  elements.eventHeadline.textContent = currentEvent?.headline || "准备就绪";
  elements.eventSummary.textContent =
    currentEvent?.summary || "点击播放或单步，查看 agent 如何围着策略搜索互动。";
  elements.eventDetail.textContent = currentEvent?.detail || "";
  elements.speakerRole.textContent = actorName(currentEvent) || "待机";

  renderStrategy(currentStrategy, currentFamily);
  renderFeedback(currentEvent);
  renderSearch(currentSearch, currentFamily, currentInternalSearch);
  renderLiveRunIssue();
  renderStrategyComparison();
  renderTimeline();
  renderConfigState(configValidation, configPreview);

  scene.setPlaybackView({
    activeAgentId: currentEvent?.actorId,
    activeAgentRole: currentEvent?.actorRole,
    bubble: currentEvent?.bubble,
    actions: currentStrategy?.actions,
  });
}

function exportRunSummary() {
  const preview = buildRunConfigPreview(runConfig);
  const markdown = buildRunSummaryMarkdown(playback.events, {
    productLabel: preview.productLabel,
    sourceLabel: playbackSource === RUN_SOURCES.LIVE ? "真实搜索 / 存档事件流" : preview.sourceLabel,
  });
  const fileName = `marketing-sandbox-summary-${new Date().toISOString().slice(0, 10)}.md`;

  downloadTextFile(fileName, markdown);
  elements.exportStatus.textContent = `已导出 ${fileName}。`;
}

function downloadTextFile(fileName, text) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/markdown;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

function renderLiveRunIssue() {
  elements.runIssuePanel.hidden = !liveRunIssue;
  elements.runIssuePanel.dataset.state = liveRunIssue?.kind || "idle";
  elements.runIssueKind.textContent = liveRunIssue?.kind || "issue";
  elements.runIssueTitle.textContent = liveRunIssue?.title || "";
  elements.runIssueExplanation.textContent = liveRunIssue?.explanation || "";
  elements.runIssueMessage.textContent = liveRunIssue?.message || "";
}

function renderStrategyComparison() {
  const comparison = createStrategyComparison(playback.events, comparisonSelection.leftId, comparisonSelection.rightId);
  const selectedLeftId = comparison.left?.id || "";
  const selectedRightId = comparison.right?.id || "";
  comparisonSelection = {
    leftId: selectedLeftId,
    rightId: selectedRightId,
  };

  renderComparisonSelect(elements.compareLeftSelect, comparison.strategies, selectedLeftId);
  renderComparisonSelect(elements.compareRightSelect, comparison.strategies, selectedRightId);
  elements.comparisonOutput.replaceChildren();

  if (!comparison.left || !comparison.right) {
    elements.comparisonOutput.append(createParagraph("当前事件流还没有可比较的策略提案。", "empty-copy"));
    return;
  }

  const grid = document.createElement("div");
  grid.className = "comparison-grid";
  grid.append(
    createComparisonCard("方案 A", comparison.left),
    createComparisonCard("方案 B", comparison.right),
  );
  elements.comparisonOutput.append(grid);

  const shared = document.createElement("article");
  shared.className = "shared-persona";
  const title = document.createElement("h3");
  title.textContent = "同一 persona 反应";
  shared.append(title);
  if (comparison.sharedPersonaReactions.length === 0) {
    shared.append(createParagraph("这两个方案暂时没有同一 persona 的成对反馈。", "empty-copy"));
  } else {
    for (const reaction of comparison.sharedPersonaReactions) {
      const item = document.createElement("p");
      item.textContent = `${reaction.actorName}：A ${reaction.left.summary} / B ${reaction.right.summary}`;
      shared.append(item);
    }
  }
  elements.comparisonOutput.append(shared);
}

function renderComparisonSelect(select, strategies, selectedId) {
  select.replaceChildren();
  if (strategies.length === 0) {
    const option = document.createElement("option");
    option.textContent = "等待策略事件";
    option.value = "";
    select.append(option);
    select.disabled = true;
    return;
  }

  select.disabled = false;
  for (const strategy of strategies) {
    const option = document.createElement("option");
    option.value = strategy.id;
    option.textContent = strategy.label;
    option.selected = strategy.id === selectedId;
    select.append(option);
  }
}

function createComparisonCard(label, snapshot) {
  const card = document.createElement("article");
  card.className = "comparison-card";
  const heading = document.createElement("h3");
  heading.textContent = `${label} · Round ${snapshot.round}`;
  const strategy = document.createElement("strong");
  strategy.textContent = snapshot.strategy.name || "未命名策略";
  const family = createParagraph(
    `Family：${snapshot.family?.name || snapshot.family?.id || snapshot.strategy.familyId || "未记录"}`,
  );
  const intent = createParagraph(snapshot.strategy.intent || "本轮没有意图说明。");
  const actionList = document.createElement("ul");
  actionList.className = "comparison-actions";
  for (const action of snapshot.strategy.actions || []) {
    const item = document.createElement("li");
    item.textContent = `${action.category}：${action.note}`;
    actionList.append(item);
  }
  if (actionList.childElementCount === 0) {
    const item = document.createElement("li");
    item.textContent = "未记录动作拆解。";
    actionList.append(item);
  }
  const metric = createParagraph(
    snapshot.search?.internalMetrics?.reward === undefined
      ? "内部 reward：未记录"
      : `内部 reward：${formatMetric(snapshot.search.internalMetrics.reward)}`,
    "comparison-metric",
  );
  const reaction = createParagraph(
    snapshot.consumerFeedback[0]
      ? `${snapshot.consumerFeedback[0].actorName}：${snapshot.consumerFeedback[0].summary}`
      : "本轮还没有消费者反应。",
  );
  const risk = createParagraph(
    snapshot.critique?.mainRisk ? `风险：${snapshot.critique.mainRisk}` : "风险：未记录",
  );
  card.append(heading, strategy, family, intent, actionList, metric, reaction, risk);
  return card;
}

function createParagraph(text, className = "") {
  const paragraph = document.createElement("p");
  paragraph.textContent = text;
  if (className) {
    paragraph.className = className;
  }
  return paragraph;
}

function handleConfigInput(event) {
  if (!event.target.closest(".config-rail")) {
    return;
  }
  if (event.target.closest(".archive-panel")) {
    return;
  }

  const previousSource = runConfig.source;
  const targetId = event.target.id || "";
  configCheckRequested = configCheckRequested && targetId !== "api-key-input";
  runConfig = readRunConfigFromInputs();
  if (PROVIDER_CHECK_INPUT_IDS.has(targetId) || previousSource !== runConfig.source) {
    providerCheckState = createProviderCheckState();
  }
  if (runConfig.source === RUN_SOURCES.FIXTURE && previousSource !== RUN_SOURCES.FIXTURE) {
    resetFixturePlayback();
  }
  render();
}

function writeRunConfigToInputs(config) {
  checkNamedValue("run-source", config.source);
  elements.providerSelect.value = config.provider.id;
  elements.baseUrlInput.value = config.provider.baseUrl;
  elements.apiKeyInput.value = config.provider.apiKey;
  elements.backendDefaultsInput.checked = config.provider.useBackendDefaults;
  elements.defaultModelInput.value = config.provider.defaultModel;
  elements.decisionModelInput.value = config.models.decision;
  elements.consumerModelInput.value = config.models.consumers;
  elements.synthesizerModelInput.value = config.models.synthesizer;
  elements.criticModelInput.value = config.models.critic;
  elements.productNameInput.value = config.product.name;
  elements.brandInput.value = config.product.brand;
  elements.productFactsInput.value = config.product.facts;
  elements.goalInput.value = config.product.goal;
  setCheckedValues("persona-choice", config.personaIds);
  checkNamedValue("scenario-choice", config.scenarioId);
  setCheckedValues("action-category", config.actionCategories);
  elements.ucbToggle.checked = config.search.useUcb;
  elements.roundsInput.value = config.search.rounds;
  elements.candidatesInput.value = config.search.candidatesPerRound;
  setCheckedValues("family-choice", config.search.familyIds);
}

function readRunConfigFromInputs() {
  return {
    source: checkedValue("run-source"),
    provider: {
      id: elements.providerSelect.value,
      baseUrl: elements.baseUrlInput.value,
      apiKey: elements.apiKeyInput.value,
      useBackendDefaults: elements.backendDefaultsInput.checked,
      defaultModel: elements.defaultModelInput.value,
    },
    models: {
      decision: elements.decisionModelInput.value,
      consumers: elements.consumerModelInput.value,
      synthesizer: elements.synthesizerModelInput.value,
      critic: elements.criticModelInput.value,
    },
    product: {
      name: elements.productNameInput.value,
      brand: elements.brandInput.value,
      facts: elements.productFactsInput.value,
      goal: elements.goalInput.value,
    },
    personaIds: checkedValues("persona-choice"),
    scenarioId: checkedValue("scenario-choice"),
    actionCategories: checkedValues("action-category"),
    search: {
      useUcb: elements.ucbToggle.checked,
      rounds: readInteger(elements.roundsInput.value),
      candidatesPerRound: readInteger(elements.candidatesInput.value),
      familyIds: checkedValues("family-choice"),
    },
  };
}

function normalizeArchiveRunConfig(archiveConfig) {
  if (!archiveConfig || typeof archiveConfig !== "object") {
    return null;
  }
  const defaults = createRunConfig();
  return {
    ...defaults,
    ...archiveConfig,
    source: RUN_SOURCES.LIVE,
    provider: {
      ...defaults.provider,
      ...(archiveConfig.provider || {}),
      apiKey: "",
    },
    models: {
      ...defaults.models,
      ...(archiveConfig.models || {}),
      ...(archiveConfig.provider?.models || {}),
    },
    product: {
      ...defaults.product,
      ...(archiveConfig.product || {}),
    },
    personaIds: Array.isArray(archiveConfig.personaIds) ? archiveConfig.personaIds : defaults.personaIds,
    scenarioId: archiveConfig.scenarioId || defaults.scenarioId,
    actionCategories: Array.isArray(archiveConfig.actionCategories)
      ? archiveConfig.actionCategories
      : defaults.actionCategories,
    search: {
      ...defaults.search,
      ...(archiveConfig.search || {}),
    },
  };
}

function configReadinessTitle(validation, liveProviderReady) {
  if (runConfig.source === RUN_SOURCES.FIXTURE) {
    return "示例回放可直接播放";
  }
  if (!validation.ready) {
    return "真实运行配置还没齐";
  }
  if (providerCheckState.status === PROVIDER_CHECK_STATUS.CHECKING) {
    return "正在检测真实 provider";
  }
  if (liveProviderReady) {
    return "真实 provider 已连接";
  }
  if (providerCheckState.status === PROVIDER_CHECK_STATUS.FAILED) {
    return "Provider 检测失败";
  }
  return "真实运行配置已齐，等待 provider-check";
}

function providerCheckMessage() {
  const suffix = providerCheckState.modelStatus ? ` (${providerCheckState.modelStatus})` : "";
  return `${providerCheckState.message}${suffix}`;
}

function renderConfigState(validation, preview) {
  elements.runSourceBadge.textContent = runConfig.source;
  elements.personaCount.textContent = `${runConfig.personaIds.length} selected`;
  elements.baseUrlInput.disabled = runConfig.provider.useBackendDefaults;
  elements.apiKeyInput.disabled = runConfig.provider.useBackendDefaults;
  const waitingForLiveEvents = runConfig.source === RUN_SOURCES.LIVE && playbackSource !== RUN_SOURCES.LIVE;
  const providerChecking = providerCheckState.status === PROVIDER_CHECK_STATUS.CHECKING;
  const liveProviderReady =
    runConfig.source !== RUN_SOURCES.LIVE || providerCheckAllowsLiveRun(providerCheckState);
  const liveBusy = isRunBusyStatus(liveStreamState.status);
  elements.playButton.disabled = liveBusy || waitingForLiveEvents;
  elements.stepButton.disabled = liveBusy || waitingForLiveEvents;
  elements.liveRunButton.disabled =
    runConfig.source !== RUN_SOURCES.LIVE || !validation.ready || !liveProviderReady || liveBusy || providerChecking;
  elements.stopRunButton.disabled = !activeLiveAbortController || !currentRunId || !canStopRun(liveStreamState.status);
  elements.checkConfigButton.disabled = liveBusy || providerChecking;
  elements.checkConfigButton.textContent = providerChecking ? "检测中..." : "配置预检";
  elements.liveRunButton.dataset.state = liveStreamState.status;
  elements.liveRunButton.textContent = isRunBusyStatus(liveStreamState.status) ? "接收中" : "真实运行";
  elements.stopRunButton.dataset.state = liveStreamState.status;
  elements.loadFixtureButton.dataset.active = String(playbackSource === RUN_SOURCES.FIXTURE);
  document.querySelector("#family-choices").dataset.disabled = String(!runConfig.search.useUcb);

  elements.configReadiness.replaceChildren();
  elements.configReadiness.dataset.ready = String(validation.ready && liveProviderReady);
  const title = document.createElement("strong");
  title.textContent = configReadinessTitle(validation, liveProviderReady);
  elements.configReadiness.append(title);

  if (validation.errors.length > 0 && (configCheckRequested || runConfig.source === RUN_SOURCES.LIVE)) {
    const list = document.createElement("ul");
    for (const error of validation.errors) {
      const item = document.createElement("li");
      item.textContent = error;
      list.append(item);
    }
    elements.configReadiness.append(list);
  }

  for (const notice of validation.notices) {
    const item = document.createElement("p");
    item.textContent = notice;
    elements.configReadiness.append(item);
  }

  if (runConfig.source === RUN_SOURCES.LIVE) {
    const providerItem = document.createElement("p");
    providerItem.className = "provider-check-message";
    providerItem.dataset.state = providerCheckState.status;
    providerItem.textContent = providerCheckMessage();
    elements.configReadiness.append(providerItem);
  }

  if (runConfig.source === RUN_SOURCES.LIVE || playbackSource === RUN_SOURCES.LIVE) {
    const item = document.createElement("p");
    item.className = "live-stream-message";
    item.dataset.state = liveStreamState.status;
    item.textContent = liveStreamState.message;
    elements.configReadiness.append(item);
  }

  renderConfigPreview(preview);
  renderArchivePanel();
}

function renderArchivePanel() {
  elements.archiveStateBadge.textContent = archiveState.status;
  elements.archiveStatus.textContent = archiveState.message;
  elements.archiveStatus.dataset.state = archiveState.status;
  elements.saveArchiveButton.disabled = !pendingArchive;
  elements.discardArchiveButton.disabled = !pendingArchive;
  elements.archiveSelect.replaceChildren();

  if (savedArchives.length === 0) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "暂无存档";
    elements.archiveSelect.append(option);
  } else {
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "选择一个存档";
    elements.archiveSelect.append(placeholder);
    for (const archive of savedArchives) {
      const option = document.createElement("option");
      option.value = archive.archiveId;
      option.textContent = `${archive.label || archive.archiveId} · ${archive.completedRoundCount || 0} 轮 · ${archiveStorageLabel(archive)}`;
      option.selected = archive.archiveId === selectedArchiveId;
      elements.archiveSelect.append(option);
    }
  }

  const hasArchiveSelection = Boolean(selectedArchiveId);
  const selectedSummary = savedArchives.find((archive) => archive.archiveId === selectedArchiveId);
  elements.importArchiveButton.disabled = savedArchives.length === 0 || !hasArchiveSelection;
  elements.continueArchiveButton.disabled =
    savedArchives.length === 0 || !hasArchiveSelection || !selectedSummary?.canContinue;
  elements.archiveResumeNote.textContent = selectedSummary
    ? selectedSummary.canContinue
      ? `${archiveStorageLabel(selectedSummary)}存档有完整轮次，可以恢复到安全边界后续跑。`
      : `${archiveStorageLabel(selectedSummary)}存档只能回看，不能直接续跑。`
    : "存档不会保存明文 API Key；续跑时需要重新提供可用凭据。";
}

function renderConfigPreview(preview) {
  elements.configPreview.replaceChildren();
  appendConfigPreview("来源", preview.sourceLabel);
  appendConfigPreview("Provider", preview.providerLabel);
  appendConfigPreview("密钥", preview.credentialLabel);
  appendConfigPreview("模型", preview.modelLabel);
  appendConfigPreview("产品", preview.productLabel);
  appendConfigPreview("人群", preview.personaLabel);
  appendConfigPreview("场景", preview.scenarioLabel);
  appendConfigPreview("动作", preview.actionLabel);
  appendConfigPreview("搜索", preview.searchLabel);
}

function renderStrategy(strategy, family) {
  elements.familyState.textContent = family?.state || strategy?.familyId || "未选择";
  elements.strategyName.textContent = strategy?.name || "等待 DecisionAgent 出招";
  elements.strategyIntent.textContent = strategy?.intent || family?.note || "策略动作会在这里落回动作集边界。";
  elements.actionList.replaceChildren();

  for (const action of strategy?.actions || []) {
    const item = document.createElement("article");
    item.className = "action-chip";
    item.innerHTML = `<strong>${action.category}</strong><span>${action.note}</span>`;
    elements.actionList.append(item);
  }
}

function renderFeedback(event) {
  elements.feedbackDetails.replaceChildren();
  const groups = [
    ["第一印象", event?.feedback?.firstImpression],
    ["主要阻力", event?.feedback?.barrier],
    ["复购感觉", event?.feedback?.repeat],
    ["竞品冲击", event?.feedback?.competitor],
    ["汇总", event?.synthesis?.moved],
    ["未被打动", event?.synthesis?.unmoved],
    ["下一步", event?.synthesis?.next || event?.critique?.next],
    ["风险", event?.critique?.mainRisk],
    ["边界", event?.critique?.boundary],
  ].filter(([, value]) => value);

  if (groups.length === 0) {
    appendDefinition("状态", "还没有消费者、总结者或批评者反馈。");
    return;
  }

  for (const [label, value] of groups) {
    appendDefinition(label, value);
  }
}

function renderSearch(search, family, internalSearch) {
  elements.searchNote.textContent = search?.note || family?.note || "还没有搜索更新。";
  elements.familyTrack.replaceChildren();

  for (const item of search?.families || (family ? [{ id: family.id, label: family.state, tone: "active" }] : [])) {
    const node = document.createElement("span");
    node.className = `family-node tone-${item.tone || "active"}`;
    node.innerHTML = `<strong>${item.id}</strong><small>${item.label}</small>`;
    elements.familyTrack.append(node);
  }

  renderSearchMetrics(search?.internalMetrics, internalSearch);
}

function renderSearchMetrics(metrics, internalSearch) {
  elements.searchMetrics.replaceChildren();

  if (!metrics && !internalSearch) {
    appendSearchMetric("内部指标", "暂无 reward / UCB 数据。");
    return;
  }

  if (internalSearch?.ucbScore) {
    appendSearchMetric("UCB 分数", formatScorePayload(internalSearch.ucbScore));
  }

  if (internalSearch?.generationIntent) {
    appendSearchMetric("生成意图", internalSearch.generationIntent);
  }

  if (internalSearch?.selectionReason) {
    appendSearchMetric("选择原因", internalSearch.selectionReason);
  }

  if (metrics) {
    appendSearchMetric("Reward", formatMetric(metrics.reward));
    appendSearchMetric("正向效用", formatMetric(metrics.positiveUtility));
    appendSearchMetric("风险扣减", formatMetric(metrics.riskPenalty));
    appendSearchMetric("更新前均值", formatMetric(metrics.stateBefore?.meanReward));
    appendSearchMetric("更新后均值", formatMetric(metrics.stateAfter?.meanReward));
    appendSearchMetric("Pull 次数", formatMetric(metrics.stateAfter?.pullCount));
    appendSearchMetric("正向拆解", formatMetricMap(metrics.positiveComponents));
    appendSearchMetric("风险拆解", formatMetricMap(metrics.riskComponents));
    appendSearchMetric("Caps", (metrics.appliedCaps || []).join(" / ") || "none");
    appendSearchMetric("映射说明", metrics.mappingNote || "内部 reward 映射。");
  }

  appendSearchMetric(
    "边界",
    metrics?.metricBoundary ||
      internalSearch?.metricBoundary ||
      "这些数字只解释搜索过程，不代表购买率、复购率或市场预测。",
  );
}

function renderTimeline() {
  elements.timeline.replaceChildren();

  playback.events.forEach((event, index) => {
    const marker = document.createElement("button");
    marker.type = "button";
    marker.className = "timeline-marker";
    marker.dataset.active = String(index === playback.index);
    marker.dataset.visited = String(index <= playback.index);
    marker.innerHTML = `<span>R${event.round || "-"}</span><strong>${labelForEvent(event.type)}</strong>`;
    marker.addEventListener("click", () => {
      stopAutoplay();
      dispatch({ type: "seek", index });
    });
    elements.timeline.append(marker);
  });
}

function appendDefinition(label, value) {
  const term = document.createElement("dt");
  term.textContent = label;
  const detail = document.createElement("dd");
  detail.textContent = value;
  elements.feedbackDetails.append(term, detail);
}

function appendConfigPreview(label, value) {
  const term = document.createElement("dt");
  term.textContent = label;
  const detail = document.createElement("dd");
  detail.textContent = value;
  elements.configPreview.append(term, detail);
}

function appendSearchMetric(label, value) {
  const term = document.createElement("dt");
  term.textContent = label;
  const detail = document.createElement("dd");
  detail.textContent = value;
  elements.searchMetrics.append(term, detail);
}

function actorName(event) {
  if (!event) {
    return "";
  }

  return event.actorName || event.actor_name || SAMPLE_AGENTS.find((agent) => agent.id === event.actorId)?.name || event.actorId;
}

function setCheckedValues(name, selectedValues) {
  const selectedSet = new Set(selectedValues);
  for (const input of document.querySelectorAll(`input[name="${name}"]`)) {
    input.checked = selectedSet.has(input.value);
  }
}

function checkNamedValue(name, selectedValue) {
  for (const input of document.querySelectorAll(`input[name="${name}"]`)) {
    input.checked = input.value === selectedValue;
  }
}

function checkedValues(name) {
  return [...document.querySelectorAll(`input[name="${name}"]:checked`)].map((input) => input.value);
}

function checkedValue(name) {
  return document.querySelector(`input[name="${name}"]:checked`)?.value || "";
}

function readInteger(value) {
  return Number.parseInt(value, 10);
}

function formatScorePayload(score) {
  if (score.value === null || score.value === undefined) {
    return score.display || "not recorded";
  }

  const display = score.display ? ` (${score.display})` : "";
  return `${formatMetric(score.value)}${display}`;
}

function formatMetric(value) {
  if (value === null || value === undefined) {
    return "未记录";
  }

  if (typeof value === "number") {
    return Number.isFinite(value) ? value.toFixed(3).replace(/\.?0+$/, "") : String(value);
  }

  return String(value);
}

function formatMetricMap(value) {
  if (!value || typeof value !== "object") {
    return "未记录";
  }

  const entries = Object.entries(value);
  if (entries.length === 0) {
    return "none";
  }

  return entries.map(([key, item]) => `${key}: ${formatMetric(item)}`).join(" / ");
}

function labelForEvent(type) {
  const labels = {
    [SANDBOX_EVENT_TYPES.RUN_STARTED]: "Run",
    [SANDBOX_EVENT_TYPES.ROUND_PROGRESS]: "Progress",
    [SANDBOX_EVENT_TYPES.ROUND_STARTED]: "Round",
    [SANDBOX_EVENT_TYPES.FAMILY_SELECTED]: "Family",
    [SANDBOX_EVENT_TYPES.STRATEGY_PROPOSED]: "Strategy",
    [SANDBOX_EVENT_TYPES.CONSUMER_FEEDBACK_READY]: "Consumer",
    [SANDBOX_EVENT_TYPES.FEEDBACK_SUMMARY_READY]: "Summary",
    [SANDBOX_EVENT_TYPES.CRITIQUE_READY]: "Critic",
    [SANDBOX_EVENT_TYPES.SEARCH_UPDATED]: "Search",
    [SANDBOX_EVENT_TYPES.ROUND_COMPLETED]: "Close",
    [SANDBOX_EVENT_TYPES.RUN_FAILED]: "Failed",
    [SANDBOX_EVENT_TYPES.RUN_COMPLETED]: "Done",
  };

  return labels[type] || type;
}
