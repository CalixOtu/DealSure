import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from procurement.models import ProcurementOrder

from .forms import DisputeEvidenceForm, DisputeForm
from .models import (
    Dispute,
    DisputeEvidence,
    EscrowAudit,
    EscrowTransaction,
    StellarPayment,
)
from .stellar import (
    StellarConfigurationError,
    StellarTransactionError,
    build_funding_transaction,
    perform_testnet_refund,
    perform_testnet_release,
    stellar_is_configured,
    submit_funding_transaction,
)


def user_is_admin(user):
    return user.is_staff or user.is_superuser


def user_is_participant(user, escrow):
    return user.id in [escrow.buyer_id, escrow.supplier_id] or user.is_staff


def _payment_error(request, prefix, exc):
    messages.error(request, f'{prefix}: {exc}')


@login_required
def transaction_list(request):
    user = request.user
    qs = EscrowTransaction.objects.select_related(
        'order',
        'buyer',
        'supplier',
    ).filter(Q(buyer=user) | Q(supplier=user))
    if user.is_staff:
        qs = EscrowTransaction.objects.select_related(
            'order',
            'buyer',
            'supplier',
        ).all()
    return render(request, 'escrow/transaction_list.html', {
        'transactions': qs.order_by('-created_at'),
    })


@login_required
def transaction_detail(request, escrow_id):
    escrow = get_object_or_404(
        EscrowTransaction.objects.select_related('order', 'buyer', 'supplier'),
        id=escrow_id,
    )
    if not user_is_participant(request.user, escrow):
        raise PermissionDenied

    held_statuses = {
        EscrowTransaction.EscrowStatus.FUNDED,
        EscrowTransaction.EscrowStatus.AWAITING_DELIVERY,
        EscrowTransaction.EscrowStatus.DELIVERY_CONFIRMED,
        EscrowTransaction.EscrowStatus.RECEIPT_CONFIRMED,
    }
    can_release = (
        (request.user == escrow.buyer or request.user.is_staff)
        and escrow.status == EscrowTransaction.EscrowStatus.RECEIPT_CONFIRMED
        and not escrow.is_disputed
    )
    can_refund = (
        (request.user == escrow.supplier or request.user.is_staff)
        and escrow.status in {
            EscrowTransaction.EscrowStatus.FUNDED,
            EscrowTransaction.EscrowStatus.AWAITING_DELIVERY,
        }
        and not escrow.is_disputed
    )
    can_dispute = escrow.status in held_statuses and not escrow.is_disputed
    return render(request, 'escrow/transaction_detail.html', {
        'escrow': escrow,
        'disputes': escrow.disputes.order_by('-created_at'),
        'audits': escrow.audits.order_by('-created_at')[:25],
        'payments': escrow.payments.order_by('created_at'),
        'can_release': can_release,
        'can_refund': can_refund,
        'can_dispute': can_dispute,
        'stellar_configured': stellar_is_configured(),
        'stellar_explorer_base_url': settings.STELLAR_EXPLORER_BASE_URL.rstrip('/'),
    })


@login_required
@require_POST
def transaction_fund_prepare(request, escrow_id):
    escrow = get_object_or_404(EscrowTransaction, id=escrow_id)
    if request.user != escrow.buyer and not request.user.is_staff:
        raise PermissionDenied
    if escrow.status != EscrowTransaction.EscrowStatus.PENDING:
        return JsonResponse({'error': 'Escrow is not pending funding.'}, status=409)
    try:
        payload = json.loads(request.body or b'{}')
        address = (payload.get('address') or '').strip()
        xdr = build_funding_transaction(escrow, address)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid request body.'}, status=400)
    except (StellarConfigurationError, StellarTransactionError) as exc:
        return JsonResponse({'error': str(exc)}, status=400)

    return JsonResponse({
        'xdr': xdr,
        'network': settings.STELLAR_NETWORK,
        'network_passphrase': settings.STELLAR_NETWORK_PASSPHRASE,
        'escrow_address': escrow.escrow_wallet_address,
        'amount': str(escrow.amount),
        'asset': escrow.currency,
    })


