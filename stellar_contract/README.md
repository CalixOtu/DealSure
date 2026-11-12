# DealSure Soroban Escrow Demo Contract

WARNING: This contract is a scaffold for hackathon demonstration only. It does not handle real funds, and is not safe for production or mainnet!

## Purpose
Models an escrow between buyer and supplier:
- Buyer funds contract.
- Supplier payout address is set at init.
- Funds can only be released after explicit storage of buyer+supplier confirmations.
- Dispute state is tracked. Only admin can resolve disputes.

## Structure
- Both buyer and supplier Stellar testnet addresses are checked.
- State variables track funding and confirmation status.
- Only release/refund per explicit workflow/order.

## How to Build/Deploy on Stellar Testnet

1. Install Rust and Soroban CLI:
   https://soroban.stellar.org/docs/getting-started

2. Build:
   cd stellar_contract
   cargo build --target wasm32-unknown-unknown --release

3. Deploy contract to Stellar testnet using your testnet wallet keys and the Soroban CLI:

   soroban contract deploy --wasm target/wasm32-unknown-unknown/release/dealsure_escrow.wasm \
    --source buyer_account_key \
    --rpc-url https://rpc-futurenet.stellar.org 

4. Initialize contract state with buyer/supplier addresses and amount:

   soroban contract invoke --id <contract_id> --fn initialize --arg buyer --arg supplier --arg amount --arg currency

## Limitations
- This code is provided as-is, for hackathon demo only.
- No frontend or mainnet deployment.
