import { useState, useSyncExternalStore, type ReactNode } from "react"
import { Dialog } from "radix-ui"
import { Link, NavLink, Outlet, useLocation, Navigate } from "react-router"
import { motion } from "motion/react"
import {
  ArrowUpRight,
  BookOpen,
  CalendarDays,
  ChartNoAxesCombined,
  ClipboardCheck,
  ClipboardList,
  Compass,
  FileCheck2,
  GraduationCap,
  House,
  Layers3,
  LogOut,
  Moon,
  Menu,
  X,
  ShieldCheck,
  Sparkles,
  Sun,
  Users,
  Wrench,
} from "lucide-react"
import { useTheme } from "@/components/theme-provider"
import { useApp } from "@/app-context"
import type { Role } from "@/api/types"

const nav = {
  Student: [
    ["/s1", "Overview", House],
    ["/s2", "Learning goal", Compass],
    ["/s3", "Assessments", ClipboardCheck],
    ["/s4", "My learning plan", Layers3],
    ["/s5", "Lessons", CalendarDays],
    ["/s6", "Learning assistant", Sparkles],
    ["/s8", "Learning record", ChartNoAxesCombined],
  ],
  Teacher: [
    ["/t1", "Overview", House],
    ["/t2", "My students", Users],
    ["/t3", "Lessons & availability", CalendarDays],
    ["/t4", "Reviews & questions", ShieldCheck],
    ["/t5", "Teaching preparation", BookOpen],
  ],
  Founder: [
    ["/f1", "Operations overview", House],
    ["/f2", "Service exceptions", ClipboardList],
    ["/f3", "Technical incidents", Wrench],
    ["/f4", "Approvals & audit", FileCheck2],
  ],
} as const
const names: Record<string, string> = {
  "/s1": "Overview",
  "/s2": "Learning goal",
  "/s3": "Assessments",
  "/s4": "My learning plan",
  "/s5": "Lessons",
  "/s6": "Learning assistant",
  "/s8": "Learning record",
  "/t1": "Overview",
  "/t2": "My students",
  "/t3": "Lessons & availability",
  "/t4": "Reviews & questions",
  "/t5": "Teaching preparation",
  "/f1": "Operations overview",
  "/f2": "Service exceptions",
  "/f3": "Technical incidents",
  "/f4": "Approvals & audit",
}
export function Guard({ role }: { role: Role }) {
  const { user, loading } = useApp()
  if (loading) return <div className="loading-screen">Opening workspace…</div>
  if (!user) return <Navigate to="/p01" replace />
  if (user.role !== role)
    return (
      <Navigate
        to={
          user.role === "Student"
            ? "/s1"
            : user.role === "Teacher"
              ? "/t1"
              : "/f1"
        }
        replace
      />
    )
  return <Shell role={role} />
}
function Shell({ role }: { role: Role }) {
  const { user, workspace, logout, notice, noticeHref, clearNotice } = useApp()
  const { theme, setTheme } = useTheme()
  const location = useLocation()
  const [motionOn, setMotionOn] = ReactUseMotion()
  const student = workspace?.students?.[user!.id]
  const isMobile = useSyncExternalStore(
    subscribeToMobile,
    mobileSnapshot,
    () => false
  )
  const sidebarContent = (closeMenu?: () => void) => (
    <>
      <div className="sidebar-content">
        <Link to="/" className="brand" onClick={closeMenu}>
          <span className="brand-mark">
            <ArrowUpRight size={23} />
          </span>
          <span>LingoPath</span>
        </Link>
        <div className="workspace-label">
          <span className="workspace-icon">
            {role === "Student" ? "A" : role === "Teacher" ? "T" : "F"}
          </span>
          <span>
            <strong>
              {role === "Student"
                ? student?.profile.goal_summary || "Learning workspace"
                : role === "Teacher"
                  ? "Teaching workspace"
                  : "Company operations"}
            </strong>
            <small>
              {role === "Student" ? "Current learning goal" : "Role workspace"}
            </small>
          </span>
        </div>
        <div className="nav-caption">
          {role === "Student"
            ? "YOUR WORKSPACE"
            : role === "Teacher"
              ? "TEACHING WORKSPACE"
              : "COMPANY WORKSPACE"}
        </div>
        <nav className="navigation" aria-label={`${role} workspace`}>
          {nav[role].map(([path, label, Icon]) => (
            <NavLink
              key={path}
              to={path}
              onClick={closeMenu}
              className={({ isActive }) =>
                `nav-item ${isActive ? "selected" : ""}`
              }
            >
              <Icon size={17} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-spacer" />
        <div className="assistant-hint">
          <Sparkles size={16} />
          <strong>
            {role === "Student"
              ? "Learning assistant"
              : role === "Teacher"
                ? "Teaching assistant"
                : "Technical manager"}
          </strong>
          <span>
            {role === "Student"
              ? "Answers, sources and practice at your level."
              : role === "Teacher"
                ? "Evidence and materials, ready for your review."
                : "Signals and evidence, with human approval."}
          </span>
          <Link
            onClick={closeMenu}
            to={role === "Student" ? "/s6" : role === "Teacher" ? "/t5" : "/f3"}
          >
            Open workspace <ArrowUpRight size={13} />
          </Link>
        </div>
      </div>
      <button
        className="sign-out"
        onClick={() => {
          closeMenu?.()
          logout()
        }}
      >
        <LogOut size={15} /> Sign out
      </button>
    </>
  )
  return (
    <div className="app-shell" data-motion={motionOn ? "on" : "off"}>
      {!isMobile && <aside className="sidebar">{sidebarContent()}</aside>}
      <div className="main-column">
        <header className="topbar">
          <div className="breadcrumbs">
            <span>{role}</span>
            <span className="crumb-sep">/</span>
            <strong>{names[location.pathname] || "Workspace"}</strong>
          </div>
          <div className="topbar-actions">
            <div className="theme-toggle">
              <button
                aria-label="Day theme"
                className={theme !== "dark" ? "active" : ""}
                onClick={() => setTheme("light")}
              >
                <Sun size={14} /> <span>Day</span>
              </button>
              <button
                aria-label="Night theme"
                className={theme === "dark" ? "active" : ""}
                onClick={() => setTheme("dark")}
              >
                <Moon size={14} /> <span>Night</span>
              </button>
            </div>
            <div className="user-chip">
              <span>
                {user?.name
                  .split(" ")
                  .map((x) => x[0])
                  .join("")}
              </span>
              <div>
                <strong>{user?.name}</strong>
                <small>{role}</small>
              </div>
            </div>
            {isMobile && (
              <MobileNavigation
                key={location.key}
                renderContent={sidebarContent}
              />
            )}
          </div>
        </header>
        <main className="content">
          <Outlet />
        </main>
        <footer className="footer">
          Learning, with support. AI assistance · Human judgement.
          <div>
            <button onClick={() => setMotionOn(!motionOn)}>
              {motionOn ? "▷ Motion on" : "◼ Motion off"}
            </button>
          </div>
        </footer>
      </div>
      {notice && (
        <motion.div
          role="status"
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          className="toast"
        >
          <span>{notice}</span>
          {noticeHref && <Link to={noticeHref}>Review approvals →</Link>}
          <button onClick={clearNotice}>×</button>
        </motion.div>
      )}
    </div>
  )
}
const MOBILE_QUERY = "(max-width: 660px)"
function mobileSnapshot() {
  return window.matchMedia(MOBILE_QUERY).matches
}
function subscribeToMobile(notify: () => void) {
  const query = window.matchMedia(MOBILE_QUERY)
  query.addEventListener("change", notify)
  return () => query.removeEventListener("change", notify)
}
function MobileNavigation({
  renderContent,
}: {
  renderContent: (close: () => void) => ReactNode
}) {
  const [open, setOpen] = useState(false)
  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <button
          className="mobile-menu-trigger"
          aria-label="Open navigation menu"
        >
          <Menu size={22} aria-hidden="true" />
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="mobile-menu-overlay" />
        <Dialog.Content
          className="sidebar mobile-navigation"
          aria-describedby={undefined}
        >
          <Dialog.Title className="sr-only">Navigation menu</Dialog.Title>
          <Dialog.Close asChild>
            <button
              className="mobile-menu-close"
              aria-label="Close navigation menu"
            >
              <X size={22} aria-hidden="true" />
            </button>
          </Dialog.Close>
          {renderContent(() => setOpen(false))}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
function ReactUseMotion(): [boolean, (v: boolean) => void] {
  const [value, setValue] = importReactUseState(
    () => localStorage.getItem("lingopath-motion") !== "off"
  )
  return [
    value,
    (v) => {
      localStorage.setItem("lingopath-motion", v ? "on" : "off")
      setValue(v)
    },
  ]
}
import { useState as importReactUseState } from "react"
export function Page({
  eyebrow,
  title,
  subtitle,
  children,
  action,
}: {
  eyebrow: string
  title: string
  subtitle: string
  children: React.ReactNode
  action?: React.ReactNode
}) {
  return (
    <>
      <div className="page-head">
        <div>
          <span className="eyebrow">{eyebrow}</span>
          <h1>{title}</h1>
          <p>{subtitle}</p>
        </div>
        {action}
      </div>
      {children}
    </>
  )
}
export function Panel({
  title,
  children,
  className = "",
  action,
}: {
  title?: string
  children: React.ReactNode
  className?: string
  action?: React.ReactNode
}) {
  return (
    <section className={`panel ${className}`}>
      {title && (
        <div className="panel-head">
          <h2>{title}</h2>
          {action}
        </div>
      )}
      {children}
    </section>
  )
}
export function Pill({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode
  tone?: "neutral" | "good" | "warn" | "info"
}) {
  return <span className={`pill ${tone}`}>{children}</span>
}
export function Metric({
  label,
  value,
  note,
  icon: Icon,
}: {
  label: string
  value: React.ReactNode
  note?: string
  icon?: React.ComponentType<{ size?: number }>
}) {
  return (
    <div className="metric">
      <div className="metric-top">
        <span>{label}</span>
        {Icon && <Icon size={16} />}
      </div>
      <strong>{value}</strong>
      <small>{note}</small>
    </div>
  )
}
export function Row({
  title,
  detail,
  right,
  onClick,
}: {
  title: string
  detail?: string
  right?: React.ReactNode
  onClick?: () => void
}) {
  const content = (
    <>
      <div>
        <strong>{title}</strong>
        {detail && <small>{detail}</small>}
      </div>
      {right}
    </>
  )
  return onClick ? (
    <button className="list-row interactive" onClick={onClick}>
      {content}
    </button>
  ) : (
    <div className="list-row">{content}</div>
  )
}
export function AIVisual({
  variant = "orbit",
}: {
  variant?: "orbit" | "scan" | "path" | "signal" | "paper"
}) {
  return (
    <div className={`ai-visual ${variant}`} aria-hidden="true">
      <div className="orbit one" />
      <div className="orbit two" />
      <div className="orb" />
      <span className="spark a" />
      <span className="spark b" />
      <span className="spark c" />
    </div>
  )
}
export function Empty({
  children = "No records yet.",
}: {
  children?: React.ReactNode
}) {
  return <p className="empty">{children}</p>
}
export function Status({ children }: { children: React.ReactNode }) {
  return (
    <p role="status" className="inline-status">
      {children}
    </p>
  )
}
export function RoleDirectory() {
  return (
    <div className="directory">
      <div className="directory-hero">
        <span className="eyebrow">LINGOPATH · STAGE ONE</span>
        <h1>One connected learning journey.</h1>
        <p>
          Explore the 18 core screens with demo data. Choose a role to enter its
          workspace.
        </p>
        <AIVisual />
      </div>
      <div className="directory-grid">
        {[
          [
            "Student",
            "7 pages",
            "Goals, assessment, plan, lessons, support and learning record.",
            GraduationCap,
            "ivy.lin@example.com",
          ],
          [
            "Teacher",
            "5 pages",
            "Student evidence, lessons, reviews and teaching material.",
            Users,
            "emily.walker@example.com",
          ],
          [
            "Founder",
            "4 pages",
            "Agent status, exceptions, incidents and approvals.",
            ShieldCheck,
            "alex.hu@example.com",
          ],
        ].map(([role, count, description, Icon, email]) => (
          <div className="directory-card" key={role as string}>
            <Icon size={22} />
            <h2>{role as string}</h2>
            <small>{count as string}</small>
            <p>{description as string}</p>
            <Link to={`/p01?email=${email}`}>
              Open {role as string} workspace <ArrowUpRight size={16} />
            </Link>
          </div>
        ))}
      </div>
      <div className="directory-foot">
        <Link to="/p01">Sign in</Link>
        <Link to="/p02">Create student account</Link>
        <span>2 public pages · 7 student · 5 teacher · 4 Founder</span>
      </div>
    </div>
  )
}