@login_required
@require_POST
def transaction_fund_submit(request, escrow_id):
    try:
        payload = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid request body.'}, status=400)

    with transaction.atomic():
        escrow = get_object_or_404(
            EscrowTransaction.objects.select_for_update(),
            id=escrow_id,
        )
        if request.user != escrow.buyer and not request.user.is_staff:
            raise PermissionDenied
        if escrow.status != EscrowTransaction.EscrowStatus.PENDING:
            return JsonResponse({'error': 'Escrow is not pending funding.'}, status=409)

        address = (payload.get('address') or '').strip()
        signed_xdr = payload.get('signed_xdr') or ''
        try:
            payment = submit_funding_transaction(
                escrow,
                signed_xdr,
                address,
            )
        except (StellarConfigurationError, StellarTransactionError) as exc:
            return JsonResponse({'error': str(exc)}, status=400)

        escrow.status = EscrowTransaction.EscrowStatus.FUNDED
        escrow.buyer_funded_at = timezone.now()
        escrow.save(update_fields=['status', 'buyer_funded_at', 'updated_at'])
        EscrowAudit.objects.create(
            escrow=escrow,
            actor=request.user,
            action='Buyer Funded',
            details=f'Stellar transaction: {payment.transaction_hash}',
        )

    return JsonResponse({
        'ok': True,
        'transaction_hash': payment.transaction_hash,
        'redirect_url': reverse(
            'escrow:transaction_detail',
            kwargs={'escrow_id': escrow.id},
        ),
    })


@login_required
@require_POST
def confirm_delivery(request, escrow_id):
    with transaction.atomic():
        escrow = get_object_or_404(
            EscrowTransaction.objects.select_for_update(),
            id=escrow_id,
        )
        if request.user != escrow.supplier and not request.user.is_staff:
            raise PermissionDenied
        if escrow.status != EscrowTransaction.EscrowStatus.FUNDED:
            messages.error(request, 'Cannot confirm delivery unless escrow is funded.')
            return redirect('escrow:transaction_detail', escrow_id=escrow.id)
        escrow.supplier_confirmed_delivery = True
        escrow.supplier_confirmed_at = timezone.now()
        escrow.status = EscrowTransaction.EscrowStatus.DELIVERY_CONFIRMED
        escrow.save(update_fields=[
            'supplier_confirmed_delivery',
            'supplier_confirmed_at',
            'status',
            'updated_at',
        ])
        EscrowAudit.objects.create(
            escrow=escrow,
            actor=request.user,
            action='Supplier Confirmed Delivery',
            details='Delivery confirmation logged. Funds remain held.',
        )
    messages.success(request, 'Delivery confirmed. Awaiting buyer receipt confirmation.')
    return redirect('escrow:transaction_detail', escrow_id=escrow.id)


@login_required
@require_POST
def confirm_receipt(request, escrow_id):
    with transaction.atomic():
        escrow = get_object_or_404(
            EscrowTransaction.objects.select_for_update(),
            id=escrow_id,
        )
        if request.user != escrow.buyer and not request.user.is_staff:
            raise PermissionDenied
        allowed_statuses = {
            EscrowTransaction.EscrowStatus.DELIVERY_CONFIRMED,
            EscrowTransaction.EscrowStatus.AWAITING_DELIVERY,
        }
        if not escrow.supplier_confirmed_delivery or escrow.status not in allowed_statuses:
            messages.error(request, 'Cannot confirm receipt before delivery confirmation.')
            return redirect('escrow:transaction_detail', escrow_id=escrow.id)
        escrow.buyer_confirmed_receipt = True
        escrow.buyer_confirmed_at = timezone.now()
        escrow.status = EscrowTransaction.EscrowStatus.RECEIPT_CONFIRMED
        escrow.save(update_fields=[
            'buyer_confirmed_receipt',
            'buyer_confirmed_at',
            'status',
            'updated_at',
        ])
        EscrowAudit.objects.create(
            escrow=escrow,
            actor=request.user,
            action='Buyer Confirmed Receipt',
            details='Buyer confirmed receipt. Funds are eligible for release.',
        )
    messages.success(request, 'Receipt confirmed. Funds can now be released.')
    return redirect('escrow:transaction_detail', escrow_id=escrow.id)


