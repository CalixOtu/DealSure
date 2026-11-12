from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.utils import timezone
from decimal import Decimal
from .models import EscrowTransaction, EscrowAudit, Dispute, DisputeEvidence
from .forms import DisputeForm, DisputeEvidenceForm
from procurement.models import ProcurementOrder, SupplierInvoice
from django.db.models import Q
from django.conf import settings
from django.http import HttpResponseForbidden

# Helpers

def user_is_admin(user):
    return user.is_staff or user.is_superuser

def user_is_participant(user, escrow):
    return user.id in [escrow.buyer_id, escrow.supplier_id] or user.is_staff

@login_required
def transaction_list(request):
    user = request.user
    qs = EscrowTransaction.objects.filter(Q(buyer=user) | Q(supplier=user)).order_by('-created_at')
    if user.is_staff:
        qs = EscrowTransaction.objects.all().order_by('-created_at')
    return render(request, 'escrow/transaction_list.html', {'transactions': qs})

@login_required
def transaction_detail(request, escrow_id):
    escrow = get_object_or_404(EscrowTransaction, id=escrow_id)
    if not user_is_participant(request.user, escrow):
        return HttpResponseForbidden()
    disputes = escrow.disputes.order_by('-created_at')
    audits = escrow.audits.order_by('-created_at')[:25]
    return render(request, 'escrow/transaction_detail.html', {
        'escrow': escrow, 'disputes': disputes, 'audits': audits
    })

@login_required
def transaction_fund(request, escrow_id):
    escrow = get_object_or_404(EscrowTransaction, id=escrow_id)
    if request.user != escrow.buyer and not request.user.is_staff:
        raise PermissionDenied
    if escrow.status != EscrowTransaction.EscrowStatus.PENDING:
        messages.error(request, 'Escrow not in pending state.')
        return redirect('escrow:transaction_detail', escrow_id=escrow.id)

    # ----- STELLAR TESTNET DEMO -----
    from .stellar import perform_testnet_fund
    demo_tx_hash, demo_error = perform_testnet_fund(escrow)
    if demo_tx_hash:
        escrow.status = EscrowTransaction.EscrowStatus.FUNDED
        escrow.buyer_funded_at = timezone.now()
        escrow.save()
        EscrowAudit.objects.create(
            escrow=escrow, actor=request.user, action='Buyer Funded', details=f'Testnet hash: {demo_tx_hash}'
        )
        messages.success(request, f'Escrow funded (Demo testnet hash: {demo_tx_hash})')
    else:
        messages.error(request, f'Stellar funding failed: {demo_error or "Unknown error"}')
    return redirect('escrow:transaction_detail', escrow_id=escrow.id)

@login_required
def confirm_delivery(request, escrow_id):
    escrow = get_object_or_404(EscrowTransaction, id=escrow_id)
    if request.user != escrow.supplier and not request.user.is_staff:
        raise PermissionDenied
    if escrow.status != EscrowTransaction.EscrowStatus.FUNDED:
        messages.error(request, 'Cannot confirm delivery unless escrow is funded.')
        return redirect('escrow:transaction_detail', escrow_id=escrow.id)
    escrow.supplier_confirmed_delivery = True
    escrow.supplier_confirmed_at = timezone.now()
    escrow.status = EscrowTransaction.EscrowStatus.AWAITING_DELIVERY
    escrow.save()
    EscrowAudit.objects.create(
        escrow=escrow, actor=request.user, action='Supplier Confirmed Delivery', details='Delivery confirmation logged.'
    )
    messages.success(request, 'Delivery confirmation recorded. Awaiting buyer confirmation.')
    return redirect('escrow:transaction_detail', escrow_id=escrow.id)

@login_required
def confirm_receipt(request, escrow_id):
    escrow = get_object_or_404(EscrowTransaction, id=escrow_id)
    if request.user != escrow.buyer and not request.user.is_staff:
        raise PermissionDenied
    if not escrow.supplier_confirmed_delivery or escrow.status not in [EscrowTransaction.EscrowStatus.AWAITING_DELIVERY]:
        messages.error(request, 'Cannot confirm receipt until delivery has been confirmed.')
        return redirect('escrow:transaction_detail', escrow_id=escrow.id)
    escrow.buyer_confirmed_receipt = True
    escrow.buyer_confirmed_at = timezone.now()
    escrow.status = EscrowTransaction.EscrowStatus.RECEIPT_CONFIRMED
    escrow.save()
    EscrowAudit.objects.create(
        escrow=escrow, actor=request.user, action='Buyer Confirmed Receipt', details='Buyer confirmed receipt or delivery.'
    )
    messages.success(request, 'Buyer receipt confirmed. Funds can now be released (demo-only).')
    return redirect('escrow:transaction_detail', escrow_id=escrow.id)

@login_required
def escrow_release(request, escrow_id):
    escrow = get_object_or_404(EscrowTransaction, id=escrow_id)
    if not (request.user == escrow.buyer or request.user.is_staff):
        raise PermissionDenied
    if escrow.is_disputed or escrow.status != EscrowTransaction.EscrowStatus.RECEIPT_CONFIRMED:
        messages.error(request, 'Escrow cannot be released due to active dispute or incomplete confirmations.')
        return redirect('escrow:transaction_detail', escrow_id=escrow.id)
    # ----- STELLAR DEMO: Transfer funds ------
    from .stellar import perform_testnet_release
    tx_hash, tx_error = perform_testnet_release(escrow)
    if tx_hash:
        escrow.status = EscrowTransaction.EscrowStatus.RELEASED
        escrow.released_at = timezone.now()
        escrow.save()
        EscrowAudit.objects.create(
            escrow=escrow, actor=request.user, action='Escrow Released', details=f'Testnet hash: {tx_hash}'
        )
        messages.success(request, f'Funds released to supplier. (Demo testnet hash: {tx_hash})')
    else:
        messages.error(request, f'Release failed: {tx_error}')
    return redirect('escrow:transaction_detail', escrow_id=escrow.id)

