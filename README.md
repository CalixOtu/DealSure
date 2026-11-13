# DealSure

DealSure is a Django procurement, invoice-risk, and Stellar escrow demonstration.
The escrow flow uses real Freighter wallet ownership checks and real Stellar
testnet transactions with test XLM.

## Local setup

```powershell
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Copy `.env.example` to `.env` and set a real Django secret before deployment.

## Create the hosted testnet escrow account

Generate and fund a new Stellar testnet escrow account:

```powershell
python manage.py setup_stellar_escrow --fund-testnet
```

The command prints `STELLAR_ESCROW_SECRET_KEY` and
`STELLAR_ESCROW_PUBLIC_KEY`. Store both in the hosting provider's environment
variables and restart the application. Never commit the secret key.

If a key is already configured, the command validates it and reports its XLM
balance. The hosted escrow account pays transaction fees, so keep a small
testnet XLM reserve in it.

## Demo workflow

1. Buyer and supplier install Freighter, select Stellar Testnet, and fund their
   testnet wallets with Friendbot.
2. Each user opens **Business Profile** and selects **Connect Freighter Wallet**.
   DealSure verifies wallet ownership with a signed, expiring challenge.
3. The buyer creates an XLM procurement order.
4. The supplier accepts the order and submits a matching XLM invoice. The
   invoice payout address is prefilled from the verified supplier wallet.
5. Buyer and supplier accept the transaction agreement. DealSure creates the
   escrow after both acceptances.
6. The buyer funds the escrow. Freighter signs the payment XDR and DealSure
   submits it to Stellar Horizon.
7. The supplier confirms delivery, the buyer confirms receipt, and the buyer
   releases funds. DealSure signs the payout from the hosted escrow account.
8. Before delivery, the supplier can refund the buyer. A dispute pauses normal
   settlement and an administrator can submit either release or refund.

Every confirmed funding, release, and refund is stored with its Stellar
transaction hash and linked to Stellar Expert from the escrow page.

## Hosting variables

At minimum, configure:

```text
DJANGO_SECRET_KEY
ALLOWED_HOSTS
CSRF_TRUSTED_ORIGINS
STELLAR_NETWORK=TESTNET
STELLAR_HORIZON_URL=https://horizon-testnet.stellar.org
STELLAR_NETWORK_PASSPHRASE=Test SDF Network ; September 2015
STELLAR_ESCROW_PUBLIC_KEY
STELLAR_ESCROW_SECRET_KEY
```

Run these during deployment:

```powershell
python manage.py migrate
python manage.py collectstatic --noinput
```

## Validation

```powershell
python manage.py check
python manage.py test escrow
```

## Security scope

This implementation is a custodial, pooled-account testnet escrow for a
demonstration. Real wallets are used, but only test XLM should be deposited.
Do not switch to Stellar Public Network or accept real funds without a security
review, stronger custody controls, transaction reconciliation, monitoring, and
an audited smart-contract or multisignature escrow design.
