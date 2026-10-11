import { useState } from "react"
import { Link, useSearchParams } from "react-router"
import { ArrowRight, Moon, Sparkles, Sun } from "lucide-react"
import { useTheme } from "@/components/theme-provider"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useApp } from "@/app-context"
import { AIVisual } from "@/components/layout"

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
    <div className="auth-screen">
      <div className="auth-art">
        <Link to="/" className="brand">
          <span className="brand-mark">
            <ArrowRight size={24} />
          </span>
          LingoPath
        </Link>
        <div className="auth-visual">
          <AIVisual />
        </div>
        <span className="eyebrow">PERSONALISED LEARNING · HUMAN GUIDANCE</span>
        <h1>Every journey starts with a direction.</h1>
        <p>
          Assessment, tailored planning, and support stay connected as your goal
          evolves.
        </p>
        <div className="auth-steps">
          <span>01 · Understand</span>
          <span>02 · Assess</span>
          <span>03 · Grow</span>
        </div>
      </div>
      <div className="auth-main">
        <div className="auth-top">
          <div className="theme-toggle">
            <button
              className={theme !== "dark" ? "active" : ""}
              onClick={() => setTheme("light")}
            >
              <Sun size={14} /> Day
            </button>
            <button
              className={theme === "dark" ? "active" : ""}
              onClick={() => setTheme("dark")}
            >
              <Moon size={14} /> Night
            </button>
          </div>
        </div>
        <div className="auth-form-wrap">
          <div className="auth-kicker">
            <Sparkles size={17} /> Your workspace
          </div>
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
              />
            </label>
            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}
            <Button className="action primary full" type="submit">
              {register ? "Create account" : "Sign in"} <ArrowRight size={16} />
            </Button>
          </form>
          <p className="auth-switch">
            {register ? (
              <>
                Already have an account? <Link to="/p01">Sign in</Link>
              </>
            ) : (
              <>
                New learner? <Link to="/p02">Create a student account</Link>
              </>
            )}
          </p>
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
          <div className="demo-accounts">
            <strong>Demo access</strong>
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
          </div>
        </div>
      </div>
    </div>
  )
}
