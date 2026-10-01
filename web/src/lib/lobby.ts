import type { GuidedState } from "./guided";

export function lobbyStatus(state: GuidedState, myId: string | null, isHost: boolean) {
  const seats = state.seats ?? {};
  const hasPlayers = Object.keys(state.participants).length > 0;
  const waiting = Object.entries(seats).filter(([, seat]) => !seat.ready);
  const canBegin = hasPlayers && waiting.length === 0;
  const me = myId ? seats[myId] : undefined;
  let message: string;
  if (!hasPlayers) {
    message = "At least one person needs to play a character. Watching makes you a spectator; it does not start the adventure.";
  } else if (me && !me.ready) {
    message = me.watching
      ? "Click “I’m ready” to confirm you’re ready to watch."
      : myId && state.participants[myId]
        ? `You’ve chosen ${state.participants[myId].name}. Click “I’m ready” to continue.`
        : "Choose a character and click “I’m ready”, or choose to watch.";
  } else if (waiting.length > 0) {
    message = `Waiting for ${waiting.map(([, seat]) => seat.player_name).join(", ")} to choose a character or watch, and be ready.`;
  } else {
    message = isHost ? "Everyone is ready. Click “Begin adventure” to start." : "Everyone is ready. Your host can now begin the adventure.";
  }
  return { canBegin, message };
}
