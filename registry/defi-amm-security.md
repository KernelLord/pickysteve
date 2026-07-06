---
id: defi-amm-security
name: DeFi AMM Security
description: Audit AMM/DeFi smart contracts for oracle manipulation, reentrancy, rounding, and liquidity-drain exploits.
tags: [defi, amm, smart-contract, security, oracle, reentrancy, web3, audit, slippage, mev]
---
# DeFi AMM Security

Use when reviewing automated-market-maker or DeFi protocol code where a bug means
direct loss of funds.

## Capabilities
- Oracle manipulation and flash-loan attack surfaces; TWAP vs spot price use.
- Reentrancy (including read-only reentrancy) and checks-effects-interactions order.
- Rounding/precision errors that leak value over many small trades.
- Slippage, sandwich/MEV exposure, and fee-on-transfer token assumptions.
- Liquidity-drain and share-inflation (first-depositor) exploits in vaults.

## Notes
Protocol-code security, distinct from chain deployment (see solana-deploy) and
general appsec (see security-reviewer).
