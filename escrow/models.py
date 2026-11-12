from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal
from django.conf import settings
from procurement.models import ProcurementOrder, SupplierInvoice
from django.utils import timezone

User = settings.AUTH_USER_MODEL

class EscrowTransaction(models.Model):
    class EscrowStatus(models.TextChoices):
        PENDING = 'pending', 'Pending Buyer Funding'
        FUNDED = 'funded', 'Buyer Funded (Held)'
        AWAITING_DELIVERY = 'awaiting_delivery', 'Awaiting Supplier Delivery'
        DELIVERY_CONFIRMED = 'delivery_confirmed', 'Supplier Confirmed Delivery'
        RECEIPT_CONFIRMED = 'receipt_confirmed', 'Buyer Confirmed Receipt'
        RELEASED = 'released', 'Released to Supplier'
        REFUNDED = 'refunded', 'Refunded to Buyer'
        DISPUTED = 'disputed', 'Disputed'

    order = models.OneToOneField(ProcurementOrder, on_delete=models.CASCADE, related_name='escrow_transaction')
    invoice = models.OneToOneField(SupplierInvoice, on_delete=models.SET_NULL, null=True, blank=True, related_name='escrow_transaction')  # may be set after invoice
    buyer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='escrow_buyer')
    supplier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='escrow_supplier')
    amount = models.DecimalField(max_digits=16, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    currency = models.CharField(max_length=10, default='XLM')
    status = models.CharField(max_length=24, choices=EscrowStatus.choices, default=EscrowStatus.PENDING)
    buyer_funded_at = models.DateTimeField(null=True, blank=True)
    supplier_confirmed_delivery = models.BooleanField(default=False)
    supplier_confirmed_at = models.DateTimeField(null=True, blank=True)
    buyer_confirmed_receipt = models.BooleanField(default=False)
    buyer_confirmed_at = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    is_disputed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Escrow #{self.pk} Order {self.order_id} Status: {self.get_status_display()}"


class EscrowAudit(models.Model):
    escrow = models.ForeignKey(EscrowTransaction, on_delete=models.CASCADE, related_name='audits')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=100)
    details = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Audit: {self.action} at {self.created_at}" 

class Dispute(models.Model):
    escrow = models.ForeignKey(EscrowTransaction, on_delete=models.CASCADE, related_name='disputes')
    raised_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    reason = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    resolved = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='disputes_resolved')
    resolution = models.TextField(blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Dispute by {self.raised_by} on Escrow {self.escrow.id} ({'resolved' if self.resolved else 'pending'})"

class DisputeEvidence(models.Model):
    dispute = models.ForeignKey(Dispute, on_delete=models.CASCADE, related_name='evidence')
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    file = models.FileField(upload_to='dispute_evidence/')
    description = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Evidence for Dispute {self.dispute.id} ({self.file.name})"
