export const aiActivities = {
  goal: {
    title: "Organising your learning goal",
    detail: "Turning your needs into a clear learning direction.",
  },
  assessment: {
    title: "Preparing your assessment",
    detail: "Creating questions for this assessment.",
  },
  answer: {
    title: "Reviewing your answer",
    detail: "Analysing your response and preparing the next step.",
  },
  plan: {
    title: "Preparing your learning plan",
    detail: "Working through your learning needs and requested changes.",
  },
  progress: {
    title: "Reviewing learning progress",
    detail: "Analysing assessment evidence and lesson feedback.",
  },
  recommendation: {
    title: "Preparing plan recommendations",
    detail: "Considering the learner’s progress and goals.",
  },
  briefing: {
    title: "Preparing your lesson briefing",
    detail: "Bringing together the learner’s context and lesson focus.",
  },
  material: {
    title: "Creating your teaching draft",
    detail: "Preparing material for the selected lesson.",
  },
  practice: {
    title: "Creating your practice",
    detail: "Preparing an activity for your learning stage.",
  },
  feedback: {
    title: "Preparing practice feedback",
    detail: "Reviewing your response and explaining the next steps.",
  },
  correction: {
    title: "Processing your correction request",
    detail: "The Technical Manager is preparing a response.",
  },
} as const

export type AIActivityKind = keyof typeof aiActivities
