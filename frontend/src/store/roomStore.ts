import { create } from 'zustand';

export type Turn = {
  speaker_id: string;
  text: string;
  start_timestamp_ms: number;
  duration_ms: number;
  was_interrupted: boolean;
  intent?: string;
};

type RoomState = {
  sessionId: string | null;
  topic: string | null;
  topicContext: string | null;
  transcript: Turn[];
  currentSpeaker: string | null;
  isHushed: boolean;
  setSessionData: (id: string, topic: string, context: string) => void;
  appendTurn: (turn: Turn) => void;
  setTranscript: (turns: Turn[]) => void;
  setCurrentSpeaker: (speaker: string | null) => void;
  setIsHushed: (hushed: boolean) => void;
  resetRoom: () => void;
};

export const useRoomStore = create<RoomState>((set) => ({
  sessionId: null,
  topic: null,
  topicContext: null,
  transcript: [],
  currentSpeaker: null,
  isHushed: false,
  setSessionData: (id, topic, context) => set({ sessionId: id, topic, topicContext: context }),
  appendTurn: (turn) => set((state) => ({ transcript: [...state.transcript, turn] })),
  setTranscript: (turns) => set({ transcript: turns }),
  setCurrentSpeaker: (speaker) => set({ currentSpeaker: speaker }),
  setIsHushed: (hushed) => set({ isHushed: hushed }),
  resetRoom: () => set({
    sessionId: null,
    topic: null,
    topicContext: null,
    transcript: [],
    currentSpeaker: null,
    isHushed: false,
  }),
}));
