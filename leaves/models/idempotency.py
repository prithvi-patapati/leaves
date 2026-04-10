from django.db import models


class IdempotencyLog(models.Model):
    key = models.CharField(max_length=255, unique=True, db_index=True)
    action = models.CharField(max_length=100)
    request_payload = models.JSONField()
    response_payload = models.JSONField()
    status = models.CharField(max_length=20, choices=[
        ('SUCCESS', 'Completed successfully'),
        ('FAILED', 'Failed with error'),
    ])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'idempotency_log'

    def __str__(self):
        return f"{self.action} - {self.key}"
