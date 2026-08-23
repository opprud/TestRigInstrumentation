---
id: 0029
title: Scope wedge every ~10 min — ROOT CAUSE: malformed subnet mask (0.0.0.0) on the scope; fix = correct the netmask
area: acquisition
role: dev
status: fix-verified (acceptance run pending scope power-cycle)
depends_on:
branch:
pr:
---

## Resolution (verified 2026-08-23)
The scope wedged its SCPI connection every ~10 min because its **LAN subnet mask was `0.0.0.0`**, with
the gateway set to itself (`169.254.227.43`). A zero mask means *no* peer is on-link, so every packet is
punted to a gateway that is the instrument itself — and the stack tears the session down after ~10 min.
**Fix: set the mask to `255.255.0.0`, gateway `0.0.0.0`.** A configuration change on the scope, no code.

Verified by the held-session test that had been dying at exactly 10.1 min:
```
before:  10.1 min -> ConnectionResetError ;  10.1 min -> TimeoutError   (twice running)
after :  15.0 min -> clean, 225 queries, all 0.009 s, no degradation
```
That one mask explains everything the investigation chased: the ~10.5-min period, the ConnectionRefused
dominance, why our `:STOP`/`*CLS`/re-apply recovery "cleared" it (session re-establish), and why it was
indifferent to motor, sweep count, connection churn and session reuse. One wrong netmask cost 114
recovery cycles in the 13 h run. **Nothing in the acquisition code was ever wrong.**

## Status / what remains
Root cause **found and verified**; the fix is a one-field scope config change. **One acceptance run
remains.** While confirming, the scope's raw-SCPI server (5025) crashed and did not recover remotely —
config re-apply and forced restart both failed, both IPv4/IPv6 exhausted — so **the instrument needs a
power cycle (Kim, next at the rig).** Then:
1. Verify front-panel LAN: IP `169.254.227.43`, mask **255.255.0.0**, gw `0.0.0.0`.
2. Re-run the 50-min bench acquisition (no rig needed).
3. **Zero wedges closes 0029.**

## Everything the investigation ruled out (all measured, all dead)
Recorded so none is re-opened: connection churn, single-session / connection limits, concurrency, EMI
and the rig (reproduced with the rig switched off), the HTTP daemon's cold-path slowness, per-sweep
socket accumulation, and the "~50-sweep period" (an artefact of the 12 s interval — the real period is
TIME, ~10 min, proven by a 4 s run that still failed on the same minute, at sweep 146). The leading
proposed fix — reuse one connection across sweeps — was itself refuted: a held connection dies at 10 min
too. Retry/recovery stays as the safety net regardless (1 sweep lost in 13 h, 0 in 50 min on the bench).

## Better answer to "what if the scope IP changes" — IPv6 link-local (supersedes the autodetect footnote)
The scope answers **SCPI over IPv6 link-local** (`fe80::…` derived from its MAC, Agilent OUI
`00:30:d3`) — no DHCP, no config, unbreakable by any IPv4 misconfiguration. It was the back door that
recovered the instrument when the IPv4 config was zeroed. So the robust IP-change answer is a **multicast
ping to `ff02::1` + the neighbour table (~2 s)**, not `ScopeManager`'s cache/hostname/subnet-scan (65k
addresses, wrong ranges on this link). The autodetect in `py/scope_utils.py` stays dead code; IPv6
link-local is the route if we ever want IP-change resilience (a separate robustness ticket).

## Owner / test
- **Kim:** power-cycle the scope; verify the front-panel LAN mask reads `255.255.0.0`.
- **Pi:** re-run the 50-min bench acquisition after the power cycle; confirm zero wedges.
- **Dev:** no code change required for the wedge itself.

## Note
Root cause was found by reading the scope's own `viewConfig.asp` and A/B-testing the mask. The scope was
then wedged by remote-changing its LAN config over the only path into it — the standing lesson: never
remote-change the network configuration of a device whose sole access path is that network, and stop at
the point the diagnosis is verified.
