"""Single serial worker for AGENT_TASK_EXECUTION=worker (spec 5.2). No Celery, no Redis."""

import time

from django.core.management.base import BaseCommand

from orchestration.task_queue import dispatcher


class Command(BaseCommand):
    help = "Run queued agent tasks one at a time, oldest first."

    def add_arguments(self, parser):
        parser.add_argument("--poll", type=float, default=1.0, help="seconds to sleep when the queue is empty")
        parser.add_argument("--once", action="store_true", help="drain the queue once and exit")

    def handle(self, *args, poll: float, once: bool, **options):
        recovered = dispatcher.recover_stuck()  # also cleans up tasks left running by a crash
        if recovered:
            self.stdout.write(f"recovered {recovered} stuck task(s)")
        self.stdout.write("agent worker started")
        try:
            while True:
                dispatcher.recover_stuck()
                if dispatcher.run_next():
                    continue
                if once:
                    return
                time.sleep(poll)
        except KeyboardInterrupt:
            self.stdout.write("agent worker stopped")
