#!/usr/bin/env python3
"""
Remote Systemd Service Monitoring Agent

This agent collects metrics from a systemd service and system resources,
exposing them via HTTP for Prometheus scraping.
"""

import os
import sys
import time
import json
import subprocess
import psutil
import argparse
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/monitoring-agent.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class MetricsCollector:
    """Collects systemd service and system metrics"""
    
    def __init__(self, service_name):
        self.service_name = service_name
        self.metrics = {}
        
    def get_systemd_service_status(self):
        """Get systemd service status and metrics"""
        try:
            # Get service status
            result = subprocess.run(
                ['systemctl', 'is-active', self.service_name],
                capture_output=True, text=True, timeout=10
            )
            is_active = result.stdout.strip() == 'active'
            
            # Get service details
            result = subprocess.run(
                ['systemctl', 'show', self.service_name, '--property=ActiveState,SubState,LoadState,UnitFileState,MainPID'],
                capture_output=True, text=True, timeout=10
            )
            
            service_info = {}
            for line in result.stdout.split('\n'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    service_info[key] = value
            
            # Get service uptime
            uptime_seconds = 0
            if is_active and service_info.get('MainPID'):
                try:
                    pid = int(service_info['MainPID'])
                    process = psutil.Process(pid)
                    uptime_seconds = time.time() - process.create_time()
                except (ValueError, psutil.NoSuchProcess):
                    pass
            
            # Get restart count (approximate)
            result = subprocess.run(
                ['journalctl', '-u', self.service_name, '--since', '1 hour ago', '--no-pager'],
                capture_output=True, text=True, timeout=10
            )
            restart_count = result.stdout.count('Started') - 1  # Approximate
            
            return {
                'is_active': is_active,
                'active_state': service_info.get('ActiveState', 'unknown'),
                'sub_state': service_info.get('SubState', 'unknown'),
                'load_state': service_info.get('LoadState', 'unknown'),
                'unit_file_state': service_info.get('UnitFileState', 'unknown'),
                'main_pid': service_info.get('MainPID', '0'),
                'uptime_seconds': uptime_seconds,
                'restart_count_1h': max(0, restart_count)
            }
        except Exception as e:
            logger.error(f"Error getting systemd service status: {e}")
            return {
                'is_active': False,
                'active_state': 'error',
                'sub_state': 'error',
                'load_state': 'error',
                'unit_file_state': 'error',
                'main_pid': '0',
                'uptime_seconds': 0,
                'restart_count_1h': 0
            }
    
    def get_process_metrics(self):
        """Get process-specific metrics if service is running"""
        try:
            result = subprocess.run(
                ['systemctl', 'show', self.service_name, '--property=MainPID'],
                capture_output=True, text=True, timeout=10
            )
            
            main_pid = None
            for line in result.stdout.split('\n'):
                if line.startswith('MainPID='):
                    main_pid = line.split('=', 1)[1]
                    break
            
            if main_pid and main_pid != '0':
                try:
                    pid = int(main_pid)
                    process = psutil.Process(pid)
                    
                    # Get CPU and memory info
                    cpu_percent = process.cpu_percent(interval=0.1)
                    memory_info = process.memory_info()
                    memory_percent = process.memory_percent()
                    
                    # Get children processes
                    children = process.children(recursive=True)
                    total_children = len(children)
                    
                    return {
                        'cpu_percent': cpu_percent,
                        'memory_rss_bytes': memory_info.rss,
                        'memory_vms_bytes': memory_info.vms,
                        'memory_percent': memory_percent,
                        'num_threads': process.num_threads(),
                        'num_children': total_children,
                        'open_files': len(process.open_files()),
                        'connections': len(process.connections())
                    }
                except (ValueError, psutil.NoSuchProcess):
                    pass
            
            return {
                'cpu_percent': 0,
                'memory_rss_bytes': 0,
                'memory_vms_bytes': 0,
                'memory_percent': 0,
                'num_threads': 0,
                'num_children': 0,
                'open_files': 0,
                'connections': 0
            }
        except Exception as e:
            logger.error(f"Error getting process metrics: {e}")
            return {
                'cpu_percent': 0,
                'memory_rss_bytes': 0,
                'memory_vms_bytes': 0,
                'memory_percent': 0,
                'num_threads': 0,
                'num_children': 0,
                'open_files': 0,
                'connections': 0
            }
    
    def get_system_metrics(self):
        """Get system-level metrics"""
        try:
            # CPU metrics
            cpu_percent = psutil.cpu_percent(interval=0.1)
            cpu_count = psutil.cpu_count()
            cpu_freq = psutil.cpu_freq()
            
            # Memory metrics
            memory = psutil.virtual_memory()
            
            # Disk metrics
            disk = psutil.disk_usage('/')
            
            # Network metrics
            network = psutil.net_io_counters()
            
            # Load average
            load_avg = os.getloadavg()
            
            return {
                'cpu_percent': cpu_percent,
                'cpu_count': cpu_count,
                'cpu_freq_mhz': cpu_freq.current if cpu_freq else 0,
                'memory_total_bytes': memory.total,
                'memory_available_bytes': memory.available,
                'memory_used_bytes': memory.used,
                'memory_percent': memory.percent,
                'disk_total_bytes': disk.total,
                'disk_used_bytes': disk.used,
                'disk_free_bytes': disk.free,
                'disk_percent': (disk.used / disk.total) * 100,
                'network_bytes_sent': network.bytes_sent,
                'network_bytes_recv': network.bytes_recv,
                'load_avg_1m': load_avg[0],
                'load_avg_5m': load_avg[1],
                'load_avg_15m': load_avg[2]
            }
        except Exception as e:
            logger.error(f"Error getting system metrics: {e}")
            return {}
    
    def collect_metrics(self):
        """Collect all metrics"""
        timestamp = time.time()
        
        # Collect service metrics
        service_metrics = self.get_systemd_service_status()
        process_metrics = self.get_process_metrics()
        system_metrics = self.get_system_metrics()
        
        self.metrics = {
            'timestamp': timestamp,
            'service': service_metrics,
            'process': process_metrics,
            'system': system_metrics
        }
        
        logger.debug(f"Collected metrics: {json.dumps(self.metrics, indent=2)}")
        return self.metrics

class PrometheusMetricsHandler(BaseHTTPRequestHandler):
    """HTTP handler for Prometheus metrics endpoint"""
    
    def __init__(self, *args, collector=None, **kwargs):
        self.collector = collector
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        if self.path == '/metrics':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain; version=0.0.4; charset=utf-8')
            self.end_headers()
            
            # Collect fresh metrics
            metrics = self.collector.collect_metrics()
            
            # Format as Prometheus metrics
            prometheus_metrics = self.format_prometheus_metrics(metrics)
            self.wfile.write(prometheus_metrics.encode('utf-8'))
        elif self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            health_data = {
                'status': 'healthy',
                'timestamp': time.time(),
                'service': self.collector.service_name
            }
            self.wfile.write(json.dumps(health_data).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Not Found')
    
    def format_prometheus_metrics(self, metrics):
        """Format metrics as Prometheus text format"""
        lines = []
        
        # Service metrics
        service = metrics['service']
        lines.append(f'# HELP systemd_service_active Service active status')
        lines.append(f'# TYPE systemd_service_active gauge')
        lines.append(f'systemd_service_active{{service="{self.collector.service_name}"}} {1 if service["is_active"] else 0}')
        
        lines.append(f'# HELP systemd_service_uptime_seconds Service uptime in seconds')
        lines.append(f'# TYPE systemd_service_uptime_seconds gauge')
        lines.append(f'systemd_service_uptime_seconds{{service="{self.collector.service_name}"}} {service["uptime_seconds"]}')
        
        lines.append(f'# HELP systemd_service_restart_count_1h Service restart count in last hour')
        lines.append(f'# TYPE systemd_service_restart_count_1h counter')
        lines.append(f'systemd_service_restart_count_1h{{service="{self.collector.service_name}"}} {service["restart_count_1h"]}')
        
        # Process metrics
        process = metrics['process']
        lines.append(f'# HELP process_cpu_percent Process CPU usage percentage')
        lines.append(f'# TYPE process_cpu_percent gauge')
        lines.append(f'process_cpu_percent{{service="{self.collector.service_name}"}} {process["cpu_percent"]}')
        
        lines.append(f'# HELP process_memory_rss_bytes Process RSS memory usage in bytes')
        lines.append(f'# TYPE process_memory_rss_bytes gauge')
        lines.append(f'process_memory_rss_bytes{{service="{self.collector.service_name}"}} {process["memory_rss_bytes"]}')
        
        lines.append(f'# HELP process_memory_percent Process memory usage percentage')
        lines.append(f'# TYPE process_memory_percent gauge')
        lines.append(f'process_memory_percent{{service="{self.collector.service_name}"}} {process["memory_percent"]}')
        
        lines.append(f'# HELP process_num_threads Number of threads')
        lines.append(f'# TYPE process_num_threads gauge')
        lines.append(f'process_num_threads{{service="{self.collector.service_name}"}} {process["num_threads"]}')
        
        lines.append(f'# HELP process_num_children Number of child processes')
        lines.append(f'# TYPE process_num_children gauge')
        lines.append(f'process_num_children{{service="{self.collector.service_name}"}} {process["num_children"]}')
        
        # System metrics
        system = metrics['system']
        if system:
            lines.append(f'# HELP system_cpu_percent System CPU usage percentage')
            lines.append(f'# TYPE system_cpu_percent gauge')
            lines.append(f'system_cpu_percent {system["cpu_percent"]}')
            
            lines.append(f'# HELP system_memory_percent System memory usage percentage')
            lines.append(f'# TYPE system_memory_percent gauge')
            lines.append(f'system_memory_percent {system["memory_percent"]}')
            
            lines.append(f'# HELP system_disk_percent System disk usage percentage')
            lines.append(f'# TYPE system_disk_percent gauge')
            lines.append(f'system_disk_percent {system["disk_percent"]}')
            
            lines.append(f'# HELP system_load_average_1m System load average (1 minute)')
            lines.append(f'# TYPE system_load_average_1m gauge')
            lines.append(f'system_load_average_1m {system["load_avg_1m"]}')
        
        return '\n'.join(lines) + '\n'
    
    def log_message(self, format, *args):
        """Override to use our logger"""
        logger.info(f"{self.address_string()} - {format % args}")

def create_handler_class(collector):
    """Create a handler class with the collector instance"""
    return type('MetricsHandler', (PrometheusMetricsHandler,), {'collector': collector})

def main():
    parser = argparse.ArgumentParser(description='Remote Systemd Service Monitoring Agent')
    parser.add_argument('--service', default='myapp', help='Systemd service name to monitor')
    parser.add_argument('--port', type=int, default=9100, help='HTTP server port')
    parser.add_argument('--host', default='0.0.0.0', help='HTTP server host')
    parser.add_argument('--interval', type=int, default=30, help='Metrics collection interval in seconds')
    
    args = parser.parse_args()
    
    logger.info(f"Starting monitoring agent for service: {args.service}")
    logger.info(f"Server will listen on {args.host}:{args.port}")
    
    # Create collector
    collector = MetricsCollector(args.service)
    
    # Create HTTP server
    handler_class = create_handler_class(collector)
    server = HTTPServer((args.host, args.port), handler_class)
    
    # Start metrics collection in background
    def collect_metrics_loop():
        while True:
            try:
                collector.collect_metrics()
                time.sleep(args.interval)
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Error in metrics collection loop: {e}")
                time.sleep(args.interval)
    
    metrics_thread = Thread(target=collect_metrics_loop, daemon=True)
    metrics_thread.start()
    
    logger.info("Monitoring agent started successfully")
    logger.info(f"Metrics available at: http://{args.host}:{args.port}/metrics")
    logger.info(f"Health check available at: http://{args.host}:{args.port}/health")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down monitoring agent...")
        server.shutdown()

if __name__ == '__main__':
    main()