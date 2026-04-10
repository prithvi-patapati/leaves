from django.apps import AppConfig


class LeavesConfig(AppConfig):
    name = 'leaves'
    default_auto_field = 'django.db.models.BigAutoField'

    def ready(self):
        import leaves.signal_handlers  # noqa
