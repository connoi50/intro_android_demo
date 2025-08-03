#!/bin/bash

# Quick Start Script for Push-Based Remote Monitoring
# This script automates the setup of the monitoring infrastructure

set -e

echo "🚀 Quick Start: Push-Based Remote Monitoring Setup"
echo "=================================================="

# Configuration
PUSHGATEWAY_IP=${1:-"YOUR_PUSHGATEWAY_IP"}
REMOTE_SERVICE=${2:-"myapp"}
INSTANCE_NAME=${3:-"remote-server-01"}

if [[ "$PUSHGATEWAY_IP" == "YOUR_PUSHGATEWAY_IP" ]]; then
    echo "❌ Please provide the Pushgateway IP address"
    echo ""
    echo "Usage: $0 <pushgateway_ip> [service_name] [instance_name]"
    echo ""
    echo "Example:"
    echo "  $0 10.0.1.100 myapp remote-server-01"
    echo ""
    echo "Or for AWS public IP:"
    echo "  $0 52.23.45.67 myapp production-server"
    exit 1
fi

echo "📋 Configuration:"
echo "   - Pushgateway IP: $PUSHGATEWAY_IP"
echo "   - Service to monitor: $REMOTE_SERVICE"
echo "   - Instance name: $INSTANCE_NAME"
echo ""

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "❌ This script must be run as root (use sudo)"
   exit 1
fi

echo "🔍 Checking prerequisites..."

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.6+ first."
    exit 1
fi

# Check pip
if ! command -v pip3 &> /dev/null && ! command -v pip &> /dev/null; then
    echo "❌ Python pip is not installed. Please install pip first."
    exit 1
fi

# Check curl
if ! command -v curl &> /dev/null; then
    echo "❌ curl is not installed. Please install curl first."
    exit 1
fi

echo "✅ Prerequisites check passed"
echo ""

# Test connectivity to Pushgateway
echo "🌐 Testing connectivity to Pushgateway..."
if curl -s --connect-timeout 10 "$PUSHGATEWAY_IP:9091/-/healthy" > /dev/null; then
    echo "✅ Pushgateway is accessible"
else
    echo "⚠️  Warning: Cannot reach Pushgateway at $PUSHGATEWAY_IP:9091"
    echo "   Please ensure:"
    echo "   1. The Pushgateway is running on your AWS infrastructure"
    echo "   2. Port 9091 is open in your security groups"
    echo "   3. Network connectivity is available"
    echo ""
    read -p "Continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Setup cancelled."
        exit 1
    fi
fi

echo ""

# Deploy the monitoring agent
echo "📦 Deploying monitoring agent..."
if [ -f "deploy-push-agent.sh" ]; then
    chmod +x deploy-push-agent.sh
    ./deploy-push-agent.sh "$REMOTE_SERVICE" "http://$PUSHGATEWAY_IP:9091" "$INSTANCE_NAME"
else
    echo "❌ deploy-push-agent.sh not found in current directory"
    echo "Please run this script from the pushgateway-solution directory"
    exit 1
fi

echo ""
echo "🎉 Setup completed successfully!"
echo ""
echo "📊 Next steps:"
echo "   1. Verify metrics are being collected:"
echo "      sudo journalctl -u push-monitoring-agent.service -f"
echo ""
echo "   2. Check metrics in Pushgateway:"
echo "      curl http://$PUSHGATEWAY_IP:9091/metrics | grep systemd_service_active"
echo ""
echo "   3. Configure your Prometheus to scrape the Pushgateway:"
echo "      Add to prometheus.yml:"
echo "      - job_name: 'pushgateway'"
echo "        honor_labels: true"
echo "        static_configs:"
echo "          - targets: ['$PUSHGATEWAY_IP:9091']"
echo ""
echo "   4. Import the Grafana dashboard:"
echo "      - Upload grafana-dashboard.json to Grafana"
echo "      - Select your Prometheus data source"
echo ""
echo "🔧 Useful commands:"
echo "   - View agent logs: sudo journalctl -u push-monitoring-agent.service -f"
echo "   - Restart agent: sudo systemctl restart push-monitoring-agent.service"
echo "   - Check status: sudo systemctl status push-monitoring-agent.service"
echo "   - Test connectivity: curl http://$PUSHGATEWAY_IP:9091/-/healthy"
echo ""
echo "📈 Monitor your service at:"
echo "   - Pushgateway: http://$PUSHGATEWAY_IP:9091"
echo "   - Your Prometheus: http://YOUR_PROMETHEUS_IP:9090"
echo "   - Your Grafana: http://YOUR_GRAFANA_IP:3000"