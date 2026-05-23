import { normalizeSandboxEvents } from "./event-schema.js";

export const PLAYBACK_STATUS = Object.freeze({
  IDLE: "idle",
  PLAYING: "playing",
  PAUSED: "paused",
  COMPLETE: "complete",
});

export function createPlaybackState(events) {
  return {
    events: normalizeSandboxEvents(events),
    index: -1,
    status: PLAYBACK_STATUS.IDLE,
  };
}

export function currentPlaybackEvent(state) {
  return state.index >= 0 ? state.events[state.index] : null;
}

export function visitedPlaybackEvents(state) {
  return state.index >= 0 ? state.events.slice(0, state.index + 1) : [];
}

export function reducePlayback(state, action) {
  switch (action.type) {
    case "play":
      return play(state);
    case "pause":
      return pause(state);
    case "step":
      return step(state);
    case "seek":
      return seek(state, action.index);
    case "reset":
      return reset(state);
    default:
      throw new TypeError(`Unknown playback action "${action.type}".`);
  }
}

function play(state) {
  if (state.status === PLAYBACK_STATUS.COMPLETE) {
    return { ...reset(state), status: PLAYBACK_STATUS.PLAYING };
  }

  return { ...state, status: PLAYBACK_STATUS.PLAYING };
}

function pause(state) {
  if (state.status === PLAYBACK_STATUS.IDLE || state.status === PLAYBACK_STATUS.COMPLETE) {
    return state;
  }

  return { ...state, status: PLAYBACK_STATUS.PAUSED };
}

function step(state) {
  const lastIndex = state.events.length - 1;
  if (state.index >= lastIndex) {
    return { ...state, status: PLAYBACK_STATUS.COMPLETE };
  }

  const nextIndex = state.index + 1;
  return {
    ...state,
    index: nextIndex,
    status:
      nextIndex === lastIndex
        ? PLAYBACK_STATUS.COMPLETE
        : state.status === PLAYBACK_STATUS.PLAYING
          ? PLAYBACK_STATUS.PLAYING
          : PLAYBACK_STATUS.PAUSED,
  };
}

function seek(state, index) {
  if (!Number.isInteger(index) || index < 0 || index >= state.events.length) {
    throw new RangeError(`Playback seek index "${index}" is out of range.`);
  }

  return {
    ...state,
    index,
    status: index === state.events.length - 1 ? PLAYBACK_STATUS.COMPLETE : PLAYBACK_STATUS.PAUSED,
  };
}

function reset(state) {
  return {
    ...state,
    index: -1,
    status: PLAYBACK_STATUS.IDLE,
  };
}