@login_required
@require_POST
def escrow_release(request, escrow_id):
    with transaction.atomic():
        escrow = get_object_or_404(
            EscrowTransaction.objects.select_for_update().select_related('order'),
            id=escrow_id,
        )
        if not (request.user == escrow.buyer or request.user.is_staff):
            raise PermissionDenied
        if escrow.is_disputed or escrow.status != EscrowTransaction.EscrowStatus.RECEIPT_CONFIRMED:
            messages.error(
                request,
                'Escrow cannot be released due to a dispute or incomplete confirmations.',
            )
            return redirect('escrow:transaction_detail', escrow_id=escrow.id)
        try:
            payment = perform_testnet_release(escrow)
        except (StellarConfigurationError, StellarTransactionError) as exc:
            _payment_error(request, 'Release failed', exc)
            return redirect('escrow:transaction_detail', escrow_id=escrow.id)

        escrow.status = EscrowTransaction.EscrowStatus.RELEASED
        escrow.released_at = timezone.now()
        escrow.save(update_fields=['status', 'released_at', 'updated_at'])
        escrow.order.status = ProcurementOrder.Status.COMPLETED
        escrow.order.save(update_fields=['status', 'updated_at'])
        EscrowAudit.objects.create(
            escrow=escrow,
            actor=request.user,
            action='Escrow Released',
            details=f'Stellar transaction: {payment.transaction_hash}',
        )
    messages.success(request, 'Funds released to the supplier wallet on Stellar.')
    return redirect('escrow:transaction_detail', escrow_id=escrow.id)


@login_required
@require_POST
def escrow_refund(request, escrow_id):
    with transaction.atomic():
        escrow = get_object_or_404(
            EscrowTransaction.objects.select_for_update().select_related('order'),
            id=escrow_id,
        )
        if not (request.user == escrow.supplier or request.user.is_staff):
            raise PermissionDenied
        refundable_statuses = {
            EscrowTransaction.EscrowStatus.FUNDED,
            EscrowTransaction.EscrowStatus.AWAITING_DELIVERY,
        }
        if escrow.is_disputed or escrow.status not in refundable_statuses:
            messages.error(
                request,
                'Refund is only available before delivery and outside a dispute.',
            )
            return redirect('escrow:transaction_detail', escrow_id=escrow.id)
        try:
            payment = perform_testnet_refund(escrow)
        except (StellarConfigurationError, StellarTransactionError) as exc:
            _payment_error(request, 'Refund failed', exc)
            return redirect('escrow:transaction_detail', escrow_id=escrow.id)

        escrow.status = EscrowTransaction.EscrowStatus.REFUNDED
        escrow.refunded_at = timezone.now()
        escrow.save(update_fields=['status', 'refunded_at', 'updated_at'])
        escrow.order.status = ProcurementOrder.Status.CANCELLED
        escrow.order.save(update_fields=['status', 'updated_at'])
        EscrowAudit.objects.create(
            escrow=escrow,
            actor=request.user,
            action='Escrow Refunded',
            details=f'Stellar transaction: {payment.transaction_hash}',
        )
    messages.success(request, 'Escrow refunded to the buyer wallet on Stellar.')
    return redirect('escrow:transaction_detail', escrow_id=escrow.id)


@login_required
def dispute_create(request, escrow_id):
    escrow = get_object_or_404(EscrowTransaction, id=escrow_id)
    if not user_is_participant(request.user, escrow):
        raise PermissionDenied
    disputable_statuses = {
        EscrowTransaction.EscrowStatus.FUNDED,
        EscrowTransaction.EscrowStatus.AWAITING_DELIVERY,
        EscrowTransaction.EscrowStatus.DELIVERY_CONFIRMED,
        EscrowTransaction.EscrowStatus.RECEIPT_CONFIRMED,
    }
    if escrow.is_disputed:
        messages.error(request, 'Escrow is already under dispute.')
        return redirect('escrow:transaction_detail', escrow_id=escrow.id)
    if escrow.status not in disputable_statuses:
        messages.error(request, 'Only funded, unsettled escrows can be disputed.')
        return redirect('escrow:transaction_detail', escrow_id=escrow.id)

    if request.method == 'POST':
        form = DisputeForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                locked_escrow = EscrowTransaction.objects.select_for_update().get(
                    id=escrow.id
                )
                dispute = form.save(commit=False)
                dispute.escrow = locked_escrow
                dispute.raised_by = request.user
                dispute.save()
                locked_escrow.status_before_dispute = locked_escrow.status
                locked_escrow.is_disputed = True
                locked_escrow.status = EscrowTransaction.EscrowStatus.DISPUTED
                locked_escrow.save(update_fields=[
                    'status_before_dispute',
                    'is_disputed',
                    'status',
                    'updated_at',
                ])
                EscrowAudit.objects.create(
                    escrow=locked_escrow,
                    actor=request.user,
                    action='Dispute Initiated',
                    details=dispute.reason,
                )
            messages.success(request, 'Dispute submitted. Settlement is paused.')
            return redirect('escrow:dispute_detail', dispute_id=dispute.id)
        messages.error(request, 'Please fix the errors below.')
    else:
        form = DisputeForm()
    return render(request, 'escrow/dispute_form.html', {
        'form': form,
        'escrow': escrow,
    })


