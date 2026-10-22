"""Technical Manager monitoring cycle (UC10): detect anomalies, then diagnose new incidents.

Each cycle is an internal `system_monitoring` request through the Task Orchestrator, so the agent
gets the shared runtime (LLM diagnosis), a trace and audit like any other task.
"""

import time

from django.core.management.base import BaseCommand, CommandError

from orchestration.task_queue import dispatcher


class Command(BaseCommand):
    help = "Run Technical Manager monitoring: detect agent anomalies and diagnose new incidents."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=int, default=60, help="seconds between cycles")
        parser.add_argument("--once", action="store_true", help="run one cycle and exit")

    def handle(self, *args, interval: int, once: bool, **options):
        if interval < 1:
            raise CommandError("--interval must be at least 1 second")
        try:
            while True:
                request = dispatcher.submit("system_monitoring", actor=None, actor_role="system")
                result = request.result or {}
                line = f"monitoring {request.status}: {result.get('detected_count', 0)} anomalies, {len(result.get('diagnoses', []))} new incident(s) diagnosed"
                if request.error:
                    line += f" ({request.error.get('code')}: {request.error.get('message')})"
                self.stdout.write(line)
                if once:
                    return
                time.sleep(interval)
        except KeyboardInterrupt:
            self.stdout.write("monitoring stopped")
