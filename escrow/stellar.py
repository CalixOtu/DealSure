import os
from decimal import Decimal

def perform_testnet_fund(escrow):
    """
    Mocks a Stellar testnet transfer: buyer funds the (demo) escrow wallet.
    Returns (tx_hash, error)
    """
    # In a real integration, use python-stellar-sdk and a dedicated escrow account.
    # For hackathon, just fake a tx hash.
    import uuid
    # Simulate possible error (demo)
    if not os.environ.get('DEMO_STELLAR_CAN_FUND', '1') == '1':
        return (None, 'Testnet funding disabled for demo')
    fake_hash = uuid.uuid4().hex
    return (fake_hash, None)

def perform_testnet_release(escrow):
    """
    Mocks releasing funds to supplier wallet on Stellar testnet.
    """
    import uuid
    # In a real system, check if supplier's payout address is verified and used!
    if not escrow.supplier.business_profile.stellar_wallet_verified:
        return (None, 'Supplier wallet not verified.')
    fake_hash = uuid.uuid4().hex
    return (fake_hash, None)

def perform_testnet_refund(escrow):
    """
    Mocks refunding funds to buyer's wallet/address (testnet-only).
    """
    import uuid
    # Buyer payout address not modeled; just for demo purposes.
    fake_hash = uuid.uuid4().hex
    return (fake_hash, None)
