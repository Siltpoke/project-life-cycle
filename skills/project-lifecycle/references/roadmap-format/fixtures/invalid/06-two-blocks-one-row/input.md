# Roadmap — fixture

## 🛣 Mainline (follow it down)

| station | what | weight | eta |
|---|---|---|---|
| **○ CI line** | a docs-only change should not wait 31 minutes | 🔴 heavy | several sessions |
| **○ gate line** | whether the gates are right themselves | 🔴 heavy | several sessions |

## 🧭 Station plans

<!-- plc-station-plan v1 -->

### ci-line
- binds-to: **○ CI line**
- depends-on: none
- steps:
  - s1 measure the oracle
  - s2 filter the trigger by that oracle

### ci-line-2
- binds-to: **○ CI line**
- depends-on: none
- steps:
  - s1 measure the oracle
  - s2 filter the trigger by that oracle

## 🚦 In flight

<!-- plc-station-active v1 -->
