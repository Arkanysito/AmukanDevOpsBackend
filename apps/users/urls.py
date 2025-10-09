from django.contrib import admin
from django.urls import path, include
from apps.users.views import (
    CreateUserView, CurrentUserView, EmailAvailabilityView, UsernameAvailabilityView,
    InterestListView, UserInterestsView
)
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from apps.core.views import ChoicesView
from apps.users.views import get_user_detail, update_user, delete_user

urlpatterns = [
    path('register/', CreateUserView.as_view(), name="register"),
    path('token/', TokenObtainPairView.as_view(), name='get_token'),
    path('token/refresh/', TokenRefreshView.as_view(), name='refresh'),
    path("me/", CurrentUserView.as_view(), name="current_user"),
    path('choices/', ChoicesView.as_view(), name='choices'),
    path("check-username/", UsernameAvailabilityView.as_view(), name="check-username"),
    path("check-email/", EmailAvailabilityView.as_view(), name="check_email"),
    path("interests/", InterestListView.as_view(), name="interests-list"),
    path("me/interests/", UserInterestsView.as_view(), name="user-interests"),
    path("<str:user_id>/", get_user_detail, name="users-detail"),
    path("<str:user_id>/update/", update_user, name="users-update"),
    path("<str:user_id>/delete/", delete_user, name="users-delete"),
]