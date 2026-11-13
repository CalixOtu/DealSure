from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.db import transaction
from django.utils import timezone
from decimal import Decimal
from .models import (
    ProcurementOrder, SupplierOrderDecision, SupplierInvoice, ProcurementOrderAgreement
)
from .forms import ProcurementOrderForm, SupplierOrderDecisionForm, SupplierInvoiceForm
from accounts.models import BusinessProfile
from django.core.exceptions import PermissionDenied
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.views.decorators.http import require_POST
User = get_user_model()

# --- Buyer Views ---
@login_required
def order_list(request):
    if request.user.role not in [User.Role.BUYER, User.Role.BOTH]:
        raise PermissionDenied
    orders = ProcurementOrder.objects.filter(buyer=request.user)
    return render(request, 'procurement/order_list.html', {'orders': orders})

@login_required
def order_create(request):
    if request.user.role not in [User.Role.BUYER, User.Role.BOTH]:
        raise PermissionDenied
    if request.method == 'POST':
        form = ProcurementOrderForm(request.POST, buyer=request.user)
        if form.is_valid():
            instance = form.save(commit=False)
            instance.buyer = request.user
            instance.status = ProcurementOrder.Status.INVITED
            if form.cleaned_data['supplier']:
                instance.supplier = form.cleaned_data['supplier']
            instance.save()
            messages.success(request, 'Procurement order created.')
            return redirect('procurement:order_detail', order_id=instance.id)
        else:
            messages.error(request, 'Please fix the errors below.')
    else:
        form = ProcurementOrderForm(buyer=request.user)
    return render(request, 'procurement/order_create.html', {'form': form})

@login_required
def order_detail(request, order_id):
    order = get_object_or_404(ProcurementOrder, id=order_id)
    if not (request.user == order.buyer or request.user == order.supplier or request.user.is_staff):
        raise PermissionDenied
    invoice = getattr(order, 'invoice', None)
    agreement_buyer = ProcurementOrderAgreement.objects.filter(order=order, party=order.buyer, role='buyer').first()
    agreement_supplier = ProcurementOrderAgreement.objects.filter(order=order, party=order.supplier, role='supplier').first()
    supplier_decision = SupplierOrderDecision.objects.filter(order=order).first()
    escrow_transaction = getattr(order, 'escrow_transaction', None)
    buyer_profile = getattr(order.buyer, 'business_profile', None)
    supplier_profile = getattr(order.supplier, 'business_profile', None) if order.supplier else None
    from escrow.stellar import stellar_is_configured

    can_start_escrow = bool(
        invoice
        and agreement_buyer
        and agreement_buyer.accepted
        and agreement_supplier
        and agreement_supplier.accepted
        and not escrow_transaction
    )
    return render(request, 'procurement/order_detail.html', {
        'order': order,
        'invoice': invoice,
        'agreement_buyer': agreement_buyer,
        'agreement_supplier': agreement_supplier,
        'supplier_decision': supplier_decision,
        'escrow_transaction': escrow_transaction,
        'can_start_escrow': can_start_escrow,
        'buyer_wallet_ready': bool(
            buyer_profile and buyer_profile.stellar_wallet_verified
        ),
        'supplier_wallet_ready': bool(
            supplier_profile and supplier_profile.stellar_wallet_verified
        ),
        'stellar_configured': stellar_is_configured(),
    })

# --- Supplier Views ---
@login_required
def supplier_orders(request):
    if request.user.role not in [User.Role.SUPPLIER, User.Role.BOTH]:
        raise PermissionDenied
    orders = ProcurementOrder.objects.filter(supplier=request.user)
    return render(request, 'procurement/supplier_orders.html', {'orders': orders})

@login_required
def supplier_order_decision(request, order_id):
    order = get_object_or_404(ProcurementOrder, id=order_id)
    if not (order.supplier == request.user):
        raise PermissionDenied
    try:
        prev_decision = SupplierOrderDecision.objects.get(order=order, supplier=request.user)
        form = SupplierOrderDecisionForm(instance=prev_decision)
        already_decided = True
    except SupplierOrderDecision.DoesNotExist:
        form = SupplierOrderDecisionForm()
        already_decided = False
    if request.method == 'POST' and not already_decided:
        form = SupplierOrderDecisionForm(request.POST)
        if form.is_valid():
            decision = form.save(commit=False)
            decision.order = order
            decision.supplier = request.user
            decision.save()
            order.status = ProcurementOrder.Status.SUPPLIER_ACCEPTED if decision.decision == 'accepted' else ProcurementOrder.Status.SUPPLIER_REJECTED
            order.save()
            messages.success(request, 'You have submitted your decision.')
            return redirect('procurement:supplier_orders')
        else:
            messages.error(request, 'Please fix the errors below.')
    return render(request, 'procurement/supplier_order_decision.html', {'form': form, 'order': order, 'already_decided': already_decided})

