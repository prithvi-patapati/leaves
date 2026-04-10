from django.urls import path
from mcp_server.api import tool_list, tool_execute

urlpatterns = [
    path('list', tool_list, name='tool-list'),
    path('execute', tool_execute, name='tool-execute'),
]
