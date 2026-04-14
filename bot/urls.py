from django.urls import path

from . import views

urlpatterns = [
    path('prompts/<str:role>/', views.get_prompt, name='bot-get-prompt'),
    path('config/', views.get_bot_config, name='bot-get-config'),
    path('log/conversation/', views.log_conversation, name='bot-log-conversation'),
    path('log/tool-call/', views.log_tool_call, name='bot-log-tool-call'),
]
