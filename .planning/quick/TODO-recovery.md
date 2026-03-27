# Recovery & Auto-Start — TODO

## vco recover
- Reads agents.json + STATE.md to determine what was running when system died
- Relaunches bot, monitor, and agents that were active
- Posts recovery report to #alerts: "System was down for X time, here's what was in progress"
- Handles: power outage, reboot, bot crash, Claude outage

## Auto-start (systemd)
- systemd service for `vco bot` (auto-restarts on crash)
- systemd service for `vco monitor` (or started by bot)
- After-boot recovery: systemd triggers `vco recover` on startup
- Watchdog integration: systemd WatchdogSec for monitor heartbeat

## Post-factum alerts
- On recovery: compare last heartbeat timestamp vs now → calculate downtime
- Post to #alerts: "System recovered after {duration} downtime. {N} agents were running. Relaunching..."
- If agents crashed during downtime: classify as transient (relaunch) vs persistent (alert only)
