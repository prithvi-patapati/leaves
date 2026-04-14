from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/employees/', include('employees.api.urls')),
    path('api/v1/leaves/', include('leaves.api.urls')),
    path('api/v1/tools/', include('mcp_server.urls')),
    path('dashboard/', include('dashboard.urls')),
    path('dashboard/activity/', include('notifications.urls')),
    path('api/v1/bot/', include('bot.urls')),
]
