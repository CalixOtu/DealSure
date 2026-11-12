from django.db import models
from procurement.models import SupplierInvoice
from decimal import Decimal

class InvoiceFraudAnalysis(models.Model):
    invoice = models.OneToOneField(
        SupplierInvoice,
        on_delete=models.CASCADE,
        related_name='fraud_analysis',
        help_text='The supplier invoice analyzed'
    )
    # Deterministic
    supplier_name_mismatch = models.BooleanField(default=False)
    business_name_mismatch = models.BooleanField(default=False)
    amount_mismatch = models.BooleanField(default=False)
    duplicate_invoice_number = models.BooleanField(default=False)
    payment_wallet_mismatch = models.BooleanField(default=False)
    kyc_not_verified = models.BooleanField(default=False)
    wallet_not_verified = models.BooleanField(default=False)
    # AI Results
    openai_risk_level = models.CharField(max_length=24, blank=True)
    openai_risk_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    openai_suspicious_findings = models.TextField(blank=True)
    openai_explanation = models.TextField(blank=True)
    openai_recommendations = models.TextField(blank=True)
    openai_model_used = models.CharField(max_length=50, blank=True)
    analysis_at = models.DateTimeField(auto_now_add=True)
    openai_error = models.TextField(blank=True, help_text='If OpenAI error occurs, log message here')

    def __str__(self):
        return f"FraudAnalysis for Invoice #{self.invoice.invoice_number}"
