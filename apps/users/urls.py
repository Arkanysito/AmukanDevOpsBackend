from django.contrib import admin
from django.urls import path, include
from apps.users.views import CreateUserView, CurrentUserView, EmailAvailabilityView, UsernameAvailabilityView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from apps.core.views import ChoicesView


urlpatterns = [
    path('register/', CreateUserView.as_view(), name="register"),
    path('token/', TokenObtainPairView.as_view(), name='get_token'),
    path('token/refresh/', TokenRefreshView.as_view(), name='refresh'),
    path("me/", CurrentUserView.as_view(), name="current_user"),
    path('choices/', ChoicesView.as_view(), name='choices'),
    path("check-username/", UsernameAvailabilityView.as_view(), name="check-username"),
    path("check-email/", EmailAvailabilityView.as_view(), name="check_email"),

]