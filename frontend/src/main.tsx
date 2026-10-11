import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { ThemeProvider } from "@/components/theme-provider"
import App from "./App"
import "./index.css"

async function start() {
  if (import.meta.env.VITE_USE_MOCK_API !== "false") {
    const { worker } = await import("./mocks/browser")
    await worker.start({ onUnhandledFrame: "bypass" })
  }
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <ThemeProvider
        defaultTheme="light"
        storageKey="lingopath-theme"
        disableTransitionOnChange={false}
      >
        <App />
      </ThemeProvider>
    </StrictMode>
  )
}
void start()
