export const RUN_STATUSES = Object.freeze({
  IDLE: "idle",
  CHECKING_PROVIDER: "checking_provider",
  STARTING: "starting",
  RUNNING: "running",
  STOP_REQUESTED: "stop_requested",
  STOPPED_SAFE: "stopped_safe",
  ARCHIVED: "archived",
  RESUMING: "resuming",
  COMPLETED: "completed",
  FAILED: "failed",
});

const RUN_STATUS_SET = new Set(Object.values(RUN_STATUSES));
const BUSY_STATUSES = new Set([
  RUN_STATUSES.CHECKING_PROVIDER,
  RUN_STATUSES.STARTING,
  RUN_STATUSES.RUNNING,
  RUN_STATUSES.STOP_REQUESTED,
  RUN_STATUSES.RESUMING,
]);

export function normalizeRunStatus(status, fallback = RUN_STATUSES.IDLE) {
  return RUN_STATUS_SET.has(status) ? status : fallback;
}

export function isRunBusyStatus(status) {
  return BUSY_STATUSES.has(normalizeRunStatus(status));
}

export function canStopRun(status) {
  const normalized = normalizeRunStatus(status);
  return normalized === RUN_STATUSES.STARTING || normalized === RUN_STATUSES.RUNNING;
}

export function isRunTerminalStatus(status) {
  const normalized = normalizeRunStatus(status);
  return [
    RUN_STATUSES.STOPPED_SAFE,
    RUN_STATUSES.ARCHIVED,
    RUN_STATUSES.COMPLETED,
    RUN_STATUSES.FAILED,
  ].includes(normalized);
}
