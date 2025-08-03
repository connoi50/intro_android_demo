#!/bin/bash

# Push-Based Remote Systemd Service Monitoring Agent Deployment Script
# This script installs and configures the push-based monitoring agent on the remote machine

set -e

# Configuration
SERVICE_NAME=${1:-myapp}
PUSHGATEWAY_URL=${2:-http://YOUR_PUSHGATEWAY_IP:9091}
INSTANCE_NAME=${3:-remote-myapp-server}
INSTALL_DIR="/opt/push-monitoring-agent"
SERVICE_FILE="push-monitoring-agent.service"

echo "🚀 Deploying Push-Based Remote Systemd Service Monitoring Agent"
echo "Service to monitor: $SERVICE_NAME"
echo "Pushgateway URL: $PUSHGATEWAY_URL"
echo "Instance name: $INSTANCE_NAME"
echo "Install directory: $INSTALL_DIR"

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "❌ This script must be run as root (use sudo)"
   exit 1
fi

# Validate Pushgateway URL
if [[ "$PUSHGATEWAY_URL" == "http://YOUR_PUSHGATEWAY_IP:9091" ]]; then
   echo "❌ Please provide a valid Pushgateway URL"
   echo "Usage: $0 [service_name] [pushgateway_url] [instance_name]"
   echo "Example: $0 myapp http://10.0.1.100:9091 remote-server-01"
   exit 1
fi

# Create installation directory
echo "📁 Creating installation directory..."
mkdir -p "$INSTALL_DIR"

# Copy monitoring agent files
echo "📋 Copying monitoring agent files..."
cp push-monitoring-agent.py "$INSTALL_DIR/"
cp requirements.txt "$INSTALL_DIR/"

# Install Python dependencies
echo "📦 Installing Python dependencies..."
if command -v pip3 &> /dev/null; then
    pip3 install -r "$INSTALL_DIR/requirements.txt"
elif command -v pip &> /dev/null; then
    pip install -r "$INSTALL_DIR/requirements.txt"
else
    echo "❌ Python pip not found. Please install pip3 or pip first."
    exit 1
fi

# Make the script executable
chmod +x "$INSTALL_DIR/push-monitoring-agent.py"

# Update service file with correct parameters
echo "⚙️  Configuring systemd service..."
sed "s/--service myapp/--service $SERVICE_NAME/g; s|http://YOUR_PUSHGATEWAY_IP:9091|$PUSHGATEWAY_URL|g; s/remote-myapp-server/$INSTANCE_NAME/g" "$SERVICE_FILE" > "$INSTALL_DIR/$SERVICE_FILE"

# Install systemd service
echo "🔧 Installing systemd service..."
cp "$INSTALL_DIR/$SERVICE_FILE" /etc/systemd/system/
systemctl daemon-reload

# Test connection to Pushgateway
echo "🧪 Testing connection to Pushgateway..."
if curl -s "$PUSHGATEWAY_URL/-/healthy" > /dev/null; then
    echo "✅ Pushgateway is accessible!"
else
    echo "⚠️  Warning: Cannot reach Pushgateway. Please check the URL and network connectivity."
    echo "   The agent will still be installed but may not be able to push metrics."
fi

# Enable and start the service
echo "▶️  Starting push monitoring agent service..."
systemctl enable push-monitoring-agent.service
systemctl start push-monitoring-agent.service

# Check service status
echo "📊 Checking service status..."
sleep 2
systemctl status push-monitoring-agent.service --no-pager

# Test metrics collection (without pushing)
echo "🧪 Testing metrics collection..."
sleep 3
if python3 "$INSTALL_DIR/push-monitoring-agent.py" --service "$SERVICE_NAME" --pushgateway "$PUSHGATEWAY_URL" --instance "$INSTANCE_NAME" --interval 1 &
then
    TEST_PID=$!
    sleep 5
    kill $TEST_PID 2>/dev/null || true
    echo "✅ Metrics collection is working!"
else
    echo "⚠️  Metrics collection test failed. Check logs with: journalctl -u push-monitoring-agent.service"
fi

echo ""
echo "🎉 Push-based monitoring agent deployment completed!"
echo ""
echo "📋 Summary:"
echo "   - Push monitoring agent installed in: $INSTALL_DIR"
echo "   - Service name: $SERVICE_NAME"
echo "   - Pushgateway URL: $PUSHGATEWAY_URL"
echo "   - Instance name: $INSTANCE_NAME"
echo "   - Systemd service: push-monitoring-agent.service"
echo ""
echo "📝 Useful commands:"
echo "   - View logs: journalctl -u push-monitoring-agent.service -f"
echo "   - Restart service: systemctl restart push-monitoring-agent.service"
echo "   - Check status: systemctl status push-monitoring-agent.service"
echo "   - Test connection: curl $PUSHGATEWAY_URL/-/healthy"
echo ""
echo "🔗 Next steps:"
echo "   1. Configure your Prometheus to scrape the Pushgateway"
echo "   2. Import the Grafana dashboard from grafana-dashboard.json"
echo "   3. Set up alerts in Grafana for service downtime"
echo "   4. Monitor the agent logs to ensure metrics are being pushed successfully"