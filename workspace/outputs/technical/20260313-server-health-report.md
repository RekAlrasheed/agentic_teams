# Server Health Report
**Date:** 2026-03-13
**Agent:** Arch (Technical)
**Task:** Comprehensive server health check

---

## Summary

| Area | Status | Severity |
|------|--------|----------|
| CPU | OK | ✅ |
| Memory | Under Pressure | ⚠️ |
| Disk (Main) | 85% Used | ⚠️ |
| Disk (iOS Sim) | 98% Used | 🔴 CRITICAL |
| Network | OK | ✅ |
| Navaia Dashboard | Running | ✅ |
| Docker: genexa-embedding-service | Healthy | ✅ |
| Docker: weaviate-smart-agent | Healthy | ✅ |
| Docker: weaviate-test | **UNHEALTHY** | 🔴 |
| Telegram Bot | Running (conflict recovered) | ⚠️ |

---

## 1. CPU

- **Load Average:** 4.42, 3.00, 2.59 (1m, 5m, 15m)
- **CPU Usage:** 17% user / 24% sys / 59% idle
- **Uptime:** 3 days, 19+ hours

**Assessment:** CPU load is elevated but not critical. The 4.42 1-minute load on an Apple Silicon (8-core) machine is within acceptable range. Idle at 59% is healthy.

---

## 2. Memory

**Total RAM:** 8 GB

| Category | Usage |
|----------|-------|
| Wired (kernel) | 2.04 GB |
| Active | 1.08 GB |
| Inactive | 1.03 GB |
| **Compressed** | **3.18 GB** |
| Free | 0.05 GB |

**Assessment:** ⚠️ **HIGH MEMORY PRESSURE.** Only 50 MB free. The system is heavily relying on memory compression (3.18 GB compressed). This can cause sluggishness, swapping, and degraded application performance.

**Root Cause:** Docker containers (especially genexa-embedding-service at ~2 GB), VS Code extensions, and multiple Python processes are consuming most of the 8 GB.

---

## 3. Disk Usage

| Volume | Used | Total | % Used | Status |
|--------|------|-------|--------|--------|
| `/` (System) | 9.1 GB | 460 GB | 13% | ✅ |
| `/System/Volumes/Data` | 361 GB | 460 GB | **85%** | ⚠️ |
| `/System/Volumes/VM` (swap) | 16 GB | 460 GB | 20% | ✅ |
| iOS Simulator | 16 GB | 16.5 GB | **98%** | 🔴 CRITICAL |

**Assessment:**
- Main data volume at 85% is approaching warning threshold (typically critical at 90%).
- iOS Simulator volume is critically full with only ~460 MB remaining. This may break Xcode/simulator operations.

---

## 4. Network Connectivity

**Test:** Ping to 8.8.8.8 (Google DNS)
- Packets: 3/3 received (0% packet loss)
- Latency: min=40.6ms / avg=43.2ms / max=47.6ms

**Assessment:** ✅ Network connectivity is healthy with no packet loss and normal latency.

---

## 5. Application Services

### Navaia Dashboard (Port 7777)
- **Status:** ✅ Running (Python, PID 45885)
- **Connections:** 2 active (from Chrome browser)
- **Assessment:** Healthy

### Docker Containers

| Container | Image | Uptime | Memory | Port | Status |
|-----------|-------|--------|--------|------|--------|
| genexa-embedding-service | twk_qa_portalcopy-embedding-service | 45h | 2.0 GB / 3.8 GB (52%) | 8000 | ✅ Healthy |
| weaviate-smart-agent | weaviate:1.28.2 | 28h | 60 MB / 3.8 GB (1.5%) | 8095 | ✅ Healthy |
| weaviate-test | weaviate:1.28.2 | 45h | 234 MB / 3.8 GB (6%) | 8080 | 🔴 **UNHEALTHY** |

**Note:** `weaviate-test` is marked unhealthy by Docker. It has been running 45h in unhealthy state and is also consuming 6.88 MB/7.11 MB of network I/O, suggesting it's still processing requests despite the health check failure.

### Telegram Bot
- **Status:** ⚠️ Running with recovered errors
- **Issues Found in Logs:**
  1. **DNS resolution failure** (`[Errno 8] nodename nor servname provided`) — Temporary network outage, self-recovered
  2. **Conflict error** — `terminated by other getUpdates request; make sure only one bot instance is running` — indicates multiple bot instances were running simultaneously at some point

---

## 6. Recommendations

### Immediate Actions (High Priority)

1. **🔴 Free up iOS Simulator disk space**
   ```bash
   xcrun simctl delete unavailable
   ```
   This removes unused simulator devices and can free several GB.

2. **🔴 Investigate weaviate-test unhealthy container**
   ```bash
   docker inspect weaviate-test | grep -A 10 '"Health"'
   docker logs weaviate-test --tail 50
   ```
   Consider restarting: `docker restart weaviate-test`

3. **⚠️ Reduce memory pressure**
   - Consider stopping `weaviate-test` if it's not actively needed (saves ~234 MB)
   - Review if genexa-embedding-service needs to be running 24/7 or can be started on demand
   - Close unused browser tabs and VS Code extensions

### Medium Priority

4. **⚠️ Monitor disk usage** — At 85%, main volume needs attention within the next few weeks
   - Run `du -sh ~/Desktop/* ~/Downloads/*` to find large files
   - Consider moving large files to external storage

5. **⚠️ Ensure single Telegram bot instance**
   - Review startup scripts to prevent duplicate bot launches
   - Consider a PID file lock in `telegram_bridge.py`

### Low Priority

6. CPU load is fine — no action needed
7. Network latency is normal — no action needed

---

## Appendix: Open Ports

| Port | Service | Status |
|------|---------|--------|
| 7777 | Navaia Dashboard (Python) | Active |
| 8000 | genexa-embedding-service (Docker) | Active |
| 8080 | weaviate-test (Docker) | Active (Unhealthy) |
| 8095 | weaviate-smart-agent (Docker) | Active |
| 50051 | weaviate-test gRPC | Active |
| 50052 | weaviate-smart-agent gRPC | Active |
| 5000/7000 | ControlCenter (AirPlay/Bonjour) | Active |

---

*Report generated by Arch (Technical Agent) — 2026-03-13*
