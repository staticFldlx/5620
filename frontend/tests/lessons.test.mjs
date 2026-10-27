import test from "node:test"
import assert from "node:assert/strict"
import { upcomingLessons } from "../src/lib/lessons.ts"

test("next lessons exclude past and cancelled entries and sort chronologically", () => {
 const lessons = [
 {id:"past",status:"confirmed",starts_at:"2026-01-01T00:00:00Z"},
 {id:"later",status:"confirmed",starts_at:"2026-12-02T00:00:00Z"},
 {id:"next",status:"confirmed",starts_at:"2026-12-01T00:00:00Z"},
 {id:"cancelled",status:"cancelled",starts_at:"2026-11-01T00:00:00Z"},
 {id:"invalid",status:"confirmed",starts_at:"invalid"},
 ]
 assert.deepEqual(upcomingLessons(lessons,Date.parse("2026-10-28T00:00:00Z")).map(l=>l.id),["next","later"])
 assert.equal(lessons[0].id,"past")
})
