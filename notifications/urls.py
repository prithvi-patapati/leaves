from django.urls import path
from . import views

urlpatterns = [
    path('', views.activity_page, name='activity-page'),
    path('api/feed/', views.api_activity_feed, name='activity-feed'),
    path('api/stats/', views.api_activity_stats, name='activity-stats'),
]
