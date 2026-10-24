import { useEffect, useRef, useState, useSyncExternalStore } from "react"
import { Link } from "react-router"
import { ArrowUpRight, Pause, Play } from "lucide-react"
import { mountHeroScene } from "@/components/hero-scene"
import "./home.css"

const scenes = ["orbit", "nexus", "portal"]
const motionQuery = "(prefers-reduced-motion: reduce)"
function subscribeMotion(notify: () => void) {
  const query = window.matchMedia(motionQuery)
  query.addEventListener("change", notify)
  return () => query.removeEventListener("change", notify)
}

export function HomePage() {
  const [scene, setScene] = useState(0)
  const [playing, setPlaying] = useState(
    () => localStorage.getItem("lingopath-motion") !== "off"
  )
  const [inView, setInView] = useState(true)
  const [visible, setVisible] = useState(() => !document.hidden)
  const reduced = useSyncExternalStore(
    subscribeMotion,
    () => window.matchMedia(motionQuery).matches,
    () => true
  )
  const stage = useRef<HTMLElement>(null)
  const canvas = useRef<HTMLCanvasElement>(null)
  const moving = playing && !reduced
  const running = moving && inView && visible

  useEffect(() => {
    const onVisibility = () => setVisible(!document.hidden)
    document.addEventListener("visibilitychange", onVisibility)
    const observer = new IntersectionObserver(([entry]) =>
      setInView(entry.isIntersecting)
    )
    if (stage.current) observer.observe(stage.current)
    return () => {
      document.removeEventListener("visibilitychange", onVisibility)
      observer.disconnect()
    }
  }, [])
  useEffect(() => {
    if (!stage.current || !canvas.current) return
    return mountHeroScene(canvas.current, stage.current, scene, running)
  }, [scene, running])
  useEffect(() => {
    if (!running) return
    const timer = window.setInterval(
      () => setScene((current) => (current + 1) % scenes.length),
      6000
    )
    return () => window.clearInterval(timer)
  }, [running, scene])

  return (
    <main className="landing" ref={stage} data-scene={scenes[scene]}>
      <canvas ref={canvas} aria-hidden="true" />
      <header className="landing-header">
        <Link to="/" className="brand" aria-label="LingoPath home">
          <span className="brand-mark">
            <ArrowUpRight size={22} />
          </span>
          LingoPath
        </Link>
        <div className="landing-header-tools">
          <span>
            AI assistance.
            <br />
            Human judgement.
          </span>
          <button
            className="landing-motion"
            type="button"
            disabled={reduced}
            aria-label={
              reduced
                ? "Animation disabled by reduced motion preference"
                : moving
                  ? "Pause visual motion"
                  : "Play visual motion"
            }
            onClick={() => setPlaying((current) => !current)}
          >
            {moving ? <Pause size={16} /> : <Play size={16} />}
          </button>
        </div>
      </header>
      <div className="landing-content">
        <span className="eyebrow">A clearer learning direction</span>
        <h1>
          Your ambition.
          <br />
          <em>A clearer path.</em>
        </h1>
        <p>
          Personalised plans, thoughtful guidance, and the confidence to move
          forward.
        </p>
        <Link className="landing-cta" to="/p01">
          Get started <ArrowUpRight size={19} />
        </Link>
      </div>
    </main>
  )
}
