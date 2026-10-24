import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react"
import type { ReactNode } from "react"
import { useNavigate } from "react-router"
import { requestFeedback } from "@/api/request-feedback"
import { api, sessionStore } from "@/api/client"
import type { User, Workspace } from "@/api/types"
import type { AIActivityKind } from "@/lib/ai-activity"

type AppState = {
  user: User | null
  workspace: Workspace | null
  loading: boolean
  busy: boolean
  aiActivity: AIActivityKind | null
  notice: string
  noticeHref: string
  refresh: () => Promise<void>
  login: (email: string, password: string) => Promise<void>
  register: (name: string, email: string, password: string) => Promise<void>
  logout: () => void
  run: <T>(
    work: () => Promise<T>,
    success?: string,
    activity?: AIActivityKind
  ) => Promise<T | undefined>
  runAI: <T>(
    activity: AIActivityKind,
    work: () => Promise<T>,
    success?: string
  ) => Promise<T | undefined>
  clearNotice: () => void
}
const Context = createContext<AppState | null>(null)
const homeFor = (role: User["role"]) =>
  role === "Student" ? "/s1" : role === "Teacher" ? "/t1" : "/f1"
export function AppProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate()
  const [user, setUser] = useState<User | null>(null)
  const [workspace, setWorkspace] = useState<Workspace | null>(null)
  const [loading, setLoading] = useState(!!sessionStore.get())
  const [busy, setBusy] = useState(false)
  const [aiActivity, setAIActivity] = useState<AIActivityKind | null>(null)
  const [notice, setNotice] = useState("")
  const [noticeHref, setNoticeHref] = useState("")
  const refresh = useCallback(async () => {
    const next = await api.workspace()
    setWorkspace(next)
    setUser(next.user)
  }, [])
  useEffect(() => {
    if (!sessionStore.get()) return
    let active = true
    api
      .workspace()
      .then((next) => {
        if (active) {
          setWorkspace(next)
          setUser(next.user)
        }
      })
      .catch(() => {
        sessionStore.clear()
        if (active) {
          setUser(null)
          setWorkspace(null)
        }
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [])
  useEffect(() => {
    const onFocus = () => {
      if (sessionStore.get()) void refresh().catch(() => {})
    }
    window.addEventListener("focus", onFocus)
    return () => window.removeEventListener("focus", onFocus)
  }, [refresh])
  const login = async (email: string, password: string) => {
    const result = await api.login(email, password)
    sessionStore.set(result.session)
    await refresh()
    navigate(homeFor(result.user.role))
  }
  const register = async (name: string, email: string, password: string) => {
    const result = await api.register(name, email, password)
    sessionStore.set(result.session)
    await refresh()
    navigate(homeFor(result.user.role))
  }
  const logout = () => {
    sessionStore.clear()
    setUser(null)
    setWorkspace(null)
    setNotice("")
    navigate("/p01")
  }
  const run = async <T,>(
    work: () => Promise<T>,
    success?: string,
    activity?: AIActivityKind
  ) => {
    setAIActivity(activity ?? null)
    setBusy(true)
    setNotice("Processing your request…")
    setNoticeHref("")
    try {
      const result = await work()
      await refresh()
      const feedback = requestFeedback(result)
      setNotice(feedback?.message || success || "")
      if (feedback?.approvals && user?.role === "Founder") setNoticeHref("/f4")
      return result
    } catch (error) {
      const e = error as {
        response?: { data?: { message?: string } }
        message?: string
        code?: string
      }
      setNotice(
        e.code === "ECONNABORTED"
          ? "The server may still be processing this request. Refresh your records before submitting again."
          : e.response?.data?.message || e.message || "Request failed"
      )
      return undefined
    } finally {
      setAIActivity(null)
      setBusy(false)
    }
  }
  return (
    <Context.Provider
      value={{
        user,
        workspace,
        loading,
        busy,
        aiActivity,
        notice,
        noticeHref,
        refresh,
        login,
        register,
        logout,
        run,
        runAI: (activity, work, success) => run(work, success, activity),
        clearNotice: () => {
          setNotice("")
          setNoticeHref("")
        },
      }}
    >
      {children}
    </Context.Provider>
  )
}
export function useApp() {
  const value = useContext(Context)
  if (!value) throw new Error("AppProvider missing")
  return value
}
