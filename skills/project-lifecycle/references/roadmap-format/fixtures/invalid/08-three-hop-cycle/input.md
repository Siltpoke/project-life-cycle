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
- depends-on: gate-line
- steps:
  - s1 measure the oracle
  - s2 filter the trigger by that oracle

### gate-line
- binds-to: **○ gate line**
- depends-on: third-line
- steps:
  - s1 inventory the oracle behind each gate

### third-line
- binds-to: **○ CI line**
- depends-on: ci-line
- steps:
  - s1 the third one

## 🚦 In flight

<!-- plc-station-active v1 -->
