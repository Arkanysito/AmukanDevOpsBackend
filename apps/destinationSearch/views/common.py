from rest_framework.response import Response
from rest_framework import status

def standard_response(queryset, serializer_class, success_label):
    """
    Devuelve siempre el mismo formato:
    - 200 con resultados (incluye 'found')
    - 200 sin resultados (found=0)
    - 500 ante excepción
    """
    try:
        count = queryset.count()
        if count > 0:
            return Response({
                "status": "ok",
                "code": 200,
                "message": f"Se encontraron {count} {success_label}.",
                "found": count,
                "data": serializer_class(queryset, many=True).data
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                "status": "OK",
                "code": 200,
                "message": "No se encontraron resultados con esos parámetros",
                "found": 0,
                "data": []
            }, status=status.HTTP_200_OK)
    except Exception:
        return Response({
            "status": "error",
            "code": 500,
            "message": "Ocurrió un error inesperado al procesar la búsqueda.",
            "found": 0,
            "data": []
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)