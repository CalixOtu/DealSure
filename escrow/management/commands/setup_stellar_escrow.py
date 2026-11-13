import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from stellar_sdk import Keypair, Server


class Command(BaseCommand):
    help = (
        'Generate or inspect the hosted Stellar escrow account and optionally '
        'fund it with Stellar testnet Friendbot.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--fund-testnet',
            action='store_true',
            help='Fund the escrow account using Stellar testnet Friendbot.',
        )

    def handle(self, *args, **options):
        generated = False
        if settings.STELLAR_ESCROW_SECRET_KEY:
            try:
                keypair = Keypair.from_secret(settings.STELLAR_ESCROW_SECRET_KEY)
            except Exception as exc:
                raise CommandError('Configured escrow secret key is invalid.') from exc
        else:
            keypair = Keypair.random()
            generated = True

        self.stdout.write(f'Stellar network: {settings.STELLAR_NETWORK}')
        self.stdout.write(f'Escrow public key: {keypair.public_key}')
        if generated:
            self.stdout.write(self.style.WARNING(
                'A new escrow key was generated. Store this secret only in your '
                'hosting provider environment variables:'
            ))
            self.stdout.write(f'STELLAR_ESCROW_SECRET_KEY={keypair.secret}')
            self.stdout.write(f'STELLAR_ESCROW_PUBLIC_KEY={keypair.public_key}')
        else:
            self.stdout.write(self.style.SUCCESS(
                'The configured escrow secret key is valid.'
            ))

        if options['fund_testnet']:
            if settings.STELLAR_NETWORK != 'TESTNET':
                raise CommandError('--fund-testnet is only available on TESTNET.')
            response = requests.get(
                'https://friendbot.stellar.org',
                params={'addr': keypair.public_key},
                timeout=30,
            )
            if response.status_code not in {200, 400}:
                raise CommandError(
                    f'Friendbot failed ({response.status_code}): {response.text}'
                )
            if response.status_code == 400 and 'createAccountAlreadyExist' not in response.text:
                raise CommandError(f'Friendbot rejected the account: {response.text}')
            self.stdout.write(self.style.SUCCESS('Testnet escrow account is funded.'))

        try:
            account = Server(settings.STELLAR_HORIZON_URL).accounts().account_id(
                keypair.public_key
            ).call()
        except Exception:
            self.stdout.write(self.style.WARNING(
                'The account is not visible on Horizon yet. Fund it before use.'
            ))
        else:
            native_balance = next(
                (
                    balance['balance']
                    for balance in account.get('balances', [])
                    if balance.get('asset_type') == 'native'
                ),
                '0',
            )
            self.stdout.write(f'Current XLM balance: {native_balance}')
