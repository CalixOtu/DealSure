from django.contrib import admin
from .models import EscrowTransaction, EscrowAudit, Dispute, DisputeEvidence

@admin.register(EscrowTransaction)
class EscrowTransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'order', 'buyer', 'supplier', 'amount', 'currency', 'status', 'is_disputed', 'created_at')
    list_filter = ('status', 'currency', 'is_disputed', 'created_at')
    search_fields = ('order__title', 'buyer__email', 'supplier__email')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)

@admin.register(EscrowAudit)
class EscrowAuditAdmin(admin.ModelAdmin):
    list_display = ('escrow', 'actor', 'action', 'created_at')
    search_fields = ('action', 'details')
    list_filter = ('action', 'created_at')

@admin.register(Dispute)
class DisputeAdmin(admin.ModelAdmin):
    list_display = ('id', 'escrow', 'raised_by', 'resolved', 'created_at', 'resolved_at')
    search_fields = ('reason', 'resolution')
    list_filter = ('resolved', 'created_at')
    readonly_fields = ('created_at', 'resolved_at')

@admin.register(DisputeEvidence)
class DisputeEvidenceAdmin(admin.ModelAdmin):
    list_display = ('id', 'dispute', 'uploaded_by', 'file', 'uploaded_at')
    search_fields = ('description',)
    list_filter = ('uploaded_at',)
