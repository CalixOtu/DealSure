from django.contrib import admin
from .models import ProcurementOrder, SupplierInvoice, SupplierOrderDecision, ProcurementOrderAgreement

@admin.register(ProcurementOrder)
class ProcurementOrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'buyer', 'supplier', 'amount', 'currency', 'status', 'created_at')
    list_filter = ('status', 'currency', 'created_at')
    search_fields = ('title', 'supplier__email', 'buyer__email')
    ordering = ('-created_at',)

@admin.register(SupplierInvoice)
class SupplierInvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'order', 'submitted_by', 'amount', 'currency', 'submitted_at', 'flag_payment_address_mismatch')
    list_filter = ('currency', 'flag_payment_address_mismatch', 'submitted_at')
    search_fields = ('invoice_number', 'order__title', 'submitted_by__email')
    readonly_fields = ('flag_payment_address_mismatch', 'flag_duplicate_invoice_number', 'openai_risk_explanation')
    ordering = ('-submitted_at',)

@admin.register(SupplierOrderDecision)
class SupplierOrderDecisionAdmin(admin.ModelAdmin):
    list_display = ('order', 'supplier', 'decision', 'decision_at')
    search_fields = ('order__title', 'supplier__email')
    list_filter = ('decision', 'decision_at')
    ordering = ('-decision_at',)

@admin.register(ProcurementOrderAgreement)
class ProcurementOrderAgreementAdmin(admin.ModelAdmin):
    list_display = ('order', 'party', 'role', 'accepted', 'accepted_at', 'updated_at')
    list_filter = ('role', 'accepted')
    search_fields = ('order__title', 'party__email')
