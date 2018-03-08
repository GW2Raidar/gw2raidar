from rest_framework import serializers, viewsets, generics
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.schemas.inspectors import AutoSchema
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.parsers import FileUploadParser, MultiPartParser
import coreapi
import coreschema
from ..models import *
from ..views import _perform_upload
from distutils.util import strtobool




class EncounterSerializer(serializers.HyperlinkedModelSerializer):
    name = serializers.CharField(source='area.name')

    class Meta:
        model = Encounter
        fields = ('url_id', 'started_at', 'name', 'success')

class EncounterListView(generics.ListAPIView):
    """
    List own encounters
    """
    pagination_class = LimitOffsetPagination
    serializer_class = EncounterSerializer

    def get_queryset(self):
        queryset = Encounter.objects.filter(accounts__user=self.request.user)
        since = self.request.query_params.get('since', None)
        if since is not None:
            queryset = queryset.filter(started_at__gte=since)
        success = self.request.query_params.get('success', None)
        if success is not None:
            queryset = queryset.filter(success=strtobool(success))
        return queryset

    schema = AutoSchema(manual_fields=[
        coreapi.Field(
            name="since",
            required=False,
            location='query',
            schema=coreschema.Integer(
                title="Since",
                description="Earliest time (UNIX timestamp)",
            ),
        ),
        coreapi.Field(
            name="success",
            required=False,
            location='query',
            schema=coreschema.Boolean(
                title="Success",
                description="Return only successful or unsuccessful encounters",
            ),
        ),
    ])


class EncounterUploadView(APIView):
    """
    Upload an encounter
    """
    parser_classes = (MultiPartParser,)

    def put(self, request):
        """
            Upload an encounter
        """
        filename, upload = _perform_upload(request)
        return Response({
            "filename": filename,
            "upload_id": upload.id,
        })

    # XXX broken on https://github.com/swagger-api/swagger-ui/issues/3784
    schema = AutoSchema(manual_fields=[
        coreapi.Field(
            name="file",
            required=True,
            location='form',
            schema=coreschema.String(
                title="File",
                description="The encounter log",
            ),
        ),
        coreapi.Field(
            name="category",
            required=False,
            location='form',
            schema=coreschema.Integer(
                title="Category",
                description="Category ID",
            ),
        ),
        coreapi.Field(
            name="tags",
            required=False,
            location='form',
            schema=coreschema.String(
                title="Tags",
                description="List of tags, comma-separated",
            ),
        ),
    ])

class CategorySerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Category
        fields = ('id', 'name')

class CategoryListView(generics.ListAPIView):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    pagination_class = LimitOffsetPagination
