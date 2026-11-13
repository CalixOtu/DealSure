from django.urls import path
from . import views

app_name = 'escrow'

urlpatterns = [
    path('transactions/', views.transaction_list, name='transaction_list'),
    path('transactions/<int:escrow_id>/', views.transaction_detail, name='transaction_detail'),
    path(
        'transactions/<int:escrow_id>/fund/prepare/',
        views.transaction_fund_prepare,
        name='transaction_fund_prepare',
    ),
    path(
        'transactions/<int:escrow_id>/fund/submit/',
        views.transaction_fund_submit,
        name='transaction_fund_submit',
    ),
    path('transactions/<int:escrow_id>/confirm_delivery/', views.confirm_delivery, name='confirm_delivery'),
    path('transactions/<int:escrow_id>/confirm_receipt/', views.confirm_receipt, name='confirm_receipt'),
    path('transactions/<int:escrow_id>/release/', views.escrow_release, name='escrow_release'),
    path('transactions/<int:escrow_id>/refund/', views.escrow_refund, name='escrow_refund'),
    # Dispute
    path('transactions/<int:escrow_id>/dispute/', views.dispute_create, name='dispute_create'),
    path('dispute/<int:dispute_id>/', views.dispute_detail, name='dispute_detail'),
    path('dispute/<int:dispute_id>/evidence/', views.evidence_upload, name='evidence_upload'),
    path('dispute/<int:dispute_id>/resolve/', views.dispute_resolve, name='dispute_resolve'),
]