@login_required
def escrow_refund(request, escrow_id):
    escrow = get_object_or_404(EscrowTransaction, id=escrow_id)
    if not (request.user == escrow.supplier or request.user.is_staff):
        raise PermissionDenied
    if escrow.is_disputed or escrow.status not in [EscrowTransaction.EscrowStatus.FUNDED, EscrowTransaction.EscrowStatus.AWAITING_DELIVERY]:
        messages.error(request, 'Refund only possible before delivery and if not in dispute.')
        return redirect('escrow:transaction_detail', escrow_id=escrow.id)
    # ----- STELLAR DEMO: Refund ------
    from .stellar import perform_testnet_refund
    tx_hash, tx_error = perform_testnet_refund(escrow)
    if tx_hash:
        escrow.status = EscrowTransaction.EscrowStatus.REFUNDED
        escrow.refunded_at = timezone.now()
        escrow.save()
        EscrowAudit.objects.create(
            escrow=escrow, actor=request.user, action='Escrow Refunded', details=f'Testnet hash: {tx_hash}'
        )
        messages.success(request, f'Escrow refunded to buyer. (Demo testnet hash: {tx_hash})')
    else:
        messages.error(request, f'Refund failed: {tx_error}')
    return redirect('escrow:transaction_detail', escrow_id=escrow.id)

# --- DISPUTES ---
@login_required
def dispute_create(request, escrow_id):
    escrow = get_object_or_404(EscrowTransaction, id=escrow_id)
    if not user_is_participant(request.user, escrow):
        raise PermissionDenied
    if escrow.is_disputed:
        messages.error(request, 'Escrow is already under dispute.')
        return redirect('escrow:transaction_detail', escrow_id=escrow.id)
    if request.method == 'POST':
        form = DisputeForm(request.POST)
        if form.is_valid():
            dispute = form.save(commit=False)
            dispute.escrow = escrow
            dispute.raised_by = request.user
            dispute.save()
            escrow.is_disputed = True
            escrow.status = EscrowTransaction.EscrowStatus.DISPUTED
            escrow.save()
            EscrowAudit.objects.create(escrow=escrow, actor=request.user, action='Dispute Initiated', details=dispute.reason)
            messages.success(request, 'Dispute has been submitted. An admin will review.')
            return redirect('escrow:dispute_detail', dispute_id=dispute.id)
        else:
            messages.error(request, 'Please fix the errors below.')
    else:
        form = DisputeForm()
    return render(request, 'escrow/dispute_form.html', {'form': form, 'escrow': escrow})

@login_required
def dispute_detail(request, dispute_id):
    dispute = get_object_or_404(Dispute, id=dispute_id)
    escrow = dispute.escrow
    if not user_is_participant(request.user, escrow):
        raise PermissionDenied
    evidence = dispute.evidence.order_by('-uploaded_at')
    return render(request, 'escrow/dispute_detail.html', {
        'dispute': dispute, 'escrow': escrow, 'evidence': evidence
    })

@login_required
def evidence_upload(request, dispute_id):
    dispute = get_object_or_404(Dispute, id=dispute_id)
    escrow = dispute.escrow
    if not user_is_participant(request.user, escrow):
        raise PermissionDenied
    if request.method == 'POST':
        form = DisputeEvidenceForm(request.POST, request.FILES)
        if form.is_valid():
            evidence = form.save(commit=False)
            evidence.dispute = dispute
            evidence.uploaded_by = request.user
            evidence.save()
            EscrowAudit.objects.create(escrow=escrow, actor=request.user, action='Evidence Uploaded', details=evidence.description)
            messages.success(request, 'Evidence uploaded.')
            return redirect('escrow:dispute_detail', dispute_id=dispute.id)
        else:
            messages.error(request, 'Error uploading evidence.')
    else:
        form = DisputeEvidenceForm()
    return render(request, 'escrow/evidence_upload.html', {'form': form, 'dispute': dispute})

@user_passes_test(user_is_admin)
def dispute_resolve(request, dispute_id):
    dispute = get_object_or_404(Dispute, id=dispute_id)
    escrow = dispute.escrow
    if dispute.resolved:
        messages.info(request, 'Dispute already resolved.')
        return redirect('escrow:dispute_detail', dispute_id=dispute.id)
    if request.method == 'POST':
        resolution = request.POST.get('resolution')
        dispute.resolved = True
        dispute.resolved_by = request.user
        dispute.resolution = resolution or ''
        dispute.resolved_at = timezone.now()
        dispute.save()
        # Set Escrow status depending on admin decision
        allow_release = request.POST.get('allow_release') == 'on'
        if allow_release:
            escrow.status = EscrowTransaction.EscrowStatus.RECEIPT_CONFIRMED
            escrow.is_disputed = False
            EscrowAudit.objects.create(
                escrow=escrow, actor=request.user, action='Dispute Resolved - Release OK', details=resolution
            )
            messages.success(request, 'Dispute resolved. Funds are eligible for release.')
        else:
            escrow.status = EscrowTransaction.EscrowStatus.REFUNDED
            escrow.is_disputed = False
            EscrowAudit.objects.create(
                escrow=escrow, actor=request.user, action='Dispute Resolved - Refunded', details=resolution
            )
            messages.success(request, 'Dispute resolved. Escrow refunded to buyer.')
        escrow.save()
        return redirect('escrow:transaction_detail', escrow_id=escrow.id)
    return render(request, 'escrow/dispute_resolve.html', {'dispute': dispute, 'escrow': escrow})
