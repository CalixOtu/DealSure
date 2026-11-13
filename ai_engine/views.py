from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from procurement.models import SupplierInvoice
from ai_engine.models import InvoiceFraudAnalysis
from django.core.exceptions import PermissionDenied
from accounts.models import BusinessProfile
from django.contrib.auth import get_user_model
User = get_user_model()

@login_required
def fraud_analysis_view(request, invoice_id):
    invoice = get_object_or_404(SupplierInvoice, id=invoice_id)
    order = invoice.order
    if not (request.user.is_staff or request.user == order.buyer or request.user == order.supplier):
        raise PermissionDenied
    fraud_analysis = getattr(invoice, 'fraud_analysis', None)
    supplier_profile = getattr(order.supplier, 'business_profile', None)
    if not fraud_analysis:
        # Run new analysis
        from ai_engine.ai import perform_fraud_analysis
        fraud_analysis = perform_fraud_analysis(invoice)
        messages.success(request, "Fraud risk analysis completed.")
    # Severity badge class helper
    def risk_level_badge(level):
        if not level:
            return 'bg-gray-200 text-gray-700'
        return {
            'low': 'bg-green-100 text-green-700',
            'moderate': 'bg-yellow-100 text-yellow-700',
            'medium': 'bg-yellow-100 text-yellow-700',
            'high': 'bg-red-100 text-red-700',
        }.get(level.lower(), 'bg-gray-300 text-gray-900')
    return render(request, 'ai_engine/fraud_analysis.html', {
        'invoice': invoice,
        'order': order,
        'fraud_analysis': fraud_analysis,
        'supplier_profile': supplier_profile,
        'escrow_transaction': getattr(order, 'escrow_transaction', None),
        'risk_badge_class': risk_level_badge(fraud_analysis.openai_risk_level),
    })
