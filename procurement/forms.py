from django import forms
from decimal import Decimal
from .models import ProcurementOrder, SupplierOrderDecision, SupplierInvoice
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

User = get_user_model()


class ProcurementOrderForm(forms.ModelForm):
    class Meta:
        model = ProcurementOrder
        fields = ['title', 'description', 'amount', 'currency', 'supplier', 'supplier_invite_email']

    def __init__(self, *args, **kwargs):
        buyer = kwargs.pop('buyer', None)
        super().__init__(*args, **kwargs)
        self.fields['supplier'].required = False
        self.fields['supplier_invite_email'].required = False
        # Only show users who are suppliers and verified
        self.fields['supplier'].queryset = User.objects.filter(role__in=['supplier','both'], is_active=True)
        if buyer:
            self.fields['supplier'].queryset = self.fields['supplier'].queryset.exclude(id=buyer.id)

    def clean(self):
        cleaned = super().clean()
        supplier = cleaned.get('supplier')
        invite_email = cleaned.get('supplier_invite_email')
        if supplier and invite_email:
            raise ValidationError("Select a supplier OR invite via email, not both.")
        if not supplier and not invite_email:
            raise ValidationError("You must select an existing supplier or invite a new one via email.")
        return cleaned


class SupplierOrderDecisionForm(forms.ModelForm):
    class Meta:
        model = SupplierOrderDecision
        fields = ['decision', 'comment']


class SupplierInvoiceForm(forms.ModelForm):
    class Meta:
        model = SupplierInvoice
        fields = [
            'invoice_number', 'amount', 'currency', 'description', 'payment_address', 'attachment'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows':3}),
        }

    def __init__(self, *args, **kwargs):
        supplier = kwargs.pop('supplier', None)
        super().__init__(*args, **kwargs)

    def clean_amount(self):
        amt = self.cleaned_data['amount']
        if amt <= Decimal('0.0'):
            raise forms.ValidationError('Amount must be positive.')
        return amt
