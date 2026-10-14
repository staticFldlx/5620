"""Index the material corpus (spec 7.4). Only for seed data; later changes go through an approved UpdateProposal."""

from django.core.management.base import BaseCommand

from domain.learning.models import LearningMaterial
from infrastructure import retrieval


class Command(BaseCommand):
    help = "Ingest learning materials into the configured retrieval backend (no-op when RETRIEVAL_BACKEND=none)."

    def handle(self, *args, **options):
        ids = [str(pk) for pk in LearningMaterial.objects.values_list("pk", flat=True)]
        if not retrieval.is_enabled():
            self.stdout.write("RETRIEVAL_BACKEND=none: nothing to ingest")
            return
        report = retrieval.ingest(ids)
        self.stdout.write(f"ingested {len(report.ingested)}, unchanged {len(report.skipped)}, failed {len(report.failed)}")
