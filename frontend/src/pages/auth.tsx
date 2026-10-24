import { useState } from "react"
import { Link, useSearchParams } from "react-router"
import { ArrowLeft, ArrowRight, ArrowUpRight, Moon, Sun } from "lucide-react"
import { useTheme } from "@/components/theme-provider"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useApp } from "@/app-context"

export function AuthPage({ register = false }: { register?: boolean }) {
  const [params] = useSearchParams()
  const { user, login, register: create, busy, run } = useApp()
  const { theme, setTheme } = useTheme()
  const [name, setName] = useState("")
  const [email, setEmail] = useState(params.get("email") || "")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setError("")
    try {
      if (register) await create(name, email, password)
      else await login(email, password)
    } catch (err) {
      const e = err as {
        response?: { data?: { message?: string } }
        message?: string
      }
      setError(
        e.response?.data?.message || e.message || "Please check your details."
      )
    }
  }
  void run
  void busy
  return (
    <>
      <header className="auth-page-header">
        <Link to="/" className="brand">
          <span className="brand-mark">
            <ArrowUpRight size={22} />
          </span>
          LingoPath
        </Link>
        <div className="auth-header-actions">
          <Link className="auth-back" to="/">
            <ArrowLeft size={15} />
            Back home
          </Link>
          <div className="theme-toggle">
            <button
              aria-label="Day theme"
              className={theme !== "dark" ? "active" : ""}
              onClick={() => setTheme("light")}
            >
              <Sun size={14} />
              Day
            </button>
            <button
              aria-label="Night theme"
              className={theme === "dark" ? "active" : ""}
              onClick={() => setTheme("dark")}
            >
              <Moon size={14} />
              Night
            </button>
          </div>
        </div>
      </header>
      <div className="auth-screen">
        <div className="auth-art">
          <span className="eyebrow">LingoPath</span>
          <h1>
            {register
              ? "Your next chapter starts here."
              : "Every journey starts with a direction."}
          </h1>
          <p>Personalised learning. AI assistance. Human judgement.</p>
          <div className="auth-steps">
            <span>Set your learning goal</span>
            <span>Assess and build a plan</span>
            <span>Learn with your teacher</span>
          </div>
          <div className="auth-lines" aria-hidden="true">
            <span />
            <span />
            <span />
          </div>
        </div>
        <div className="auth-main">
          <div className="auth-form-wrap">
            <div className="auth-kicker">Your workspace</div>
            <h2>{register ? "Create your student account" : "Welcome back"}</h2>
            <p>
              {register
                ? "Start with your learning goal. Teacher and Founder accounts are managed separately."
                : "Sign in to continue your learning or review work."}
            </p>
            <form onSubmit={submit}>
              {register && (
                <label>
                  Full name
                  <Input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    required
                    placeholder="Your name"
                    autoComplete="name"
                  />
                </label>
              )}
              <label>
                Email address
                <Input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  placeholder="you@example.com"
                  autoComplete="username"
                />
              </label>
              <label>
                Password
                <Input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  minLength={register ? 8 : undefined}
                  required
                  placeholder={
                    register ? "At least 8 characters" : "Enter password"
                  }
                  autoComplete={register ? "new-password" : "current-password"}
                />
              </label>
              {error && (
                <p className="form-error" role="alert">
                  {error}
                </p>
              )}
              <Button className="action primary full" type="submit">
                {register ? "Create account" : "Sign in"}
                <ArrowRight size={16} />
              </Button>
            </form>
            <p className="auth-switch">
              {register ? "Already have an account?" : "New learner?"}
            </p>
            <div className="auth-links">
              <Link
                className="action secondary"
                to={register ? "/p01" : "/p02"}
              >
                {register ? "Sign in" : "Create a student account"}
              </Link>
              <Link className="action secondary" to="/workspaces">
                Choose a role
              </Link>
            </div>
            {user && (
              <p className="auth-switch">
                Already signed in as {user.name}.{" "}
                <Link
                  to={
                    user.role === "Student"
                      ? "/s1"
                      : user.role === "Teacher"
                        ? "/t1"
                        : "/f1"
                  }
                >
                  Open workspace
                </Link>
              </p>
            )}
            <details className="demo-accounts">
              <summary>Demo access</summary>
              <p>
                Password for all accounts: <code>demo1238</code>
              </p>
              {[
                ["Ivy Lin · Student", "ivy.lin@example.com"],
                ["Emily Walker · Teacher", "emily.walker@example.com"],
                ["Alex Hu · Founder", "alex.hu@example.com"],
              ].map(([label, address]) => (
                <button
                  key={address}
                  type="button"
                  onClick={() => {
                    setEmail(address)
                    setPassword("demo1238")
                  }}
                >
                  {label}
                  <span>{address}</span>
                </button>
              ))}
            </details>
          </div>
        </div>
      </div>
    </>
  )
}
