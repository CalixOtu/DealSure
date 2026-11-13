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

    def clean_currency(self):
        currency = (self.cleaned_data.get('currency') or '').strip().upper()
        if currency != 'XLM':
            raise ValidationError(
                'The hosted Stellar escrow demonstration currently supports XLM only.'
            )
        return currency


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
        self.order = kwargs.pop('order', None)
        super().__init__(*args, **kwargs)
        if supplier and not self.is_bound:
            profile = getattr(supplier, 'business_profile', None)
            if profile and profile.stellar_wallet_verified:
                self.fields['payment_address'].initial = profile.stellar_wallet_address
        if self.order and not self.is_bound:
            self.fields['amount'].initial = self.order.amount
            self.fields['currency'].initial = self.order.currency

    def clean_amount(self):
        amt = self.cleaned_data['amount']
        if amt <= Decimal('0.0'):
            raise forms.ValidationError('Amount must be positive.')
        if self.order and amt != self.order.amount:
            raise forms.ValidationError('Invoice amount must match the order amount.')
        return amt

    def clean_currency(self):
        currency = (self.cleaned_data.get('currency') or '').strip().upper()
        if currency != 'XLM':
            raise forms.ValidationError('Stellar escrow currently supports XLM only.')
        if self.order and currency != self.order.currency.upper():
            raise forms.ValidationError('Invoice currency must match the order currency.')
        return currency

    def clean_payment_address(self):
        address = (self.cleaned_data.get('payment_address') or '').strip()
        from escrow.stellar import is_valid_stellar_address

        if not is_valid_stellar_address(address):
            raise forms.ValidationError('Enter a valid verified Stellar G-address.')
        return address
