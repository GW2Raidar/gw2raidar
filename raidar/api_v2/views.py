from rest_framework import serializers, viewsets, generics
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.parsers import FileUploadParser, MultiPartParser
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from ..models import *
from ..views import _perform_upload


def strtobool(value):
    """1/0 for the usual spellings of true and false (as distutils.util.strtobool did)."""
    value = value.lower()
    if value in ('y', 'yes', 't', 'true', 'on', '1'):
        return 1
    if value in ('n', 'no', 'f', 'false', 'off', '0'):
        return 0
    raise ValueError("invalid truth value %r" % (value,))



class EncounterSerializer(serializers.HyperlinkedModelSerializer):
    #name = serializers.CharField(source='area.name')
    tags = serializers.CharField(source='tagstring')

    class Meta:
        model = Encounter
        fields = ('url_id', 'started_at', 'filename', 'area_id', 'category_id', 'tags', 'success')

@extend_schema(parameters=[
    OpenApiParameter("since", OpenApiTypes.INT, OpenApiParameter.QUERY,
                     description="Earliest time (UNIX timestamp)"),
    OpenApiParameter("area_id", OpenApiTypes.INT, OpenApiParameter.QUERY,
                     description="ID of the area where encounter took place"),
    OpenApiParameter("success", OpenApiTypes.BOOL, OpenApiParameter.QUERY,
                     description="Return only successful or unsuccessful encounters"),
])
class EncounterListView(generics.ListAPIView):
    """
    List own encounters
    """
    pagination_class = LimitOffsetPagination
    serializer_class = EncounterSerializer

    def get_queryset(self):
        queryset = Encounter.objects.filter(accounts__user=self.request.user).order_by('-started_at')

        since = self.request.query_params.get('since', None)
        if since is not None:
            queryset = queryset.filter(started_at__gte=since)

        area_id = self.request.query_params.get('area_id', None)
        if area_id is not None:
            queryset = queryset.filter(area_id=int(area_id))

        success = self.request.query_params.get('success', None)
        if success is not None:
            queryset = queryset.filter(success=strtobool(success))

        return queryset


class EncounterUploadView(APIView):
    """
    Upload an encounter
    """
    parser_classes = (MultiPartParser,)

    @extend_schema(
        request={"multipart/form-data": inline_serializer("EncounterUpload", {
            "file": serializers.FileField(help_text="The encounter log"),
            "category": serializers.IntegerField(required=False, help_text="Category ID"),
            "tags": serializers.CharField(required=False, help_text="List of tags, comma-separated"),
        })},
        responses=inline_serializer("EncounterUploadResult", {
            "filename": serializers.CharField(),
            "upload_id": serializers.IntegerField(),
        }),
    )
    def put(self, request):
        """
            Upload an encounter
        """
        filename, upload = _perform_upload(request)
        return Response({
            "filename": filename,
            "upload_id": upload.id,
        })

class CategorySerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Category
        fields = ('id', 'name')

class CategoryListView(generics.ListAPIView):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    pagination_class = LimitOffsetPagination

class AreaSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Area
        fields = ('id', 'name', 'is_cm', 'is_lcm')

class AreaListView(generics.ListAPIView):
    queryset = Area.objects.all()
    serializer_class = AreaSerializer
    pagination_class = LimitOffsetPagination
