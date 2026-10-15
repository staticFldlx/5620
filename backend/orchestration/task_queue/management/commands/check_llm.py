"""Check the configured LLM endpoint before relying on it (run after changing LLM_* settings)."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from infrastructure.llm import OPENAI_COMPATIBLE_PROVIDERS, build_adapter
from infrastructure.llm.diagnostics import probe, suggested_capabilities


class Command(BaseCommand):
    help = "Probe the configured LLM endpoint for text, JSON-schema output and tool calling."

    def add_arguments(self, parser):
        parser.add_argument("--model", help="model to test instead of LLM_MODEL_DEFAULT")

    def handle(self, *args, model: str | None, **options):
        provider = settings.LLM_PROVIDER
        if provider == "fake":
            self.stdout.write("LLM_PROVIDER=fake: no endpoint to check (agents use their offline scripts).")
            return
        if provider not in OPENAI_COMPATIBLE_PROVIDERS:
            raise CommandError(f"Unknown LLM_PROVIDER={provider!r}; use openai, school or fake.")
        missing = [name for name in ("LLM_BASE_URL", "LLM_API_KEY") if not getattr(settings, name)]
        if not (model or settings.LLM_MODEL_DEFAULT):
            missing.append("LLM_MODEL_DEFAULT")
        if missing:
            raise CommandError(f"Set {', '.join(missing)} in backend/.env first.")

        # Claim every capability so the probe measures what the endpoint really supports.
        adapter = build_adapter(provider, base_url=settings.LLM_BASE_URL, api_key=settings.LLM_API_KEY, capabilities=("tools", "json_schema"))
        models = [model] if model else list(dict.fromkeys(m for m in (settings.LLM_MODEL_DEFAULT, settings.LLM_MODEL_FAST) if m))
        all_ok = True
        for name in models:
            self.stdout.write(f"\n{settings.LLM_BASE_URL}  model={name}")
            results = probe(adapter, model=name, timeout_s=settings.LLM_TIMEOUT_SECONDS)
            for result in results:
                mark = self.style.SUCCESS("OK  ") if result.ok else self.style.ERROR("FAIL")
                self.stdout.write(f"  {mark} {result.name:<12} {result.latency_ms:>6} ms  {result.detail}")
            text_ok = results[0].ok
            all_ok = all_ok and text_ok
            if text_ok:
                self.stdout.write(f"  -> LLM_CAPABILITIES={suggested_capabilities(results)}")
        if not all_ok:
            raise CommandError("The endpoint did not answer a plain text request; check the URL, key, model and network/VPN.")
