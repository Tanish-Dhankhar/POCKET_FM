import { create } from 'zustand'

const initial = {
  mode: 'write', idea: '', transcript: '', sourceBlob: null, seriesId: null,
  questions: [], answers: [], confirm: null, demoReplay: false,
}

export const useWizard = create((set) => ({
  ...initial,
  set: (patch) => set(patch),
  reset: (mode = 'write') => set({ ...initial, mode }),
  answer: (index, answer) => set((state) => {
    const answers = [...state.answers]
    answers[index] = { question: state.questions[index]?.question || '', answer }
    return { answers }
  }),
}))
