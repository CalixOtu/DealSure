import base64
import binascii
import json
import secrets
import time
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from stellar_sdk import Asset, Keypair, Server, TransactionBuilder, TransactionEnvelope
from stellar_sdk.exceptions import (
    AccountNotFoundException,
    BadRequestError,
    NotFoundError,
)
from stellar_sdk.operation import Payment


class StellarConfigurationError(RuntimeError):
    pass


class StellarTransactionError(RuntimeError):
    pass


def stellar_is_configured():
    try:
        get_escrow_keypair()
    except StellarConfigurationError:
        return False
    return True


def get_escrow_keypair():
    secret = settings.STELLAR_ESCROW_SECRET_KEY.strip()
    if not secret:
        raise StellarConfigurationError(
            'STELLAR_ESCROW_SECRET_KEY is not configured on the server.'
        )
    try:
        keypair = Keypair.from_secret(secret)
    except Exception as exc:
        raise StellarConfigurationError(
            'STELLAR_ESCROW_SECRET_KEY is not a valid Stellar secret key.'
        ) from exc

    configured_public = settings.STELLAR_ESCROW_PUBLIC_KEY.strip()
    if configured_public and configured_public != keypair.public_key:
        raise StellarConfigurationError(
            'STELLAR_ESCROW_PUBLIC_KEY does not match the configured secret key.'
        )
    return keypair


def get_escrow_public_key():
    return get_escrow_keypair().public_key


def is_valid_stellar_address(address):
    if not address or not isinstance(address, str):
        return False
    try:
        Keypair.from_public_key(address.strip())
    except Exception:
        return False
    return True


def _format_amount(amount):
    value = Decimal(amount).quantize(Decimal('0.0000001'))
    if value <= 0:
        raise StellarTransactionError('Payment amount must be greater than zero.')
    return f'{value:.7f}'


def _server():
    return Server(horizon_url=settings.STELLAR_HORIZON_URL)


def _network_error_message(exc):
    if isinstance(exc, (AccountNotFoundException, NotFoundError)):
        return (
            'A Stellar account was not found on this network. Fund the wallet '
            'with Friendbot before continuing.'
        )
    if isinstance(exc, BadRequestError):
        extras = getattr(exc, 'extras', None)
        if extras:
            return f'Stellar rejected the transaction: {json.dumps(extras)}'
        return 'Stellar rejected the transaction.'
    return f'Stellar network request failed: {exc}'


def _decode_signature(signature):
    if not isinstance(signature, str) or not signature.strip():
        raise ValueError('Wallet signature is missing.')
    value = signature.strip()
    try:
        decoded = base64.b64decode(value, validate=True)
        if len(decoded) == 64:
            return decoded
    except (binascii.Error, ValueError):
        pass
    try:
        decoded = bytes.fromhex(value.removeprefix('0x'))
        if len(decoded) == 64:
            return decoded
    except ValueError:
        pass
    raise ValueError('Wallet returned an unsupported signature format.')


def create_wallet_challenge(request):
    nonce = secrets.token_urlsafe(32)
    message = (
        'DealSure Stellar wallet verification\n'
        f'Host: {request.get_host()}\n'
        f'User ID: {request.user.pk}\n'
        f'Network: {settings.STELLAR_NETWORK}\n'
        f'Nonce: {nonce}'
    )
    request.session['stellar_wallet_challenge'] = {
        'message': message,
        'expires_at': int(time.time()) + 300,
        'user_id': request.user.pk,
    }
    request.session.modified = True
    return message


def verify_wallet_challenge(request, address, signature):
    challenge = request.session.get('stellar_wallet_challenge')
    if not challenge:
        raise ValueError('Wallet verification challenge is missing or expired.')
    if challenge.get('user_id') != request.user.pk:
        raise ValueError('Wallet verification challenge does not match this user.')
    if challenge.get('expires_at', 0) < int(time.time()):
        request.session.pop('stellar_wallet_challenge', None)
        raise ValueError('Wallet verification challenge has expired.')

    address = (address or '').strip()
    if not is_valid_stellar_address(address):
        raise ValueError('Freighter returned an invalid Stellar public address.')

    signature_bytes = _decode_signature(signature)
    try:
        Keypair.from_public_key(address).verify(
            challenge['message'].encode('utf-8'),
            signature_bytes,
        )
    except Exception as exc:
        raise ValueError('Wallet signature verification failed.') from exc

    request.session.pop('stellar_wallet_challenge', None)
    request.session.modified = True
    return address


