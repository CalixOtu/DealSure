import base64
import json
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from stellar_sdk import Account, Keypair, TransactionEnvelope

from accounts.models import BusinessProfile, User
from procurement.models import (
    ProcurementOrder,
    ProcurementOrderAgreement,
    SupplierInvoice,
)

from .models import Dispute, EscrowTransaction, StellarPayment


ESCROW_KEYPAIR = Keypair.random()


class FakeHorizonServer:
    def __init__(self):
        self.submission_count = 0

    def load_account(self, account_id):
        return Account(account_id, sequence=100)

    def submit_transaction(self, envelope):
        self.submission_count += 1
        return {'hash': f'{self.submission_count:064x}'}


@override_settings(
    STELLAR_NETWORK='TESTNET',
    STELLAR_NETWORK_PASSPHRASE='Test SDF Network ; September 2015',
    STELLAR_HORIZON_URL='https://horizon-testnet.invalid',
    STELLAR_ESCROW_SECRET_KEY=ESCROW_KEYPAIR.secret,
    STELLAR_ESCROW_PUBLIC_KEY=ESCROW_KEYPAIR.public_key,
    STELLAR_BASE_FEE=100,
    STELLAR_TRANSACTION_TIMEOUT=300,
)
class StellarEscrowFlowTests(TestCase):
    def setUp(self):
        self.buyer_keypair = Keypair.random()
        self.supplier_keypair = Keypair.random()
        self.buyer = User.objects.create_user(
            email='buyer@example.com',
            password='test-password',
            role=User.Role.BUYER,
        )
        self.supplier = User.objects.create_user(
            email='supplier@example.com',
            password='test-password',
            role=User.Role.SUPPLIER,
        )
        self.admin = User.objects.create_user(
            email='admin@example.com',
            password='test-password',
            role=User.Role.BUYER,
            is_staff=True,
        )
        BusinessProfile.objects.create(
            user=self.buyer,
            business_name='Buyer Business',
            stellar_wallet_address=self.buyer_keypair.public_key,
            stellar_wallet_verified=True,
        )
        BusinessProfile.objects.create(
            user=self.supplier,
            business_name='Supplier Business',
            stellar_wallet_address=self.supplier_keypair.public_key,
            stellar_wallet_verified=True,
        )

    def create_order_and_invoice(self, title='Test order'):
        order = ProcurementOrder.objects.create(
            buyer=self.buyer,
            supplier=self.supplier,
            title=title,
            amount=Decimal('5.00'),
            currency='XLM',
            status=ProcurementOrder.Status.SUPPLIER_ACCEPTED,
        )
        invoice = SupplierInvoice.objects.create(
            order=order,
            submitted_by=self.supplier,
            invoice_number=f'INV-{order.pk}',
            amount=order.amount,
            currency='XLM',
            payment_address=self.supplier_keypair.public_key,
        )
        return order, invoice

    def accept_agreements(self, order):
        self.client.force_login(self.buyer)
        self.client.post(reverse('procurement:agreement_accept', args=[order.id]))
        self.client.force_login(self.supplier)
        self.client.post(reverse('procurement:agreement_accept', args=[order.id]))
        return EscrowTransaction.objects.get(order=order)

    def add_confirmed_funding(self, escrow, tx_hash='a' * 64):
        StellarPayment.objects.create(
            escrow=escrow,
            transaction_hash=tx_hash,
            payment_type=StellarPayment.PaymentType.FUND,
            source_address=escrow.buyer_wallet_address,
            destination_address=escrow.escrow_wallet_address,
            amount=escrow.amount,
            asset='XLM',
            network='TESTNET',
        )
        escrow.status = EscrowTransaction.EscrowStatus.FUNDED
        escrow.save(update_fields=['status', 'updated_at'])

    def test_wallet_challenge_verifies_real_stellar_signature(self):
        self.buyer.business_profile.stellar_wallet_verified = False
        self.buyer.business_profile.save(update_fields=['stellar_wallet_verified'])
        self.client.force_login(self.buyer)

        challenge_response = self.client.post(
            reverse('accounts:stellar_wallet_challenge'),
            data='{}',
            content_type='application/json',
        )
        self.assertEqual(challenge_response.status_code, 200)
        message = challenge_response.json()['message']
        signature = base64.b64encode(
            self.buyer_keypair.sign(message.encode('utf-8'))
        ).decode('ascii')

        verify_response = self.client.post(
            reverse('accounts:stellar_wallet_verify'),
            data=json.dumps({
                'address': self.buyer_keypair.public_key,
                'signature': signature,
            }),
            content_type='application/json',
        )
        self.assertEqual(verify_response.status_code, 200)
        self.buyer.business_profile.refresh_from_db()
        self.assertTrue(self.buyer.business_profile.stellar_wallet_verified)

    def test_agreements_create_escrow_and_full_release_flow(self):
        order, _ = self.create_order_and_invoice()
        escrow = self.accept_agreements(order)
        self.assertEqual(escrow.status, EscrowTransaction.EscrowStatus.PENDING)
        self.assertEqual(escrow.escrow_wallet_address, ESCROW_KEYPAIR.public_key)

        fake_horizon = FakeHorizonServer()
        with patch('escrow.stellar._server', return_value=fake_horizon):
            self.client.force_login(self.buyer)
            prepare_response = self.client.post(
                reverse('escrow:transaction_fund_prepare', args=[escrow.id]),
                data=json.dumps({'address': self.buyer_keypair.public_key}),
                content_type='application/json',
            )
            self.assertEqual(prepare_response.status_code, 200)
            envelope = TransactionEnvelope.from_xdr(
                prepare_response.json()['xdr'],
                'Test SDF Network ; September 2015',
            )
            envelope.sign(self.buyer_keypair)
            submit_response = self.client.post(
                reverse('escrow:transaction_fund_submit', args=[escrow.id]),
                data=json.dumps({
                    'address': self.buyer_keypair.public_key,
                    'signed_xdr': envelope.to_xdr(),
                }),
                content_type='application/json',
            )
            self.assertEqual(submit_response.status_code, 200)

            self.client.force_login(self.supplier)
            self.client.post(reverse('escrow:confirm_delivery', args=[escrow.id]))
            self.client.force_login(self.buyer)
            self.client.post(reverse('escrow:confirm_receipt', args=[escrow.id]))
            release_response = self.client.post(
                reverse('escrow:escrow_release', args=[escrow.id])
            )
            self.assertEqual(release_response.status_code, 302)

        escrow.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(escrow.status, EscrowTransaction.EscrowStatus.RELEASED)
        self.assertEqual(order.status, ProcurementOrder.Status.COMPLETED)
        self.assertEqual(escrow.demo_balance, Decimal('0'))
        self.assertEqual(escrow.payments.count(), 2)

    def test_supplier_can_refund_before_delivery(self):
        order, _ = self.create_order_and_invoice('Refund order')
        escrow = self.accept_agreements(order)
        self.add_confirmed_funding(escrow)

        with patch('escrow.stellar._server', return_value=FakeHorizonServer()):
            self.client.force_login(self.supplier)
            response = self.client.post(
                reverse('escrow:escrow_refund', args=[escrow.id])
            )
        self.assertEqual(response.status_code, 302)
        escrow.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(escrow.status, EscrowTransaction.EscrowStatus.REFUNDED)
        self.assertEqual(order.status, ProcurementOrder.Status.CANCELLED)
        self.assertTrue(
            escrow.payments.filter(
                payment_type=StellarPayment.PaymentType.REFUND
            ).exists()
        )

    def test_admin_dispute_resolution_submits_refund(self):
        order, _ = self.create_order_and_invoice('Dispute order')
        escrow = self.accept_agreements(order)
        self.add_confirmed_funding(escrow, tx_hash='b' * 64)

        self.client.force_login(self.buyer)
        dispute_response = self.client.post(
            reverse('escrow:dispute_create', args=[escrow.id]),
            data={'reason': 'Goods were not delivered.'},
        )
        self.assertEqual(dispute_response.status_code, 302)
        dispute = Dispute.objects.get(escrow=escrow)

        with patch('escrow.stellar._server', return_value=FakeHorizonServer()):
            self.client.force_login(self.admin)
            resolve_response = self.client.post(
                reverse('escrow:dispute_resolve', args=[dispute.id]),
                data={'resolution': 'Refund approved.'},
            )
        self.assertEqual(resolve_response.status_code, 302)
        dispute.refresh_from_db()
        escrow.refresh_from_db()
        self.assertTrue(dispute.resolved)
        self.assertFalse(escrow.is_disputed)
        self.assertEqual(escrow.status, EscrowTransaction.EscrowStatus.REFUNDED)
