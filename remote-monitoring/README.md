# Remote Systemd Service Monitoring

This solution provides monitoring for a remote systemd service (`myapp`) that cannot be accessed via direct SSH due to firewall restrictions.

## Architecture

```
Remote Machine                    AWS Infrastructure
┌─────────────────┐              ┌─────────────────┐
│  myapp service  │              │   Prometheus    │
│  (systemd)      │              │                 │
│                 │              │                 │
│  Monitoring     │◄────────────►│   Grafana       │
│  Agent          │              │                 │
└─────────────────┘              └─────────────────┘
```

## Components

1. **Monitoring Agent** (`monitoring-agent.py`): Collects systemd service metrics and system metrics
2. **Prometheus Configuration**: Scrapes metrics from the remote agent
3. **Grafana Dashboards**: Visualizes the collected metrics
4. **Deployment Scripts**: Easy setup and configuration

## Features

- ✅ Systemd service status monitoring
- ✅ CPU and memory usage tracking
- ✅ Service uptime and restart tracking
- ✅ System resource monitoring
- ✅ Prometheus metrics export
- ✅ Grafana dashboard templates

## Quick Start

1. Deploy the monitoring agent on the remote machine
2. Configure Prometheus to scrape the remote agent
3. Import Grafana dashboards
4. Start monitoring!

See individual component documentation for detailed setup instructions.