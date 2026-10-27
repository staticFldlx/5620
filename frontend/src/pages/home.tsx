import { useEffect, useRef, useState } from "react"
import { Link } from "react-router"
import { ArrowUpRight } from "lucide-react"
import "./home.css"

const scenes = [
  {
    name: "book",
    title: "Room to discover.",
    detail: "English, one idea at a time.",
  },
  {
    name: "plan",
    title: "A plan that fits.",
    detail: "A clear next step, shaped around you.",
  },
  {
    name: "conversation",
    title: "A little help, anytime.",
    detail: "AI assistance. Human guidance.",
  },
] as const

export function HomePage() {
  const [scene, setScene] = useState(0)
  const [ready, setReady] = useState(false)
  const stage = useRef<HTMLDivElement>(null)
  const canvas = useRef<HTMLCanvasElement>(null)
  const caption = useRef<HTMLElement>(null)

  useEffect(() => {
    let cancelled = false
    let dispose: (() => void) | undefined

    // Keep the 3D engine out of the initial application bundle and other pages.
    void import("@/components/hero-scene")
      .then(({ mountHeroScene }) => {
        if (cancelled || !stage.current || !canvas.current || !caption.current)
          return
        dispose = mountHeroScene(
          canvas.current,
          stage.current,
          caption.current,
          {
            onSceneChange: setScene,
            onReady: () => setReady(true),
            onUnavailable: () => setReady(false),
          }
        )
      })
      .catch(() => {
        // The static illustration and real authentication link remain usable.
      })

    return () => {
      cancelled = true
      dispose?.()
    }
  }, [])

  return (
    <main className="landing" data-scene={scenes[scene].name}>
      <header className="landing-header">
        <Link to="/" className="landing-brand" aria-label="LingoPath home">
          <span className="landing-brand-mark">
            <ArrowUpRight size={24} aria-hidden="true" />
          </span>
          LingoPath
        </Link>
        <p className="landing-principle">
          AI assistance.
          <br />
          Human judgement.
        </p>
      </header>
      <div className="landing-hero">
        <div className="landing-content">
          <h1>
            English opens
            <br />
            new paths.
          </h1>
          <p className="landing-intro">
            Your goals, a personal learning plan,
            <br className="landing-wide-break" /> and a teacher to guide you
            forward.
          </p>
          <Link className="landing-cta" to="/p01">
            Get started <ArrowUpRight size={21} aria-hidden="true" />
          </Link>
          <p className="landing-support">
            Learn with AI. Grow with human guidance.
          </p>
        </div>
        <figure
          className="landing-art"
          data-renderer={ready ? "webgl" : "fallback"}
        >
          <div className="landing-stage" ref={stage} aria-hidden="true">
            <canvas ref={canvas} />
            {!ready && (
              <div className="landing-book-fallback">
                <span />
                <span />
              </div>
            )}
          </div>
          <figcaption ref={caption}>
            <span className="landing-caption-title">{scenes[scene].title}</span>
            <span className="landing-caption-detail">
              {scenes[scene].detail}
            </span>
          </figcaption>
        </figure>
      </div>
    </main>
  )
}
