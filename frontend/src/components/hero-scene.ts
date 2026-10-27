import * as THREE from "three"

type HeroCallbacks = {
  onSceneChange: (scene: number) => void
  onReady: () => void
  onUnavailable: () => void
}

/** Decorative only: no API requests, authentication changes, or stored user data. */
export function mountHeroScene(
  canvas: HTMLCanvasElement,
  stage: HTMLElement,
  caption: HTMLElement,
  callbacks: HeroCallbacks
) {
  const renderer = new THREE.WebGLRenderer({
    canvas,
    alpha: true,
    antialias: true,
  })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
  renderer.setClearColor(0, 0)
  renderer.shadowMap.enabled = true
  renderer.shadowMap.type = THREE.VSMShadowMap
  renderer.outputColorSpace = THREE.SRGBColorSpace
  renderer.toneMapping = THREE.ACESFilmicToneMapping
  renderer.toneMappingExposure = 1.15
  const scene = new THREE.Scene(),
    camera = new THREE.PerspectiveCamera(32, 1, 0.1, 100)
  camera.position.set(0, 0, 9.4)
  camera.lookAt(0, 0, 0)
  scene.add(new THREE.HemisphereLight(0xffffff, 0xabc0e7, 2.6))
  const key = new THREE.DirectionalLight(0xffffff, 4)
  key.position.set(-3, 5, 7)
  key.castShadow = true
  key.shadow.mapSize.set(1024, 1024)
  key.shadow.camera.left = -5
  key.shadow.camera.right = 5
  key.shadow.camera.top = 5
  key.shadow.camera.bottom = -5
  key.shadow.normalBias = 0.025
  key.shadow.radius = 5
  key.shadow.blurSamples = 12
  scene.add(key)
  const rim = new THREE.DirectionalLight(0xc5daff, 2)
  rim.position.set(4, 1, -1)
  scene.add(rim)
  const blue = new THREE.MeshStandardMaterial({
    color: 0x345fbd,
    roughness: 0.3,
    metalness: 0.16,
  })
  const white = new THREE.MeshStandardMaterial({
    color: 0xfdfefe,
    roughness: 0.48,
    metalness: 0.02,
  })
  const silver = new THREE.MeshStandardMaterial({
    color: 0xa9c0e7,
    roughness: 0.3,
    metalness: 0.45,
  })
  const pageEdge = new THREE.MeshStandardMaterial({
    color: 0xd1daeb,
    roughness: 0.75,
  })
  const pale = new THREE.MeshStandardMaterial({
    color: 0xb9cff6,
    roughness: 0.45,
    metalness: 0.1,
  })
  const shadow = new THREE.Mesh(
    new THREE.PlaneGeometry(20, 20),
    new THREE.ShadowMaterial({ opacity: 0.065 })
  )
  shadow.position.z = -0.95
  shadow.receiveShadow = true
  scene.add(shadow)
  const host = new THREE.Group()
  scene.add(host)
  function rounded(w: number, h: number, r: number) {
    const s = new THREE.Shape(),
      x = -w / 2,
      y = -h / 2
    r = Math.min(r, w / 2, h / 2)
    s.moveTo(x + r, y)
    s.lineTo(x + w - r, y)
    s.quadraticCurveTo(x + w, y, x + w, y + r)
    s.lineTo(x + w, y + h - r)
    s.quadraticCurveTo(x + w, y + h, x + w - r, y + h)
    s.lineTo(x + r, y + h)
    s.quadraticCurveTo(x, y + h, x, y + h - r)
    s.lineTo(x, y + r)
    s.quadraticCurveTo(x, y, x + r, y)
    return s
  }
  function solid(
    shape: THREE.Shape,
    depth: number,
    mat: THREE.Material,
    bevel = 0.055
  ) {
    const g = new THREE.ExtrudeGeometry(shape, {
      depth,
      bevelEnabled: true,
      bevelSegments: 5,
      steps: 1,
      bevelSize: bevel,
      bevelThickness: bevel,
      curveSegments: 24,
    })
    g.translate(0, 0, -depth / 2)
    const m = new THREE.Mesh(g, mat)
    m.castShadow = true
    m.receiveShadow = true
    return m
  }
  function plate(
    w: number,
    h: number,
    depth: number,
    r: number,
    mat: THREE.Material
  ) {
    return solid(rounded(w, h, r), depth, mat)
  }
  function box(w: number, h: number, d: number, mat: THREE.Material) {
    const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat)
    m.castShadow = true
    m.receiveShadow = true
    return m
  }
  function sphere(r: number, mat: THREE.Material) {
    const m = new THREE.Mesh(new THREE.SphereGeometry(r, 32, 24), mat)
    m.castShadow = true
    return m
  }
  function barBetween(
    a: [number, number],
    b: [number, number],
    width: number,
    mat: THREE.Material,
    z: number
  ) {
    const mid = new THREE.Vector3((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, z)
    const len = Math.hypot(b[0] - a[0], b[1] - a[1])
    const m = plate(len, width, 0.045, width / 2, mat)
    m.position.copy(mid)
    m.rotation.z = Math.atan2(b[1] - a[1], b[0] - a[0])
    return m
  }
  function book() {
    const group = new THREE.Group()
    for (const side of [-1, 1]) {
      const wing = new THREE.Group()
      wing.rotation.y = side * 0.13
      wing.position.x = side * 0.05
      const cover = plate(1.62, 2.45, 0.12, 0.1, blue)
      cover.position.set(side * 0.82, 0, -0.15)
      wing.add(cover)
      const pages = plate(1.49, 2.27, 0.18, 0.05, pageEdge)
      pages.position.set(side * 0.8, 0.01, 0)
      wing.add(pages)
      for (let k = 0; k < 4; k++) {
        const line = box(1.38, 0.009, 0.008, white)
        line.position.set(side * 0.8, -1.11, 0.06 - k * 0.037)
        wing.add(line)
      }
      // The page bends only at its binding; the book silhouette stays familiar.
      const geo = new THREE.PlaneGeometry(1.46, 2.25, 28, 1),
        pos = geo.attributes.position
      for (let i = 0; i < pos.count; i++) {
        const u = (pos.getX(i) + 0.73) / 1.46
        const dist = side === 1 ? u : 1 - u
        pos.setZ(i, 0.16 + 0.19 * Math.exp(-dist * 5))
      }
      geo.computeVertexNormals()
      const page = new THREE.Mesh(geo, white)
      page.position.set(side * 0.8, 0.01, 0)
      page.castShadow = true
      page.receiveShadow = true
      wing.add(page)
      if (side === 1) {
        const bookmark = plate(0.2, 0.76, 0.022, 0.02, blue)
        bookmark.position.set(1.19, -0.88, 0.19)
        wing.add(bookmark)
      }
      // A few engraved lines read as a page, without adding interface copy.
      for (let i = 0; i < 5; i++) {
        const line = box(i === 4 ? 0.63 : 0.94, 0.025, 0.008, pale)
        line.position.set(side * 0.85, 0.5 - i * 0.2, 0.205)
        wing.add(line)
      }
      group.add(wing)
    }
    const spine = plate(0.13, 2.35, 0.15, 0.045, blue)
    spine.position.z = -0.12
    group.add(spine)
    group.rotation.set(-0.24, -0.3, -0.13)
    return group
  }
  function plan() {
    const group = new THREE.Group(),
      back = plate(2.34, 2.94, 0.17, 0.2, blue)
    back.position.set(0.13, 0.05, -0.2)
    back.rotation.z = -0.09
    group.add(back)
    const board = plate(2.22, 2.86, 0.18, 0.17, white)
    group.add(board)
    const clip = plate(0.72, 0.25, 0.16, 0.08, silver)
    clip.position.set(0, 1.39, 0.17)
    group.add(clip)
    for (let i = 0; i < 3; i++) {
      const y = 0.73 - i * 0.71
      const tile = plate(0.37, 0.37, 0.04, 0.065, i === 0 ? blue : pale)
      tile.position.set(-0.67, y, 0.19)
      group.add(tile)
      if (i === 0) {
        group.add(barBetween([-0.78, y], [-0.7, y - 0.08], 0.025, white, 0.26))
        group.add(
          barBetween([-0.7, y - 0.08], [-0.56, y + 0.1], 0.025, white, 0.26)
        )
      }
      const line = plate(1.0, 0.1, 0.035, 0.04, i === 0 ? blue : silver)
      line.position.set(0.23, y + 0.06, 0.19)
      group.add(line)
      const small = plate(0.67, 0.06, 0.025, 0.025, pale)
      small.position.set(0.065, y - 0.15, 0.18)
      group.add(small)
    }
    group.rotation.set(-0.08, -0.32, 0.12)
    return group
  }
  function bubbleShape(w: number, h: number, tailSide: number) {
    const s = rounded(w, h, 0.23)
    const tail = new THREE.Shape()
    const x = tailSide * w * 0.28
    tail.moveTo(x, -h / 2 + 0.12)
    tail.lineTo(x + tailSide * 0.14, -h / 2 - 0.43)
    tail.lineTo(x - tailSide * 0.44, -h / 2 + 0.09)
    tail.closePath()
    return [s, tail]
  }
  function bubble(w: number, h: number, mat: THREE.Material, tailSide: number) {
    const g = new THREE.Group()
    for (const shape of bubbleShape(w, h, tailSide))
      g.add(solid(shape, 0.18, mat, 0.06))
    return g
  }
  function conversation() {
    const group = new THREE.Group(),
      rear = bubble(2.25, 1.55, blue, 1)
    rear.position.set(0.42, 0.57, -0.17)
    rear.rotation.set(0, -0.1, -0.09)
    group.add(rear)
    for (let i = 0; i < 2; i++) {
      const line = plate(i ? 0.74 : 1.15, 0.07, 0.025, 0.03, pale)
      line.position.set(-0.16, 0.2 - i * 0.27, 0.19)
      rear.add(line)
    }
    const front = bubble(2.52, 1.64, white, -1)
    front.position.set(-0.35, -0.46, 0.24)
    front.rotation.z = 0.08
    group.add(front)
    for (let i = 0; i < 3; i++) {
      const dot = sphere(0.115, blue)
      dot.position.set((i - 1) * 0.46, 0.02, 0.18)
      front.add(dot)
      dot.userData.pulse = i
    }
    group.rotation.set(-0.08, -0.25, -0.05)
    return group
  }
  const objects = [book(), plan(), conversation()]
  objects.forEach((o, i) => {
    o.visible = i === 0
    host.add(o)
  })
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)")
  let time = 0,
    last: number | null = null,
    current = 0,
    visible = true,
    frameId = 0,
    disposed = false,
    unavailable = false,
    painted = false
  let px = 0,
    py = 0,
    tx = 0,
    ty = 0

  function moving() {
    return (
      visible &&
      !document.hidden &&
      !reduced.matches &&
      !unavailable &&
      !disposed
    )
  }
  function request() {
    if (!frameId && !disposed && !unavailable)
      frameId = requestAnimationFrame(frame)
  }
  function frame(now: number) {
    frameId = 0
    if (disposed || unavailable) return
    if (moving() && last !== null) time += now - last
    last = now
    // Swap one model and one caption while fully faded, never overlapping scenes.
    const step = Math.floor(time / 6000) % objects.length,
      local = time % 6000
    let opacity = 1
    if (local < 420 && time >= 6000) opacity = local / 420
    else if (local > 5580) opacity = (6000 - local) / 420
    if (step !== current) {
      canvas.style.opacity = "0"
      caption.style.opacity = "0"
      objects[current].visible = false
      current = step
      objects[current].visible = true
      callbacks.onSceneChange(current)
    }
    canvas.style.opacity = String(reduced.matches ? 1 : opacity)
    caption.style.opacity = String(reduced.matches ? 1 : opacity)
    px += (tx - px) * 0.035
    py += (ty - py) * 0.035
    host.rotation.y = reduced.matches
      ? 0
      : Math.sin(time / 4500) * 0.085 + px * 0.12
    host.rotation.x = reduced.matches ? 0 : py * 0.08
    host.position.y = reduced.matches ? 0 : Math.sin(time / 1900) * 0.055
    host.scale.setScalar(reduced.matches ? 1 : 0.98 + 0.02 * opacity)
    if (current === 2 && !reduced.matches)
      objects[2].traverse((o) => {
        const pulse = o.userData.pulse as number | undefined
        if (pulse !== undefined)
          o.scale.setScalar(
            1 + Math.max(0, Math.sin(time / 350 - pulse * 0.9)) * 0.15
          )
      })
    renderer.render(scene, camera)
    if (!painted) {
      painted = true
      callbacks.onReady()
    }
    if (moving()) request()
  }
  function pauseOrResume() {
    cancelAnimationFrame(frameId)
    frameId = 0
    last = null
    // A fresh static frame also removes any partial fade when reduced motion changes.
    if (visible && !document.hidden) request()
  }
  function fit() {
    if (disposed || unavailable) return
    const { width, height } = stage.getBoundingClientRect()
    if (!width || !height) return
    renderer.setSize(width, height, false)
    camera.aspect = width / height
    camera.position.z = camera.aspect < 0.9 ? 10.2 : 9.4
    camera.updateProjectionMatrix()
    request()
  }
  function move(event: PointerEvent) {
    if (event.pointerType === "touch" || !moving()) return
    const b = stage.getBoundingClientRect()
    tx = (event.clientX - b.left) / b.width - 0.5
    ty = (event.clientY - b.top) / b.height - 0.5
  }
  function leave() {
    tx = ty = 0
  }
  function contextLost(event: Event) {
    event.preventDefault()
    unavailable = true
    cancelAnimationFrame(frameId)
    frameId = 0
    caption.style.opacity = "1"
    callbacks.onSceneChange(0)
    callbacks.onUnavailable()
  }
  const resizeObserver = new ResizeObserver(fit)
  resizeObserver.observe(stage)
  const intersectionObserver = new IntersectionObserver(([entry]) => {
    visible = entry.isIntersecting
    pauseOrResume()
  })
  intersectionObserver.observe(stage)
  document.addEventListener("visibilitychange", pauseOrResume)
  reduced.addEventListener("change", pauseOrResume)
  stage.addEventListener("pointermove", move)
  stage.addEventListener("pointerleave", leave)
  canvas.addEventListener("webglcontextlost", contextLost)
  fit()

  return () => {
    disposed = true
    cancelAnimationFrame(frameId)
    resizeObserver.disconnect()
    intersectionObserver.disconnect()
    document.removeEventListener("visibilitychange", pauseOrResume)
    reduced.removeEventListener("change", pauseOrResume)
    stage.removeEventListener("pointermove", move)
    stage.removeEventListener("pointerleave", leave)
    canvas.removeEventListener("webglcontextlost", contextLost)
    const geometries = new Set<THREE.BufferGeometry>(),
      materials = new Set<THREE.Material>()
    scene.traverse((o) => {
      if (o instanceof THREE.Mesh) {
        geometries.add(o.geometry)
        for (const material of Array.isArray(o.material)
          ? o.material
          : [o.material])
          materials.add(material)
      }
    })
    geometries.forEach((g) => g.dispose())
    materials.forEach((m) => m.dispose())
    key.shadow.dispose()
    renderer.dispose()
    renderer.forceContextLoss()
    canvas.style.opacity = "1"
    caption.style.opacity = "1"
  }
}
