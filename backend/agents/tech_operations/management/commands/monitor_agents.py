
"""Run periodic AI agent anomaly detection."""

import time
import logging

from django.core.management.base import BaseCommand

from agents.tech_operations.agent import TechOperationsAgent
from agents.runtime import AgentStatus


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Periodically monitor AI agents for anomalies."

    def add_arguments(self, parser):
        parser.add_argument(
            "--interval",
            type=int,
            default=60,
            help="Monitoring interval in seconds.",
        )

        parser.add_argument(
            "--once",
            action="store_true",
            help="Run monitoring once and exit.",
        )

    def handle(self, *args, **options):
        interval = options["interval"]

        if interval < 1:
            raise ValueError("Interval must be at least 1 second.")

        self.stdout.write(
            self.style.SUCCESS(
                f"Monitoring started (interval={interval}s)"
            )
        )

        while True:
            try:
                agent = TechOperationsAgent(runtime=None)
                result = agent.detect_system_anomalies()

                if result.status == AgentStatus.OK:
                    payload = result.payload

                    self.stdout.write(
                        "Detection completed: "
                        f"{payload['detected_count']} anomalies"
                    )
                else:
                    logger.error(
                        "Anomaly detection failed: %s",
                        result.reason,
                    )

            except Exception:
                logger.exception("Monitoring cycle failed")

            if options["once"]:
                break

            time.sleep(interval)
