from django.db import models


class Designation(models.Model):
    title = models.CharField(max_length=100, unique=True)
    level = models.IntegerField(default=0)
    department_default = models.ForeignKey(
        'Department', null=True, blank=True, on_delete=models.SET_NULL
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'designations'
        ordering = ['level', 'title']

    def __str__(self):
        return self.title
