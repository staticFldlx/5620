/** Decorative canvas only. No API calls or application state. Returns complete cleanup. */
export function mountHeroScene(
  canvas: HTMLCanvasElement,
  stage: HTMLElement,
  slide: number,
  moving: boolean
) {
  const context = canvas.getContext("2d")
  if (!context) return () => {}
  const ctx: CanvasRenderingContext2D = context
  const bg = "#050a14",
    beam = "#8fbfff",
    rgb = "143,191,255"
  let w = 0,
    h = 0,
    time = 0,
    frame = 0,
    last = 0
  const pointer = { x: 0, y: 0 }
  function fit() {
    w = stage.clientWidth
    h = stage.clientHeight
    const dpr = Math.min(devicePixelRatio || 1, 2)
    canvas.width = w * dpr
    canvas.height = h * dpr
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    draw()
  }
  function project(
    x: number,
    y: number,
    z: number,
    cx: number,
    cy: number,
    scale: number
  ) {
    const a = -0.48,
      b = 0.24,
      xx = x * Math.cos(a) + z * Math.sin(a),
      zz = -x * Math.sin(a) + z * Math.cos(a),
      yy = y * Math.cos(b) - zz * Math.sin(b),
      z2 = y * Math.sin(b) + zz * Math.cos(b)
    const p = 3.8 / (3.8 + z2)
    return [cx + xx * scale * p, cy + yy * scale * p, p, z2]
  }
  function draw() {
    if (!w || !h) return
    ctx.clearRect(0, 0, w, h)
    ctx.fillStyle = bg
    ctx.fillRect(0, 0, w, h)
    const mobile = w < 761,
      cx = w * (mobile ? 0.55 : 0.74) + pointer.x * 12,
      cy = h * (mobile ? 0.27 : 0.46) + pointer.y * 10,
      s = Math.min(w * (mobile ? 0.32 : 0.245), h * 0.35),
      tau = Math.PI * 2
    function glow(
      x: number,
      y: number,
      r: number,
      color: string,
      alpha: number
    ) {
      const g = ctx.createRadialGradient(x, y, 0, x, y, r)
      g.addColorStop(0, "rgba(" + color + "," + alpha + ")")
      g.addColorStop(0.27, "rgba(" + color + "," + alpha * 0.35 + ")")
      g.addColorStop(1, "rgba(" + color + ",0)")
      ctx.fillStyle = g
      ctx.fillRect(x - r, y - r, r * 2, r * 2)
    }
    function trace(points: number[][], color: string, width: number) {
      ctx.beginPath()
      points.forEach((p, i) =>
        i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])
      )
      ctx.strokeStyle = color
      ctx.lineWidth = width
      ctx.stroke()
    }
    glow(cx, cy, s * 2.3, rgb, 0.25)
    glow(cx - s * 0.55, cy + s * 0.45, s * 1.7, "49,94,210", 0.16)
    for (let i = 0; i < 165; i++) {
      const x = ((i * 0.61803398875) % 1) * w,
        y = ((i * i * 0.03741) % 1) * h,
        a = 0.15 + 0.5 * (0.5 + 0.5 * Math.sin(i + time * 0.5))
      ctx.fillStyle = "rgba(194,216,255," + a + ")"
      ctx.beginPath()
      ctx.arc(x, y, i % 19 === 0 ? 1.3 : 0.55, 0, tau)
      ctx.fill()
    }
    ctx.save()
    ctx.globalCompositeOperation = "screen"
    if (slide === 0) {
      // A luminous, tilted accretion disc with a dark core and moving light filaments.
      ctx.save()
      ctx.translate(cx, cy)
      ctx.rotate(-0.42 + pointer.x * 0.015)
      for (let j = 0; j < 52; j++) {
        const r = s * (0.8 + j * 0.0105),
          ry = r * (0.34 + j * 0.0015),
          alpha = 0.018 + 0.13 * Math.pow(Math.sin((j / 52) * Math.PI), 2)
        ctx.beginPath()
        ctx.ellipse(0, 0, r, ry, 0, 0, tau)
        ctx.strokeStyle = "rgba(" + rgb + "," + alpha + ")"
        ctx.lineWidth = 2.7
        ctx.stroke()
      }
      ctx.shadowColor = beam
      ctx.shadowBlur = 19
      for (let j = 0; j < 7; j++) {
        ctx.beginPath()
        ctx.ellipse(
          0,
          0,
          s * (1.12 + j * 0.009),
          s * (0.43 + j * 0.003),
          0,
          0,
          tau
        )
        ctx.strokeStyle = "rgba(" + rgb + "," + (0.45 - j * 0.05) + ")"
        ctx.lineWidth = 1.4
        ctx.stroke()
      }
      ctx.shadowBlur = 0
      ctx.restore()
      ctx.globalCompositeOperation = "source-over"
      const r = s * 0.74,
        g = ctx.createRadialGradient(
          cx - r * 0.33,
          cy - r * 0.4,
          r * 0.1,
          cx,
          cy,
          r
        )
      g.addColorStop(0, "#172e56")
      g.addColorStop(0.5, "#0c1526")
      g.addColorStop(0.91, "#060b15")
      g.addColorStop(0.97, "#234b88")
      g.addColorStop(1, "#b5dbff")
      ctx.fillStyle = g
      ctx.beginPath()
      ctx.arc(cx, cy, r, 0, tau)
      ctx.fill()
      ctx.save()
      ctx.beginPath()
      ctx.arc(cx, cy, r, 0, tau)
      ctx.clip()
      for (let j = 0; j < 30; j++) {
        ctx.beginPath()
        for (let i = 0; i <= 90; i++) {
          const x = ((i / 90) * 2 - 1) * r,
            y =
              ((j / 29) * 2 - 1) * r +
              Math.sin((x / r) * 3 + j * 0.2 + time * 0.18) * r * 0.055
          if (i) ctx.lineTo(cx + x, cy + y)
          else ctx.moveTo(cx + x, cy + y)
        }
        ctx.strokeStyle = "rgba(" + rgb + ",0.075)"
        ctx.lineWidth = 0.6
        ctx.stroke()
      }
      ctx.restore()
      ctx.globalCompositeOperation = "screen"
      ctx.save()
      ctx.translate(cx, cy)
      ctx.rotate(-0.42)
      ctx.shadowColor = beam
      ctx.shadowBlur = 16
      for (let j = 0; j < 24; j++) {
        ctx.beginPath()
        ctx.ellipse(
          0,
          0,
          s * (0.8 + j * 0.022),
          s * (0.36 + j * 0.007),
          0,
          0,
          Math.PI
        )
        ctx.strokeStyle =
          "rgba(" +
          rgb +
          "," +
          (0.12 + Math.sin((j / 24) * Math.PI) * 0.32) +
          ")"
        ctx.lineWidth = 1.2
        ctx.stroke()
      }
      ctx.shadowBlur = 0
      for (let j = 0; j < 48; j++) {
        const a = ((j / 48) * tau + time * 0.09) % tau,
          rr = s * (0.94 + (j % 5) * 0.07),
          x = Math.cos(a) * rr,
          y = Math.sin(a) * rr * 0.4
        glow(
          x,
          y,
          j % 12 === 0 ? 16 : 5,
          "199,227,255",
          j % 12 === 0 ? 0.9 : 0.5
        )
      }
      ctx.restore()
      glow(cx - r * 0.53, cy - r * 0.7, s * 0.43, "186,221,255", 0.4)
      // Long, low-intensity light paths across the horizon.
      for (let j = 0; j < 12; j++) {
        const pts = []
        for (let i = 0; i < 90; i++) {
          const x = (w * i) / 89,
            y =
              cy +
              s * 0.92 +
              (j - 6) * 3 +
              Math.sin((x / w) * 5 + time * 0.1) * s * 0.05
          pts.push([x, y])
        }
        trace(
          pts,
          "rgba(" + rgb + "," + (j === 5 ? 0.28 : 0.045) + ")",
          j === 5 ? 1 : 0.6
        )
      }
    } else if (slide === 1) {
      // Two intertwined light ribbons: a visible flowing structure rather than a flat wire grid.
      for (let k = 0; k < 2; k++)
        for (let j = 0; j < 35; j++) {
          const pts = []
          for (let i = 0; i <= 150; i++) {
            const u = (i / 150 - 0.5) * 4.8,
              z = Math.sin(u * 1.45 + time * 0.3 + k * Math.PI) * 0.7,
              y =
                Math.cos(u * 1.45 + time * 0.3 + k * Math.PI) * 0.7 +
                (j / 34 - 0.5) * 0.4
            pts.push(project(u * 0.7, y, z, cx, cy, s * 0.65))
          }
          ctx.shadowColor = k === 0 ? beam : "#3d69e8"
          ctx.shadowBlur = j % 7 === 0 ? 8 : 0
          trace(
            pts,
            k === 0
              ? "rgba(" +
                  rgb +
                  "," +
                  (0.18 + 0.36 * Math.sin((j / 35) * Math.PI)) +
                  ")"
              : "rgba(68,117,241,.34)",
            j % 7 === 0 ? 1.5 : 0.8
          )
        }
      ctx.shadowBlur = 0
      for (let j = 0; j < 48; j++) {
        const u = (j / 48 - 0.5) * 4.8,
          ang = u * 1.45 + time * 0.3
        const a = project(
            u * 0.7,
            Math.cos(ang) * 0.7,
            Math.sin(ang) * 0.7,
            cx,
            cy,
            s * 0.65
          ),
          b = project(
            u * 0.7,
            -Math.cos(ang) * 0.7,
            -Math.sin(ang) * 0.7,
            cx,
            cy,
            s * 0.65
          )
        trace([a, b], "rgba(" + rgb + ",0.15)", 0.7)
        glow(a[0], a[1], 6, "206,230,255", 0.7)
        glow(b[0], b[1], 5, rgb, 0.5)
      }
    } else {
      // An illuminated portal with perspective lines moving slowly toward the viewer.
      ctx.save()
      ctx.translate(cx, cy)
      ctx.rotate(0.13 + Math.sin(time * 0.09) * 0.03)
      for (let j = 27; j >= 0; j--) {
        const t = ((j + time * 0.55) % 28) / 28,
          scale = 0.14 + Math.pow(t, 1.8) * 1.8,
          alpha = 0.06 + 0.55 * t
        ctx.beginPath()
        ctx.roundRect(
          -s * 0.7 * scale,
          -s * 0.95 * scale,
          s * 1.4 * scale,
          s * 1.9 * scale,
          s * 0.18 * scale
        )
        ctx.strokeStyle = "rgba(" + rgb + "," + alpha + ")"
        ctx.lineWidth = j % 5 === 0 ? 2 : 1
        ctx.shadowColor = beam
        ctx.shadowBlur = j % 5 === 0 ? 14 : 0
        ctx.stroke()
      }
      ctx.shadowBlur = 0
      const rays = [
        [-0.7, -0.95],
        [0.7, -0.95],
        [-0.7, 0.95],
        [0.7, 0.95],
      ]
      for (const [x, y] of rays)
        trace(
          [
            [x * s * 0.16, y * s * 0.16],
            [x * s * 2, y * s * 2],
          ],
          "rgba(" + rgb + ",0.3)",
          1
        )
      glow(0, 0, s * 0.34, "185,219,255", 0.55)
      ctx.restore()
    }
    ctx.restore()
    const vignette = ctx.createRadialGradient(
      cx,
      cy,
      s * 0.8,
      cx,
      cy,
      Math.max(w, h) * 0.9
    )
    vignette.addColorStop(0, "rgba(3,7,16,0)")
    vignette.addColorStop(1, "rgba(3,7,16,.65)")
    ctx.fillStyle = vignette
    ctx.fillRect(0, 0, w, h)
  }

  function tick(now: number) {
    frame = requestAnimationFrame(tick)
    if (now - last < 1000 / 30) return
    time += last ? Math.min((now - last) / 1000, 0.1) : 0
    last = now
    draw()
  }
  function move(e: PointerEvent) {
    if (!moving) return
    const r = stage.getBoundingClientRect()
    pointer.x = (e.clientX - r.left) / r.width - 0.5
    pointer.y = (e.clientY - r.top) / r.height - 0.5
  }
  function leave() {
    pointer.x = 0
    pointer.y = 0
  }
  const observer = new ResizeObserver(fit)
  observer.observe(stage)
  stage.addEventListener("pointermove", move)
  stage.addEventListener("pointerleave", leave)
  fit()
  if (moving) frame = requestAnimationFrame(tick)
  return () => {
    cancelAnimationFrame(frame)
    observer.disconnect()
    stage.removeEventListener("pointermove", move)
    stage.removeEventListener("pointerleave", leave)
  }
}