@login_required
def supplier_invoice_submit(request, order_id):
    order = get_object_or_404(ProcurementOrder, id=order_id)
    if not (order.supplier == request.user):
        raise PermissionDenied
    if hasattr(order, 'invoice'):
        messages.info(request, 'Invoice already submitted for this order.')
        return redirect('procurement:order_detail', order_id=order.id)

    supplier_profile = getattr(request.user, 'business_profile', None)
    if not supplier_profile or not supplier_profile.stellar_wallet_verified:
        messages.error(
            request,
            'Connect and verify your Freighter wallet before submitting an invoice.',
        )
        return redirect('accounts:business_profile')

    if request.method == 'POST':
        form = SupplierInvoiceForm(
            request.POST,
            request.FILES,
            supplier=request.user,
            order=order,
        )
        if form.is_valid():
            invoice = form.save(commit=False)
            invoice.order = order
            invoice.submitted_by = request.user
            # Fraud prevention check: Compare payment address against previously verified
            try:
                buss_profile = request.user.business_profile
                if (
                    buss_profile.stellar_wallet_verified
                    and buss_profile.stellar_wallet_address
                    and invoice.payment_address.strip() != buss_profile.stellar_wallet_address.strip()
                ):
                    invoice.flag_payment_address_mismatch = True
            except BusinessProfile.DoesNotExist:
                invoice.flag_payment_address_mismatch = False

            # Check for duplicate invoice number by the same supplier
            if SupplierInvoice.objects.filter(invoice_number=invoice.invoice_number, submitted_by=request.user).exists():
                invoice.flag_duplicate_invoice_number = True

            # --- AI: OpenAI API Risk Explanation -- #
            from django.conf import settings
            import os
            import openai
            openai_api_key = os.environ.get('OPENAI_API_KEY')
            ai_explanation = ''
            if openai_api_key:
                try:
                    openai.api_key = openai_api_key
                    system = """
                            You are an assistant for B2B payments fraud risk explanation. Input is a structured supplier invoice, linked to a purchase order, and verified payment address. Explain any discrepancies and fraud risks for a payment manager. Do NOT claim that this invoice is genuine or not fraudulent. Highlight any risk and provide a concise business explanation.
                            """
                    prompt = f"""
                            Order:
                            title: {order.title}\n  desc: {order.description}\n  amount: {order.amount}\n  currency: {order.currency}\nSupplier business profile:\n  name: {getattr(order.supplier.business_profile, 'business_name', '(unknown)') if hasattr(order.supplier, 'business_profile') else '(missing)'}\n  verified_wallet: {getattr(order.supplier.business_profile, 'stellar_wallet_address', '(none)') if hasattr(order.supplier, 'business_profile') else '(missing)'}\nInvoice submitted:\n  invoice_number: {invoice.invoice_number}\n  amount: {invoice.amount}\n  currency: {invoice.currency}\n  payment_address: {invoice.payment_address}\nDiscrepancy analysis:\n"""
                    resp = openai.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[
                            {"role": "system", "content": system},
                            {"role": "user", "content": prompt}
                        ],
                        max_tokens=200
                    )
                    ai_explanation = resp.choices[0].message.content.strip()
                except Exception as e:
                    ai_explanation = 'AI analysis unavailable.'
            else:
                ai_explanation = 'No OpenAI API key provided.'
            invoice.openai_risk_explanation = ai_explanation
            invoice.save()
            messages.success(request, 'Invoice submitted. Fraud risk will be checked.')
            try:
                from escrow.stellar import (
                    StellarConfigurationError,
                    create_escrow_for_order,
                )

                escrow, created = create_escrow_for_order(order, actor=request.user)
                if created:
                    messages.success(
                        request,
                        f'Stellar escrow #{escrow.id} was created automatically.',
                    )
            except StellarConfigurationError:
                # Agreements or host escrow configuration may not be ready yet.
                pass
            return redirect('procurement:order_detail', order_id=order.id)
        else:
            messages.error(request, 'Please fix the errors below.')
    else:
        form = SupplierInvoiceForm(supplier=request.user, order=order)
    return render(request, 'procurement/supplier_invoice_submit.html', {'form': form, 'order': order})

# --- Agreement Acceptance ---
@login_required
@require_POST
def agreement_accept(request, order_id):
    order = get_object_or_404(ProcurementOrder, id=order_id)
    if not (request.user == order.buyer or request.user == order.supplier):
        raise PermissionDenied
    role = 'buyer' if (request.user == order.buyer) else 'supplier'
    agreement, created = ProcurementOrderAgreement.objects.get_or_create(
        order=order, party=request.user, role=role
    )
    if not agreement.accepted:
        agreement.accepted = True
        agreement.accepted_at = timezone.now()
        agreement.save()
        messages.success(request, 'You have accepted the transaction agreement.')
    else:
        messages.info(request, 'Agreement already accepted.')
    buyer_accepted = ProcurementOrderAgreement.objects.filter(
        order=order,
        role='buyer',
        accepted=True,
    ).exists()
    supplier_accepted = ProcurementOrderAgreement.objects.filter(
        order=order,
        role='supplier',
        accepted=True,
    ).exists()
    if buyer_accepted and supplier_accepted and hasattr(order, 'invoice'):
        try:
            from escrow.stellar import (
                StellarConfigurationError,
                create_escrow_for_order,
            )

            escrow, escrow_created = create_escrow_for_order(
                order,
                actor=request.user,
            )
            if escrow_created:
                messages.success(
                    request,
                    f'Stellar escrow #{escrow.id} is ready for buyer funding.',
                )
        except StellarConfigurationError as exc:
            messages.warning(request, f'Agreement saved. Escrow is not ready: {exc}')
    return redirect('procurement:order_detail', order_id=order.id)


@login_required
@require_POST
def escrow_start(request, order_id):
    order = get_object_or_404(ProcurementOrder, id=order_id)
    if not (
        request.user == order.buyer
        or request.user == order.supplier
        or request.user.is_staff
    ):
        raise PermissionDenied
    try:
        from escrow.stellar import (
            StellarConfigurationError,
            create_escrow_for_order,
        )

        escrow, created = create_escrow_for_order(order, actor=request.user)
    except StellarConfigurationError as exc:
        messages.error(request, f'Unable to create Stellar escrow: {exc}')
    else:
        if created:
            messages.success(request, f'Stellar escrow #{escrow.id} created.')
        else:
            messages.info(request, f'Stellar escrow #{escrow.id} already exists.')
    return redirect('procurement:order_detail', order_id=order.id)
