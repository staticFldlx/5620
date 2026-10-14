"""INotifyHuman (Fig 5). Notifications are stored; there is no delivery channel or unread API (out of scope)."""

from domain.governance import services as gov
from domain.governance.models import EscalationCase


def notify_assignee(case: EscalationCase) -> None:
    gov.notify("escalation_manager", recipient=case.assignee, kind=f"case_{case.kind}", ref=str(case.pk))
