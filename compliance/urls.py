from django.urls import path
from . import views

urlpatterns = [
    path('reports', views.reports_hub, name='reports'),
    path('standards', views.standards_list, name='standards'),
    path('assessment/<int:standard_id>', views.assessment, name='assessment'),
    path('results/<int:standard_id>', views.results, name='results'),
    path('results/<int:standard_id>/report', views.results_print, name='results_print'),
]