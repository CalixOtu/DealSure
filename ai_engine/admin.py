from django.contrib import admin
from .models import InvoiceFraudAnalysis

@admin.register(InvoiceFraudAnalysis)
class InvoiceFraudAnalysisAdmin(admin.ModelAdmin):
    list_display = (
        'invoice', 'analysis_at', 'openai_risk_level', 'openai_risk_score',
        'supplier_name_mismatch', 'amount_mismatch', 'payment_wallet_mismatch',
    )
    search_fields = ('invoice__invoice_number', 'invoice__order__title')
    list_filter = (
        'openai_risk_level', 'supplier_name_mismatch', 'amount_mismatch',
        'duplicate_invoice_number', 'payment_wallet_mismatch',
    )
    readonly_fields = (
        'invoice', 'openai_risk_level', 'openai_risk_score',
        'openai_suspicious_findings', 'openai_explanation', 'openai_recommendations',
        'openai_model_used', 'analysis_at', 'openai_error',
        'supplier_name_mismatch', 'business_name_mismatch', 'amount_mismatch',
        'duplicate_invoice_number', 'payment_wallet_mismatch', 'kyc_not_verified', 'wallet_not_verified',
    )