@transaction.atomic
def create_escrow_for_order(order, actor=None):
    from accounts.models import BusinessProfile
    from procurement.models import ProcurementOrderAgreement, SupplierInvoice

    from .models import EscrowAudit, EscrowTransaction

    existing = EscrowTransaction.objects.filter(order=order).first()
    if existing:
        return existing, False
    if not order.supplier_id:
        raise StellarConfigurationError('The order does not have a registered supplier.')
    try:
        invoice = order.invoice
    except SupplierInvoice.DoesNotExist as exc:
        raise StellarConfigurationError('A supplier invoice is required first.') from exc

    buyer_accepted = ProcurementOrderAgreement.objects.filter(
        order=order,
        party=order.buyer,
        role='buyer',
        accepted=True,
    ).exists()
    supplier_accepted = ProcurementOrderAgreement.objects.filter(
        order=order,
        party=order.supplier,
        role='supplier',
        accepted=True,
    ).exists()
    if not (buyer_accepted and supplier_accepted):
        raise StellarConfigurationError(
            'Both buyer and supplier must accept the agreement first.'
        )

    try:
        buyer_profile = order.buyer.business_profile
        supplier_profile = order.supplier.business_profile
    except BusinessProfile.DoesNotExist as exc:
        raise StellarConfigurationError(
            'Both parties need a business profile and verified Stellar wallet.'
        ) from exc

    for label, profile in (
        ('Buyer', buyer_profile),
        ('Supplier', supplier_profile),
    ):
        if not profile.stellar_wallet_verified:
            raise StellarConfigurationError(
                f'{label} must connect and verify a Freighter wallet first.'
            )
        if not is_valid_stellar_address(profile.stellar_wallet_address):
            raise StellarConfigurationError(f'{label} wallet address is invalid.')

    if invoice.payment_address.strip() != supplier_profile.stellar_wallet_address:
        raise StellarConfigurationError(
            'Invoice payment address does not match the supplier verified wallet.'
        )
    if invoice.amount != order.amount or invoice.currency.upper() != order.currency.upper():
        raise StellarConfigurationError(
            'Invoice amount and currency must match the procurement order.'
        )
    if invoice.currency.upper() != 'XLM':
        raise StellarConfigurationError(
            'This hosted escrow demonstration currently supports native XLM only.'
        )

    escrow = EscrowTransaction.objects.create(
        order=order,
        invoice=invoice,
        buyer=order.buyer,
        supplier=order.supplier,
        amount=invoice.amount,
        currency='XLM',
        network=settings.STELLAR_NETWORK,
        escrow_wallet_address=get_escrow_public_key(),
        buyer_wallet_address=buyer_profile.stellar_wallet_address,
        supplier_wallet_address=supplier_profile.stellar_wallet_address,
    )
    EscrowAudit.objects.create(
        escrow=escrow,
        actor=actor,
        action='Escrow Created',
        details=(
            f'{settings.STELLAR_NETWORK} escrow prepared at '
            f'{escrow.escrow_wallet_address}.'
        ),
    )
    return escrow, True


def build_funding_transaction(escrow, source_address):
    source_address = (source_address or '').strip()
    if source_address != escrow.buyer_wallet_address:
        raise StellarTransactionError(
            'Connected wallet does not match the buyer verified wallet.'
        )
    if not is_valid_stellar_address(source_address):
        raise StellarTransactionError('Buyer wallet address is invalid.')
    if escrow.network != settings.STELLAR_NETWORK:
        raise StellarTransactionError('Escrow network does not match server network.')

    try:
        source_account = _server().load_account(source_address)
        transaction = (
            TransactionBuilder(
                source_account=source_account,
                network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
                base_fee=settings.STELLAR_BASE_FEE,
            )
            .append_payment_op(
                destination=escrow.escrow_wallet_address,
                asset=Asset.native(),
                amount=_format_amount(escrow.amount),
            )
            .add_text_memo(f'DealSure #{escrow.pk}')
            .set_timeout(settings.STELLAR_TRANSACTION_TIMEOUT)
            .build()
        )
    except Exception as exc:
        raise StellarTransactionError(_network_error_message(exc)) from exc
    return transaction.to_xdr()


