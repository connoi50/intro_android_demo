#!/bin/bash

# Remote Systemd Service Monitoring Agent Deployment Script
# This script installs and configures the monitoring agent on the remote machine

set -e

# Configuration
SERVICE_NAME=${1:-myapp}
AGENT_PORT=${2:-9100}
INSTALL_DIR="/opt/monitoring-agent"
SERVICE_FILE="monitoring-agent.service"

echo "🚀 Deploying Remote Systemd Service Monitoring Agent"
echo "Service to monitor: $SERVICE_NAME"
echo "Agent port: $AGENT_PORT"
echo "Install directory: $INSTALL_DIR"

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "❌ This script must be run as root (use sudo)"
   exit 1
fi

# Create installation directory
echo "📁 Creating installation directory..."
mkdir -p "$INSTALL_DIR"

# Copy monitoring agent files
echo "📋 Copying monitoring agent files..."
cp monitoring-agent.py "$INSTALL_DIR/"
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
chmod +x "$INSTALL_DIR/monitoring-agent.py"

# Update service file with correct service name and port
echo "⚙️  Configuring systemd service..."
sed "s/--service myapp/--service $SERVICE_NAME/g; s/--port 9100/--port $AGENT_PORT/g" "$SERVICE_FILE" > "$INSTALL_DIR/$SERVICE_FILE"

# Install systemd service
echo "🔧 Installing systemd service..."
cp "$INSTALL_DIR/$SERVICE_FILE" /etc/systemd/system/
systemctl daemon-reload

# Enable and start the service
echo "▶️  Starting monitoring agent service..."
systemctl enable monitoring-agent.service
systemctl start monitoring-agent.service

# Check service status
echo "📊 Checking service status..."
sleep 2
systemctl status monitoring-agent.service --no-pager

# Test metrics endpoint
echo "🧪 Testing metrics endpoint..."
sleep 3
if curl -s "http://localhost:$AGENT_PORT/metrics" > /dev/null; then
    echo "✅ Metrics endpoint is working!"
    echo "📈 Metrics available at: http://localhost:$AGENT_PORT/metrics"
    echo "🏥 Health check available at: http://localhost:$AGENT_PORT/health"
else
    echo "⚠️  Metrics endpoint test failed. Check logs with: journalctl -u monitoring-agent.service"
fi

# Configure firewall (if ufw is available)
if command -v ufw &> /dev/null; then
    echo "🔥 Configuring firewall..."
    ufw allow $AGENT_PORT/tcp
    echo "✅ Firewall rule added for port $AGENT_PORT"
fi

# Configure firewall (if firewalld is available)
if command -v firewall-cmd &> /dev/null; then
    echo "🔥 Configuring firewalld..."
    firewall-cmd --permanent --add-port=$AGENT_PORT/tcp
    firewall-cmd --reload
    echo "✅ Firewall rule added for port $AGENT_PORT"
fi

echo ""
echo "🎉 Deployment completed successfully!"
echo ""
echo "📋 Summary:"
echo "   - Monitoring agent installed in: $INSTALL_DIR"
echo "   - Service name: $SERVICE_NAME"
echo "   - Agent port: $AGENT_PORT"
echo "   - Systemd service: monitoring-agent.service"
echo ""
echo "📝 Useful commands:"
echo "   - View logs: journalctl -u monitoring-agent.service -f"
echo "   - Restart service: systemctl restart monitoring-agent.service"
echo "   - Check status: systemctl status monitoring-agent.service"
echo "   - View metrics: curl http://localhost:$AGENT_PORT/metrics"
echo ""
echo "🔗 Next steps:"
echo "   1. Configure your Prometheus to scrape http://REMOTE_IP:$AGENT_PORT/metrics"
echo "   2. Import the Grafana dashboard from grafana-dashboard.json"
echo "   3. Set up alerts in Grafana for service downtime"