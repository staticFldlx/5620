from django.apps import AppConfig


class TaskQueueConfig(AppConfig):
    """Registered only for its management commands (run_agent_worker); it defines no models."""

    name = "orchestration.task_queue"
    label = "task_queue"
