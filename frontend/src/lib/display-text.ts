// Presentation only. Never use these labels as API identifiers or stored values.
export type DisplayReference = { id: string; label: string }
const uuid =
  /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi
const labels: Record<string, string> = {
  teaching_support: "Teaching Assistant",
  tech_operations: "Technical Manager",
  planning: "Course Consultant",
  coordinator: "Course Coordinator",
  assessment: "Assessment Agent",
  timeout_seconds: "Response timeout (seconds)",
  probable_cause: "Possible cause",
  recommended_action: "Recommended action",
  risk_level: "Risk level",
  confidence: "Confidence",
  tasks: "Agent tasks",
  total_tasks: "Total agent tasks",
  failure_rate: "Task failure rate",
  escalation_rate: "Human review rate",
  avg_duration_ms: "Average task duration (milliseconds)",
  high_failure_rate: "High task failure rate",
  high_latency: "Slow task responses",
  retry_request: "Retry the request",
  resume_agent: "Resume the agent",
  request_founder_review: "Request Founder review",
  no_action: "No action recommended",
  agent_resumed: "Agent resumed; recovery still requires verification",
  recovery_failed: "Recovery failed",
  agent_state_healthy: "Agent status verified as healthy",
  agent_state_verification_failed: "Agent status verification failed",
  rollback_verified: "Rollback verified",
}
function label(value: string): string {
  if (Object.hasOwn(labels, value)) return labels[value]
  const words = value.replaceAll("_", " ")
  return words.charAt(0).toUpperCase() + words.slice(1)
}
function readableText(value: string, references: DisplayReference[]): string {
  let resolved = value.replace(uuid, (id) => {
    const reference = references.find(
      (item) => item.id.toLowerCase() === id.toLowerCase()
    )
    return reference
      ? reference.label.replace(uuid, "Related record")
      : "Related record"
  })
  resolved = resolved
    .replace(
      /^(planning|assessment|coordinator|teaching_support|tech_operations):/,
      (agent) => `${label(agent.slice(0, -1))}:`
    )
    .replace(
      /\b(Update |of |agent:)(planning|assessment|coordinator|teaching_support|tech_operations)\b/g,
      (_match, prefix: string, agent: string) => `${prefix}${label(agent)}`
    )
  if (Object.hasOwn(labels, resolved)) return labels[resolved]
  // Preserve ordinary prose, numbers, URLs and email addresses.
  return resolved.replace(
    /https?:\/\/\S+|[^\s]+@[^\s]+|\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b/g,
    (token) =>
      token.includes("://") || token.includes("@") ? token : label(token)
  )
}

// Some older incident evidence is Python dictionary text. Convert literals only;
// never evaluate code. Quoted text (including apostrophes) stays quoted data.
function decodePythonString(token: string): string {
  let text = ""
  const escapes: Record<string, string> = {
    n: "\n",
    r: "\r",
    t: "\t",
    b: "\b",
    f: "\f",
    "\\": "\\",
    "'": "'",
    '"': '"',
  }
  for (let i = 1; i < token.length - 1; i++) {
    const char = token[i]
    if (char !== "\\") {
      text += char
      continue
    }
    const next = token[++i]
    if (Object.hasOwn(escapes, next)) {
      text += escapes[next]
      continue
    }
    const size = next === "u" ? 4 : next === "x" ? 2 : 0
    const hex = token.slice(i + 1, i + 1 + size)
    if (size && new RegExp(`^[0-9a-fA-F]{${size}}$`).test(hex)) {
      text += String.fromCharCode(parseInt(hex, 16))
      i += size
    } else text += `\\${next}`
  }
  return text
}
function parseDetails(value: string): unknown {
  try {
    return JSON.parse(value)
  } catch {
    const converted = value.replace(
      /"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\b(?:True|False|None)\b/g,
      (token) => {
        if (token.startsWith('"')) return token
        if (token.startsWith("'"))
          return JSON.stringify(decodePythonString(token))
        return { True: "true", False: "false", None: "null" }[token] || token
      }
    )
    return JSON.parse(converted)
  }
}
function formatValue(
  value: unknown,
  references: DisplayReference[],
  key = ""
): string {
  if (value === null) return "Not provided"
  if (typeof value === "boolean") return value ? "Yes" : "No"
  if (typeof value === "number") {
    if (
      ["confidence", "failure_rate", "escalation_rate"].includes(key) &&
      value >= 0 &&
      value <= 1
    )
      return `${Number((value * 100).toFixed(2))}%`
    return String(value)
  }
  if (typeof value === "string") return readableText(value, references)
  if (Array.isArray(value))
    return value.length
      ? value
          .map(
            (item, index) => `${index + 1}. ${formatValue(item, references)}`
          )
          .join("\n")
      : "None recorded"
  if (typeof value === "object" && value)
    return (
      Object.entries(value)
        .map(
          ([field, item]) =>
            `${label(field)}: ${formatValue(item, references, field)}`
        )
        .join("\n") || "No details recorded"
    )
  return "Not provided"
}
export function displayText(
  value: string,
  references: DisplayReference[] = []
): string {
  const trimmed = value.trim()
  if (
    (trimmed.startsWith("{") && trimmed.endsWith("}")) ||
    (trimmed.startsWith("[") && trimmed.endsWith("]"))
  ) {
    try {
      return formatValue(parseDetails(trimmed), references)
    } catch {
      return "These details could not be displayed in a readable format. Please refresh the record."
    }
  }
  return readableText(value, references)
}
