#!/usr/bin/env python3
"""
System monitoring script for the optimized chatbot
Run this in a separate terminal to monitor performance
"""

import psutil
import time
import os
from datetime import datetime

def format_bytes(bytes_value):
    """Convert bytes to human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.1f}{unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.1f}TB"

def monitor_system():
    """Monitor system resources in real-time"""
    print("🔍 Real-time System Monitor for Optimized Chatbot")
    print("=" * 60)
    
    try:
        while True:
            # Clear screen (works on most terminals)
            os.system('clear' if os.name == 'posix' else 'cls')
            
            # Current time
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"📊 System Monitor - {now}")
            print("=" * 60)
            
            # CPU information
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_freq = psutil.cpu_freq()
            cpu_count = psutil.cpu_count()
            
            print(f"🔧 CPU: {cpu_percent:.1f}% ({cpu_count} cores)")
            if cpu_freq:
                print(f"   Frequency: {cpu_freq.current:.0f}MHz")
            
            # Memory information
            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()
            
            print(f"💾 RAM: {memory.percent:.1f}% ({format_bytes(memory.used)}/{format_bytes(memory.total)})")
            print(f"   Available: {format_bytes(memory.available)}")
            if swap.total > 0:
                print(f"💿 Swap: {swap.percent:.1f}% ({format_bytes(swap.used)}/{format_bytes(swap.total)})")
            
            # Disk information
            disk = psutil.disk_usage('/')
            print(f"💽 Disk: {disk.percent:.1f}% ({format_bytes(disk.used)}/{format_bytes(disk.total)})")
            
            # Network information
            network = psutil.net_io_counters()
            print(f"🌐 Network: ⬇️ {format_bytes(network.bytes_recv)} ⬆️ {format_bytes(network.bytes_sent)}")
            
            # Process information
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'memory_percent', 'cpu_percent']):
                try:
                    if 'python' in proc.info['name'].lower() or 'ollama' in proc.info['name'].lower():
                        processes.append(proc.info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            if processes:
                print("\n🐍 Python/Ollama Processes:")
                processes.sort(key=lambda x: x['memory_percent'] or 0, reverse=True)
                for proc in processes[:5]:  # Top 5
                    mem_pct = proc['memory_percent'] or 0
                    cpu_pct = proc['cpu_percent'] or 0
                    print(f"   PID {proc['pid']}: {proc['name'][:20]:<20} "
                          f"CPU: {cpu_pct:.1f}% RAM: {mem_pct:.1f}%")
            
            # Performance recommendations
            print("\n💡 Performance Status:")
            if memory.percent > 85:
                print("   ⚠️  HIGH MEMORY USAGE - Consider restarting")
            elif memory.percent > 70:
                print("   ⚡ Moderate memory usage - Monitor closely")
            else:
                print("   ✅ Memory usage is optimal")
                
            if cpu_percent > 80:
                print("   ⚠️  HIGH CPU USAGE - System may be slow")
            elif cpu_percent > 50:
                print("   ⚡ Moderate CPU usage - Good performance")
            else:
                print("   ✅ CPU usage is optimal")
            
            print("\nPress Ctrl+C to stop monitoring...")
            time.sleep(5)
            
    except KeyboardInterrupt:
        print("\n\n👋 Monitoring stopped.")

if __name__ == "__main__":
    monitor_system()
