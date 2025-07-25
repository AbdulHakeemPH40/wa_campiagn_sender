from django.apps import AppConfig


class UserpanelConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'userpanel'

    def ready(self):
        import userpanel.signals
