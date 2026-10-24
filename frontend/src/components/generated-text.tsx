import { useEffect, useMemo, useState } from "react"

/** A brief presentation effect after the complete response arrives, not API streaming. */
export function GeneratedText({ text }: { text: string }) {
  return <RevealText key={text} text={text} />
}

function RevealText({ text }: { text: string }) {
  const characters = useMemo(() => Array.from(text), [text])
  const [visible, setVisible] = useState(() =>
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
      ? characters.length
      : 0
  )
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return
    let frame = 0
    let started: number | undefined
    const duration = Math.min(1600, Math.max(350, characters.length * 6))
    const reveal = (now: number) => {
      started ??= now
      const progress = Math.min(1, (now - started) / duration)
      setVisible(Math.ceil(characters.length * progress))
      if (progress < 1) frame = requestAnimationFrame(reveal)
    }
    frame = requestAnimationFrame(reveal)
    return () => cancelAnimationFrame(frame)
  }, [characters.length])
  const complete = visible >= characters.length
  return (
    <span className="generated-text">
      <span className="generated-text-measure" aria-hidden="true">
        {text}
      </span>
      <span className="generated-text-visible" aria-hidden="true">
        {characters.slice(0, visible).join("")}
        {!complete && <span className="generated-text-caret" />}
      </span>
      <span className="sr-only">{text}</span>
    </span>
  )
}
