import { useRef, useState, type ComponentProps } from "react"
import { Button } from "@/components/ui/button"

type Props = Omit<ComponentProps<typeof Button>, "asChild"> & {
  pendingLabel?: string
}

/** Follows the clicked button's real promise; other disabled buttons stay still. */
export function AIButton({
  children,
  onClick,
  disabled,
  className = "",
  pendingLabel = "Working…",
  ...props
}: Props) {
  const [pending, setPending] = useState(false)
  const inFlight = useRef(false)
  return (
    <Button
      {...props}
      className={`ai-action ${className}`}
      disabled={disabled || pending}
      aria-busy={pending}
      onClick={async (event) => {
        if (inFlight.current || !onClick) return
        inFlight.current = true
        setPending(true)
        try {
          await onClick(event)
        } finally {
          inFlight.current = false
          setPending(false)
        }
      }}
    >
      <span className="ai-button-content">
        <span className="ai-button-label" aria-hidden={pending}>
          {children}
        </span>
        <span className="ai-button-progress" aria-hidden={!pending}>
          <span className="ai-button-spinner" aria-hidden="true" />
          {pendingLabel}
        </span>
      </span>
    </Button>
  )
}