@login_required
def dispute_detail(request, dispute_id):
    dispute = get_object_or_404(
        Dispute.objects.select_related('escrow', 'raised_by', 'resolved_by'),
        id=dispute_id,
    )
    if not user_is_participant(request.user, dispute.escrow):
        raise PermissionDenied
    return render(request, 'escrow/dispute_detail.html', {
        'dispute': dispute,
        'escrow': dispute.escrow,
        'evidence': dispute.evidence.order_by('-uploaded_at'),
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
            EscrowAudit.objects.create(
                escrow=escrow,
                actor=request.user,
                action='Evidence Uploaded',
                details=evidence.description,
            )
            messages.success(request, 'Evidence uploaded.')
            return redirect('escrow:dispute_detail', dispute_id=dispute.id)
        messages.error(request, 'Error uploading evidence.')
    else:
        form = DisputeEvidenceForm()
    return render(request, 'escrow/evidence_upload.html', {
        'form': form,
        'dispute': dispute,
    })


@login_required
@user_passes_test(user_is_admin)
def dispute_resolve(request, dispute_id):
    dispute = get_object_or_404(Dispute, id=dispute_id)
    if dispute.resolved:
        messages.info(request, 'Dispute already resolved.')
        return redirect('escrow:dispute_detail', dispute_id=dispute.id)

    if request.method == 'POST':
        resolution = (request.POST.get('resolution') or '').strip()
        if not resolution:
            messages.error(request, 'Resolution notes are required.')
            return render(request, 'escrow/dispute_resolve.html', {
                'dispute': dispute,
                'escrow': dispute.escrow,
            })

        with transaction.atomic():
            dispute = Dispute.objects.select_for_update().select_related(
                'escrow__order'
            ).get(id=dispute.id)
            escrow = EscrowTransaction.objects.select_for_update().get(
                id=dispute.escrow_id
            )
            allow_release = request.POST.get('allow_release') == 'on'
            try:
                if allow_release:
                    payment = perform_testnet_release(escrow)
                    escrow.status = EscrowTransaction.EscrowStatus.RELEASED
                    escrow.released_at = timezone.now()
                    order_status = ProcurementOrder.Status.COMPLETED
                    action = 'Dispute Resolved - Released'
                else:
                    payment = perform_testnet_refund(escrow)
                    escrow.status = EscrowTransaction.EscrowStatus.REFUNDED
                    escrow.refunded_at = timezone.now()
                    order_status = ProcurementOrder.Status.CANCELLED
                    action = 'Dispute Resolved - Refunded'
            except (StellarConfigurationError, StellarTransactionError) as exc:
                _payment_error(request, 'Dispute settlement failed', exc)
                return redirect('escrow:dispute_detail', dispute_id=dispute.id)

            dispute.resolved = True
            dispute.resolved_by = request.user
            dispute.resolution = resolution
            dispute.resolved_at = timezone.now()
            dispute.save(update_fields=[
                'resolved',
                'resolved_by',
                'resolution',
                'resolved_at',
            ])
            escrow.is_disputed = False
            escrow.save(update_fields=[
                'status',
                'released_at',
                'refunded_at',
                'is_disputed',
                'updated_at',
            ])
            escrow.order.status = order_status
            escrow.order.save(update_fields=['status', 'updated_at'])
            EscrowAudit.objects.create(
                escrow=escrow,
                actor=request.user,
                action=action,
                details=f'{resolution}\nStellar transaction: {payment.transaction_hash}',
            )

        messages.success(request, 'Dispute resolved and Stellar settlement completed.')
        return redirect('escrow:transaction_detail', escrow_id=escrow.id)

    return render(request, 'escrow/dispute_resolve.html', {
        'dispute': dispute,
        'escrow': dispute.escrow,
    })
