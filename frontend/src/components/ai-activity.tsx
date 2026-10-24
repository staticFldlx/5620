import { Sparkles } from "lucide-react"
import { aiActivities, type AIActivityKind } from "@/lib/ai-activity"

/** Request feedback only: no invented progress or simulated completion. */
export function AIActivity({ kind }: { kind: AIActivityKind }) {
  const { title, detail } = aiActivities[kind]
  return (
    <aside
      className="ai-activity"
      role="status"
      aria-live="polite"
      aria-atomic="true"
    >
      <span className="ai-activity-orbit" aria-hidden="true">
        <span className="thinking-orbit">
          <Sparkles size={20} />
        </span>
      </span>
      <div className="ai-activity-copy">
        <span className="ai-activity-label">AI at work</span>
        <strong>{title}</strong>
        <span>{detail}</span>
      </div>
      <span className="thinking-dots" aria-hidden="true">
        <i />
        <i />
        <i />
      </span>
      <span className="ai-activity-sweep" aria-hidden="true" />
    </aside>
  )
}
