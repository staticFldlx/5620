import { useId, useState } from "react"
import { ChevronDown, ChevronUp } from "lucide-react"
import { api } from "@/api/client"
import type { AssessmentResponse } from "@/api/types"
import { Button } from "@/components/ui/button"

// Mount with key={assessmentId} so changing student or review clears old evidence.
export function AssessmentAnswers({ assessmentId }: { assessmentId: string }) {
  const regionId = useId()
  const [open, setOpen] = useState(false)
  const [responses, setResponses] = useState<AssessmentResponse[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)

  async function load() {
    setLoading(true)
    setError(false)
    try {
      const session = await api.getAssessment(assessmentId)
      setResponses(session.responses || [])
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="assessment-answers" style={{ marginTop: 16 }}>
      <Button
        className="action secondary"
        aria-expanded={open}
        aria-controls={regionId}
        onClick={() => {
          setOpen(!open)
          if (!open && responses === null && !loading) void load()
        }}
      >
        {open ? "Hide questions & answers" : "View questions & answers"}
        {open ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
      </Button>
      {open && (
        <div
          id={regionId}
          role="region"
          aria-label="Assessment questions and answers"
          aria-busy={loading}
        >
          {loading ? (
            <p role="status">Loading saved answers…</p>
          ) : error ? (
            <div role="alert">
              <p>
                Could not load the saved questions and answers. Please try
                again.
              </p>
              <Button className="action secondary" onClick={() => void load()}>
                Retry
              </Button>
            </div>
          ) : responses?.length ? (
            responses.map((item) => (
              <article
                className="record-card"
                key={item.number}
                style={{ marginTop: 12, overflowWrap: "anywhere" }}
              >
                <h4>Question {item.number}</h4>
                <p style={{ whiteSpace: "pre-wrap" }}>
                  {item.prompt ||
                    "Question text is unavailable for this record."}
                </p>
                <strong>Submitted answer</strong>
                <p style={{ whiteSpace: "pre-wrap" }}>
                  {item.answer || "No answer text was saved."}
                </p>
              </article>
            ))
          ) : (
            <p>
              No saved question-and-answer details are available for this
              assessment. Older demo records may contain only an evaluation.
            </p>
          )}
        </div>
      )}
    </section>
  )
}
