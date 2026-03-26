from django.urls import path
from . import views

urlpatterns = [
    path('standards', views.standards_list, name='standards'),
    path('assessment/<int:standard_id>', views.assessment, name='assessment'),
    path('results/<int:standard_id>', views.results, name='results'),
]