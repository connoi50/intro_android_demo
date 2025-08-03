# Push-Based Remote Monitoring Setup Guide

This guide will help you set up monitoring for your remote systemd service using a push-based approach that works with firewall restrictions.

## Prerequisites

- Remote machine with Python 3.6+ and pip
- Access to deploy containers on your AWS infrastructure
- Network connectivity from remote machine to your AWS infrastructure (outbound only)

## Step 1: Deploy Prometheus Pushgateway on AWS

### Option A: Using Docker Compose (Recommended)

1. **Create a directory for the monitoring stack:**
   ```bash
   mkdir -p /opt/monitoring-stack
   cd /opt/monitoring-stack
   ```

2. **Copy the Docker Compose file:**
   ```bash
   # Copy docker-compose.yml to your AWS server
   ```

3. **Start the monitoring stack:**
   ```bash
   docker-compose up -d pushgateway
   ```

4. **Verify Pushgateway is running:**
   ```bash
   curl http://localhost:9091/-/healthy
   ```

### Option B: Using AWS ECS/Fargate

1. **Create an ECS task definition for Pushgateway**
2. **Deploy to ECS with appropriate security groups**
3. **Note the public IP/domain of the Pushgateway**

### Option C: Using AWS EC2

1. **Launch an EC2 instance**
2. **Install Docker:**
   ```bash
   sudo yum update -y
   sudo yum install -y docker
   sudo systemctl start docker
   sudo systemctl enable docker
   ```

3. **Run Pushgateway container:**
   ```bash
   docker run -d \
     --name prometheus-pushgateway \
     -p 9091:9091 \
     prom/pushgateway:v1.6.0 \
     --web.enable-lifecycle \
     --web.enable-admin-api
   ```

## Step 2: Configure Your Existing Prometheus

1. **Update your Prometheus configuration** to scrape the Pushgateway:

   Add this to your `prometheus.yml`:
   ```yaml
   scrape_configs:
     - job_name: 'pushgateway'
       honor_labels: true
       static_configs:
         - targets: ['YOUR_PUSHGATEWAY_IP:9091']
       scrape_interval: 15s
   ```

2. **Reload Prometheus configuration:**
   ```bash
   curl -X POST http://localhost:9090/-/reload
   ```

## Step 3: Deploy Monitoring Agent on Remote Machine

1. **Transfer files to remote machine:**
   ```bash
   scp -r pushgateway-solution/ user@remote-machine:/tmp/
   ```

2. **SSH to remote machine and run deployment:**
   ```bash
   ssh user@remote-machine
   cd /tmp/pushgateway-solution
   sudo chmod +x deploy-push-agent.sh
   sudo ./deploy-push-agent.sh myapp http://YOUR_PUSHGATEWAY_IP:9091 remote-server-01
   ```

3. **Verify the agent is running:**
   ```bash
   sudo systemctl status push-monitoring-agent.service
   sudo journalctl -u push-monitoring-agent.service -f
   ```

## Step 4: Import Grafana Dashboard

1. **Access your Grafana instance**
2. **Go to Dashboards → Import**
3. **Upload the `grafana-dashboard.json` file**
4. **Select your Prometheus data source**
5. **Import the dashboard**

## Step 5: Configure Alerts (Optional)

### Grafana Alerts

1. **Create alert rules in Grafana:**
   - Service down: `systemd_service_active == 0`
   - High CPU: `process_cpu_percent > 80`
   - High Memory: `process_memory_percent > 80`
   - High Restart Rate: `rate(systemd_service_restart_count_1h[5m]) > 0.1`

### Prometheus Alertmanager

1. **Create alert rules file `alerts.yml`:**
   ```yaml
   groups:
   - name: remote-service-alerts
     rules:
     - alert: ServiceDown
       expr: systemd_service_active == 0
       for: 1m
       labels:
         severity: critical
       annotations:
         summary: "Service {{ $labels.service }} is down on {{ $labels.instance }}"
         description: "Service {{ $labels.service }} has been down for more than 1 minute on {{ $labels.instance }}"
   ```

## Step 6: Testing and Verification

1. **Check metrics are being pushed:**
   ```bash
   # On your AWS server
   curl http://YOUR_PUSHGATEWAY_IP:9091/metrics | grep systemd_service_active
   ```

2. **Verify in Prometheus:**
   - Go to Prometheus UI: `http://YOUR_PROMETHEUS_IP:9090`
   - Query: `systemd_service_active`
   - You should see metrics with labels

3. **Check Grafana dashboard:**
   - All panels should show data
   - Service status should be green if running

## Troubleshooting

### Agent Issues

1. **Check agent logs:**
   ```bash
   sudo journalctl -u push-monitoring-agent.service -f
   ```

2. **Test connectivity:**
   ```bash
   curl -v http://YOUR_PUSHGATEWAY_IP:9091/-/healthy
   ```

3. **Verify Python dependencies:**
   ```bash
   pip3 list | grep -E "(psutil|requests)"
   ```

### Pushgateway Issues

1. **Check Pushgateway logs:**
   ```bash
   docker logs prometheus-pushgateway
   ```

2. **Verify metrics are received:**
   ```bash
   curl http://YOUR_PUSHGATEWAY_IP:9091/metrics
   ```

3. **Check network connectivity:**
   ```bash
   telnet YOUR_PUSHGATEWAY_IP 9091
   ```

### Prometheus Issues

1. **Check Prometheus targets:**
   - Go to Status → Targets
   - Verify Pushgateway target is UP

2. **Check Prometheus logs:**
   ```bash
   docker logs prometheus
   ```

3. **Test queries:**
   ```bash
   curl "http://YOUR_PROMETHEUS_IP:9090/api/v1/query?query=systemd_service_active"
   ```

## Security Considerations

1. **Network Security:**
   - Use security groups to restrict access to Pushgateway
   - Consider using HTTPS with certificates
   - Implement basic authentication if needed

2. **Agent Security:**
   - Run agent as non-root user if possible
   - Restrict file permissions
   - Use read-only filesystem where possible

3. **Monitoring Security:**
   - Secure Prometheus and Grafana access
   - Use strong passwords
   - Enable HTTPS

## Scaling

### Multiple Remote Machines

1. **Deploy agent on each machine with unique instance names:**
   ```bash
   sudo ./deploy-push-agent.sh myapp http://YOUR_PUSHGATEWAY_IP:9091 server-01
   sudo ./deploy-push-agent.sh myapp http://YOUR_PUSHGATEWAY_IP:9091 server-02
   ```

2. **Multiple services on same machine:**
   ```bash
   sudo ./deploy-push-agent.sh service1 http://YOUR_PUSHGATEWAY_IP:9091 server-01
   sudo ./deploy-push-agent.sh service2 http://YOUR_PUSHGATEWAY_IP:9091 server-01
   ```

### High Availability

1. **Multiple Pushgateway instances behind load balancer**
2. **Prometheus clustering**
3. **Grafana clustering**

## Maintenance

1. **Regular updates:**
   - Update agent code periodically
   - Keep Python dependencies updated
   - Update Docker images

2. **Monitoring the monitoring:**
   - Monitor Pushgateway health
   - Monitor agent uptime
   - Set up alerts for monitoring system itself

3. **Log rotation:**
   ```bash
   # Add to /etc/logrotate.d/push-monitoring-agent
   /var/log/push-monitoring-agent.log {
       daily
       rotate 7
       compress
       delaycompress
       missingok
       notifempty
       create 644 root root
   }
   ```