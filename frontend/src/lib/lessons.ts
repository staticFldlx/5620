import type { Lesson } from "../api/types.ts"

export function upcomingLessons(lessons: Lesson[], now = Date.now()) {
  return lessons
    .filter((lesson) => lesson.status === "confirmed" && Date.parse(lesson.starts_at) >= now)
    .sort((a, b) => Date.parse(a.starts_at) - Date.parse(b.starts_at))
}
