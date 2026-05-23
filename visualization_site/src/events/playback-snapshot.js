export function createPlaybackSnapshot(events, index) {
  if (!Array.isArray(events)) {
    throw new TypeError("Playback snapshot needs an event array.");
  }

  const safeIndex = Number.isInteger(index) ? Math.min(index, events.length - 1) : -1;
  const currentIndex = safeIndex >= 0 ? safeIndex : -1;
  const visitedEvents = currentIndex >= 0 ? events.slice(0, currentIndex + 1) : [];

  return {
    currentEvent: currentIndex >= 0 ? events[currentIndex] : null,
    currentIndex,
    visitedEvents,
    strategy: findLatest(visitedEvents, (event) => event.strategy)?.strategy ?? null,
    family: findLatest(visitedEvents, (event) => event.family)?.family ?? null,
    search: findLatest(visitedEvents, (event) => event.search)?.search ?? null,
    internalSearch: findLatest(visitedEvents, (event) => event.internalSearch)?.internalSearch ?? null,
    feedbackEvent: findLatest(
      visitedEvents,
      (event) => event.feedback || event.synthesis || event.critique,
    ),
    completedRounds: completedRoundsFromEvents(visitedEvents),
  };
}

function completedRoundsFromEvents(events) {
  const rounds = [];
  const seen = new Set();
  for (const event of events) {
    if (event.type !== "round_completed" || seen.has(event.round)) {
      continue;
    }

    seen.add(event.round);
    rounds.push(event.round);
  }

  return rounds;
}

function findLatest(events, predicate) {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    if (predicate(events[index])) {
      return events[index];
    }
  }

  return null;
}
