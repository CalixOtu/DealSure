from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from decimal import Decimal
from django.utils import timezone

User = settings.AUTH_USER_MODEL


class ProcurementOrder(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        SENT = 'sent', 'Sent/Issued to Supplier'
        INVITED = 'invited', 'Supplier Invited'
        SUPPLIER_ACCEPTED = 'supplier_accepted', 'Supplier Accepted'
        SUPPLIER_REJECTED = 'supplier_rejected', 'Supplier Rejected'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'

    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='orders_created'
    )
    supplier = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='orders_received'
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    amount = models.DecimalField(
        max_digits=16, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))]
    )
    currency = models.CharField(max_length=10, default='XLM')  # Testnet default
    status = models.CharField(
        max_length=24, choices=Status.choices, default=Status.DRAFT
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    supplier_invite_email = models.EmailField(blank=True)  # If supplier is via invite

    def __str__(self):
        return f"{self.title} (Order #{self.id})"

    class Meta:
        ordering = ['-created_at']

def supplier_profile(instance):
    try:
        return instance.supplier.business_profile
    except Exception:
        return None


class SupplierOrderDecision(models.Model):
    order = models.OneToOneField(ProcurementOrder, on_delete=models.CASCADE, related_name='supplier_decision')
    supplier = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='supplier_order_decisions'
    )
    decision = models.CharField(
        max_length=8,
        choices=[
            ('accepted', 'Accepted'),
            ('rejected', 'Rejected')
        ],
        blank=False
    )
    comment = models.TextField(blank=True)
    decision_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ('order', 'supplier')

    def __str__(self):
        return f"{self.supplier.email} {self.decision} order #{self.order.id}"


class ProcurementOrderAgreement(models.Model):
    order = models.ForeignKey(ProcurementOrder, on_delete=models.CASCADE, related_name='agreements')
    party = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    accepted = models.BooleanField(default=False)
    accepted_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    role = models.CharField(max_length=12, choices=[('buyer', 'Buyer'), ('supplier', 'Supplier')])

    class Meta:
        unique_together = ('order', 'party', 'role')

    def __str__(self):
        return f"{self.party.email} - {self.role} - {'Accepted' if self.accepted else 'Pending'}"


class SupplierInvoice(models.Model):
    order = models.OneToOneField(
        ProcurementOrder, on_delete=models.CASCADE, related_name='invoice'
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='submitted_invoices')
    invoice_number = models.CharField(max_length=100)
    amount = models.DecimalField(
        max_digits=16, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))]
    )
    currency = models.CharField(max_length=10, default='XLM')
    description = models.TextField(blank=True)
    payment_address = models.CharField(
        max_length=100, help_text="Stellar wallet address for payment as supplied by the invoice"
    )
    attachment = models.FileField(upload_to='invoices/', blank=True, null=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    flag_payment_address_mismatch = models.BooleanField(default=False)
    flag_duplicate_invoice_number = models.BooleanField(default=False)
    openai_risk_explanation = models.TextField(blank=True)  # populated after analysis
    reviewed_by_buyer = models.BooleanField(default=False)
    buyer_reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-submitted_at']

    def __str__(self):
        return f"Invoice #{self.invoice_number} for Order #{self.order.id}"
