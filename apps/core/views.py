from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from .constants import Gender, Nationality

class ChoicesView(APIView):
    def get(self, request):
        return Response({
            "gender": [{"value": choice.value, "label": choice.label} for choice in Gender],
            "nationality": [{"value": choice.value, "label": choice.label} for choice in Nationality],
        })
