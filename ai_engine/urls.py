from django.urls import path
from . import views

app_name = 'ai_engine'

urlpatterns = [
    path('invoice/<int:invoice_id>/fraud-analysis/', views.fraud_analysis_view, name='invoice_fraud_analysis'),
]
