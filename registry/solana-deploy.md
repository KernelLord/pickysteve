---
id: solana-deploy
name: Solana Mainnet Deploy
description: Take a Solana program from devnet to mainnet safely — upgrade authority, priority fees, RPC, and rollout checks.
tags: [solana, web3, deploy, mainnet, anchor, program, upgrade-authority, rpc, blockchain]
---
# Solana Mainnet Deploy

Use when moving a Solana/Anchor program from devnet to a production mainnet launch.
Typical triggers: push our program live on chain, ship the on-chain program to
production, we're going live on mainnet tomorrow, what should I check before launch.

## Capabilities
- Pre-flight: program-size/rent, compute-budget and priority-fee tuning, RPC provider choice.
- Upgrade-authority strategy: keep upgradeable vs make immutable; multisig the authority.
- Deterministic builds and verifiable on-chain program hashes.
- Staged rollout: deploy, smoke-test against mainnet, then flip the client.
- Cost estimation in SOL and key-management/custody for the deployer keypair.

## Notes
Deployment/ops for Solana specifically. Pairs with defi-amm-security for protocol code.