def _validate_funding_envelope(escrow, signed_xdr, source_address):
    try:
        envelope = TransactionEnvelope.from_xdr(
            signed_xdr,
            settings.STELLAR_NETWORK_PASSPHRASE,
        )
    except Exception as exc:
        raise StellarTransactionError('Signed transaction XDR is invalid.') from exc

    transaction = envelope.transaction
    if transaction.source.account_id != source_address:
        raise StellarTransactionError('Funding transaction source wallet changed.')
    if len(transaction.operations) != 1:
        raise StellarTransactionError('Funding transaction must contain one payment.')
    operation = transaction.operations[0]
    if not isinstance(operation, Payment) or operation.source is not None:
        raise StellarTransactionError('Funding transaction operation is invalid.')
    if operation.destination.account_id != escrow.escrow_wallet_address:
        raise StellarTransactionError('Funding destination does not match escrow.')
    if not operation.asset.is_native():
        raise StellarTransactionError('Funding asset must be native XLM.')
    if Decimal(operation.amount) != Decimal(escrow.amount):
        raise StellarTransactionError('Funding amount does not match escrow.')

    source_keypair = Keypair.from_public_key(source_address)
    transaction_hash = envelope.hash()
    signature_valid = False
    for decorated_signature in envelope.signatures:
        try:
            source_keypair.verify(transaction_hash, decorated_signature.signature)
            signature_valid = True
            break
        except Exception:
            continue
    if not signature_valid:
        raise StellarTransactionError(
            'Funding transaction is not signed by the buyer wallet.'
        )
    return envelope


@transaction.atomic
def submit_funding_transaction(escrow, signed_xdr, source_address):
    from .models import StellarPayment

    existing = StellarPayment.objects.filter(
        escrow=escrow,
        payment_type=StellarPayment.PaymentType.FUND,
    ).first()
    if existing:
        return existing

    envelope = _validate_funding_envelope(escrow, signed_xdr, source_address)
    try:
        response = _server().submit_transaction(envelope)
    except Exception as exc:
        raise StellarTransactionError(_network_error_message(exc)) from exc

    return StellarPayment.objects.create(
        escrow=escrow,
        transaction_hash=response['hash'],
        payment_type=StellarPayment.PaymentType.FUND,
        source_address=source_address,
        destination_address=escrow.escrow_wallet_address,
        amount=escrow.amount,
        asset='XLM',
        network=settings.STELLAR_NETWORK,
        memo=f'DealSure #{escrow.pk}',
    )


@transaction.atomic
def _submit_escrow_payment(escrow, destination, payment_type):
    from .models import StellarPayment

    existing = StellarPayment.objects.filter(
        escrow=escrow,
        payment_type=payment_type,
    ).first()
    if existing:
        return existing
    if not StellarPayment.objects.filter(
        escrow=escrow,
        payment_type=StellarPayment.PaymentType.FUND,
        status=StellarPayment.PaymentStatus.CONFIRMED,
    ).exists():
        raise StellarTransactionError('Escrow has no confirmed funding payment.')
    if StellarPayment.objects.filter(
        escrow=escrow,
        payment_type__in=[
            StellarPayment.PaymentType.RELEASE,
            StellarPayment.PaymentType.REFUND,
        ],
        status=StellarPayment.PaymentStatus.CONFIRMED,
    ).exists():
        raise StellarTransactionError('Escrow funds have already been settled.')
    if not is_valid_stellar_address(destination):
        raise StellarTransactionError('Settlement destination wallet is invalid.')

    keypair = get_escrow_keypair()
    try:
        source_account = _server().load_account(keypair.public_key)
        transaction_envelope = (
            TransactionBuilder(
                source_account=source_account,
                network_passphrase=settings.STELLAR_NETWORK_PASSPHRASE,
                base_fee=settings.STELLAR_BASE_FEE,
            )
            .append_payment_op(
                destination=destination,
                asset=Asset.native(),
                amount=_format_amount(escrow.amount),
            )
            .add_text_memo(f'DealSure #{escrow.pk}')
            .set_timeout(settings.STELLAR_TRANSACTION_TIMEOUT)
            .build()
        )
        transaction_envelope.sign(keypair)
        response = _server().submit_transaction(transaction_envelope)
    except Exception as exc:
        raise StellarTransactionError(_network_error_message(exc)) from exc

    return StellarPayment.objects.create(
        escrow=escrow,
        transaction_hash=response['hash'],
        payment_type=payment_type,
        source_address=escrow.escrow_wallet_address,
        destination_address=destination,
        amount=escrow.amount,
        asset='XLM',
        network=settings.STELLAR_NETWORK,
        memo=f'DealSure #{escrow.pk}',
    )


def perform_testnet_release(escrow):
    from .models import StellarPayment

    return _submit_escrow_payment(
        escrow,
        escrow.supplier_wallet_address,
        StellarPayment.PaymentType.RELEASE,
    )


def perform_testnet_refund(escrow):
    from .models import StellarPayment

    return _submit_escrow_payment(
        escrow,
        escrow.buyer_wallet_address,
        StellarPayment.PaymentType.REFUND,
    )
