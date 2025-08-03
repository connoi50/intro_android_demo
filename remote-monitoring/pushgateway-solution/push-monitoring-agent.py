#!/usr/bin/env python3
"""
Push-Based Remote Systemd Service Monitoring Agent

This agent collects metrics from a systemd service and system resources,
then pushes them to Prometheus Pushgateway.
"""

import os
import sys
import time
import json
import subprocess
import psutil
import argparse
import requests
from datetime import datetime
from threading import Thread
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/push-monitoring-agent.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class PushMetricsCollector:
    """Collects systemd service and system metrics, pushes to Pushgateway"""
    
    def __init__(self, service_name, pushgateway_url, instance_name):
        self.service_name = service_name
        self.pushgateway_url = pushgateway_url.rstrip('/')
        self.instance_name = instance_name
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
    
    def format_prometheus_metrics(self, metrics):
        """Format metrics as Prometheus text format"""
        lines = []
        
        # Service metrics
        service = metrics['service']
        lines.append(f'# HELP systemd_service_active Service active status')
        lines.append(f'# TYPE systemd_service_active gauge')
        lines.append(f'systemd_service_active{{service="{self.service_name}",instance="{self.instance_name}"}} {1 if service["is_active"] else 0}')
        
        lines.append(f'# HELP systemd_service_uptime_seconds Service uptime in seconds')
        lines.append(f'# TYPE systemd_service_uptime_seconds gauge')
        lines.append(f'systemd_service_uptime_seconds{{service="{self.service_name}",instance="{self.instance_name}"}} {service["uptime_seconds"]}')
        
        lines.append(f'# HELP systemd_service_restart_count_1h Service restart count in last hour')
        lines.append(f'# TYPE systemd_service_restart_count_1h counter')
        lines.append(f'systemd_service_restart_count_1h{{service="{self.service_name}",instance="{self.instance_name}"}} {service["restart_count_1h"]}')
        
        # Process metrics
        process = metrics['process']
        lines.append(f'# HELP process_cpu_percent Process CPU usage percentage')
        lines.append(f'# TYPE process_cpu_percent gauge')
        lines.append(f'process_cpu_percent{{service="{self.service_name}",instance="{self.instance_name}"}} {process["cpu_percent"]}')
        
        lines.append(f'# HELP process_memory_rss_bytes Process RSS memory usage in bytes')
        lines.append(f'# TYPE process_memory_rss_bytes gauge')
        lines.append(f'process_memory_rss_bytes{{service="{self.service_name}",instance="{self.instance_name}"}} {process["memory_rss_bytes"]}')
        
        lines.append(f'# HELP process_memory_percent Process memory usage percentage')
        lines.append(f'# TYPE process_memory_percent gauge')
        lines.append(f'process_memory_percent{{service="{self.service_name}",instance="{self.instance_name}"}} {process["memory_percent"]}')
        
        lines.append(f'# HELP process_num_threads Number of threads')
        lines.append(f'# TYPE process_num_threads gauge')
        lines.append(f'process_num_threads{{service="{self.service_name}",instance="{self.instance_name}"}} {process["num_threads"]}')
        
        lines.append(f'# HELP process_num_children Number of child processes')
        lines.append(f'# TYPE process_num_children gauge')
        lines.append(f'process_num_children{{service="{self.service_name}",instance="{self.instance_name}"}} {process["num_children"]}')
        
        # System metrics
        system = metrics['system']
        if system:
            lines.append(f'# HELP system_cpu_percent System CPU usage percentage')
            lines.append(f'# TYPE system_cpu_percent gauge')
            lines.append(f'system_cpu_percent{{instance="{self.instance_name}"}} {system["cpu_percent"]}')
            
            lines.append(f'# HELP system_memory_percent System memory usage percentage')
            lines.append(f'# TYPE system_memory_percent gauge')
            lines.append(f'system_memory_percent{{instance="{self.instance_name}"}} {system["memory_percent"]}')
            
            lines.append(f'# HELP system_disk_percent System disk usage percentage')
            lines.append(f'# TYPE system_disk_percent gauge')
            lines.append(f'system_disk_percent{{instance="{self.instance_name}"}} {system["disk_percent"]}')
            
            lines.append(f'# HELP system_load_average_1m System load average (1 minute)')
            lines.append(f'# TYPE system_load_average_1m gauge')
            lines.append(f'system_load_average_1m{{instance="{self.instance_name}"}} {system["load_avg_1m"]}')
        
        return '\n'.join(lines) + '\n'
    
    def push_metrics(self, metrics):
        """Push metrics to Prometheus Pushgateway"""
        try:
            # Format metrics as Prometheus text format
            prometheus_metrics = self.format_prometheus_metrics(metrics)
            
            # Push to Pushgateway
            url = f"{self.pushgateway_url}/metrics/job/systemd_monitoring/instance/{self.instance_name}/service/{self.service_name}"
            
            headers = {
                'Content-Type': 'text/plain; version=0.0.4; charset=utf-8'
            }
            
            response = requests.post(url, data=prometheus_metrics, headers=headers, timeout=30)
            
            if response.status_code == 200:
                logger.debug("Metrics pushed successfully to Pushgateway")
                return True
            else:
                logger.error(f"Failed to push metrics to Pushgateway: {response.status_code} - {response.text}")
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Error pushing metrics to Pushgateway: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error pushing metrics: {e}")
            return False
    
    def collect_and_push_metrics(self):
        """Collect all metrics and push to Pushgateway"""
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
        
        # Push metrics to Pushgateway
        success = self.push_metrics(self.metrics)
        
        if success:
            logger.info(f"Successfully pushed metrics for service {self.service_name} to Pushgateway")
        else:
            logger.warning(f"Failed to push metrics for service {self.service_name} to Pushgateway")
        
        return success

def main():
    parser = argparse.ArgumentParser(description='Push-Based Remote Systemd Service Monitoring Agent')
    parser.add_argument('--service', default='myapp', help='Systemd service name to monitor')
    parser.add_argument('--pushgateway', required=True, help='Prometheus Pushgateway URL (e.g., http://pushgateway:9091)')
    parser.add_argument('--instance', required=True, help='Instance name for this monitoring agent')
    parser.add_argument('--interval', type=int, default=30, help='Metrics collection and push interval in seconds')
    
    args = parser.parse_args()
    
    logger.info(f"Starting push-based monitoring agent for service: {args.service}")
    logger.info(f"Pushgateway URL: {args.pushgateway}")
    logger.info(f"Instance name: {args.instance}")
    logger.info(f"Collection interval: {args.interval} seconds")
    
    # Create collector
    collector = PushMetricsCollector(args.service, args.pushgateway, args.instance)
    
    # Test connection to Pushgateway
    try:
        response = requests.get(f"{args.pushgateway}/-/healthy", timeout=10)
        if response.status_code == 200:
            logger.info("✅ Pushgateway is accessible")
        else:
            logger.warning(f"⚠️ Pushgateway health check returned {response.status_code}")
    except Exception as e:
        logger.error(f"❌ Cannot connect to Pushgateway: {e}")
        logger.error("Please check the Pushgateway URL and network connectivity")
        sys.exit(1)
    
    logger.info("Monitoring agent started successfully")
    
    # Main metrics collection and push loop
    while True:
        try:
            collector.collect_and_push_metrics()
            time.sleep(args.interval)
        except KeyboardInterrupt:
            logger.info("Shutting down monitoring agent...")
            break
        except Exception as e:
            logger.error(f"Error in metrics collection loop: {e}")
            time.sleep(args.interval)

if __name__ == '__main__':
    main()