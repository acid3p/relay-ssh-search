from django.urls import path
from search.views import index

urlpatterns = [path("", index, name="search")]
