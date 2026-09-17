from django.urls import path

from analytics.views import AdminAnalyticsOverviewView, AdminAnalyticsSummaryView

urlpatterns = [
    path("", AdminAnalyticsOverviewView.as_view(), name="admin-analytics-root"),
    path(
        "summary/", AdminAnalyticsSummaryView.as_view(), name="admin-analytics-summary"
    ),
    path(
        "overview/",
        AdminAnalyticsOverviewView.as_view(),
        name="admin-analytics-overview",
    ),
]
