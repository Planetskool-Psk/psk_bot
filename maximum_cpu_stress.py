#!/usr/bin/env python3
import asyncio
import socketio
import time
import threading
import psutil
from datetime import datetime

class MaximumCPUStressTest:
    def __init__(self, base_url="http://localhost:5173"):
        self.base_url = base_url
        self.monitoring = True
        self.cpu_usage = []
        self.memory_usage = []
        
    def monitor_system_resources(self):
        """Monitor CPU and memory usage during the test"""
        while self.monitoring:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            self.cpu_usage.append(cpu_percent)
            self.memory_usage.append(memory.percent)
            print(f"🔥 CPU: {cpu_percent:5.1f}% | Memory: {memory.percent:4.1f}% | Available: {memory.available // (1024**3)}GB")
            time.sleep(1)  # Faster monitoring
    
    async def stress_user(self, user_id):
        """Single user sending intensive requests continuously"""
        sio = socketio.AsyncClient()
        
        try:
            await sio.connect(self.base_url)
            print(f"🚀 User {user_id}: Connected - Starting intensive requests")
            
            response_complete = asyncio.Event()
            
            @sio.on('stream_response')
            def on_stream_response(data):
                pass  # Don't store response to save memory
            
            @sio.on('stream_end')
            def on_stream_end():
                response_complete.set()
            
            # Ultra-intensive request designed to maximize CPU usage
            intensive_request = """
            Please provide an EXTREMELY COMPREHENSIVE, DETAILED, and EXHAUSTIVE analysis covering EVERY SINGLE aspect of ALL HR policies, procedures, guidelines, benefits, requirements, compliance standards, legal frameworks, implementation processes, approval workflows, documentation requirements, eligibility criteria, calculation methods, exception handling, appeals processes, audit procedures, reporting mechanisms, training requirements, communication protocols, manager responsibilities, employee obligations, organizational hierarchy impacts, cross-departmental coordination, system integrations, data management, record keeping, privacy considerations, security protocols, performance metrics, quality assurance, continuous improvement processes, stakeholder management, vendor relationships, cost analysis, budget implications, resource allocation, timeline management, risk assessment, mitigation strategies, change management, transition planning, rollback procedures, disaster recovery, business continuity, compliance monitoring, regulatory reporting, internal controls, external audits, best practices, industry benchmarks, competitive analysis, market research, trend analysis, forecasting, strategic planning, tactical implementation, operational excellence, process optimization, efficiency improvements, automation opportunities, technology integration, digital transformation, user experience enhancement, accessibility compliance, multilingual support, cultural considerations, diversity initiatives, inclusion programs, equity measures, sustainability practices, environmental impact, social responsibility, corporate governance, ethical standards, and comprehensive future-state visioning with detailed implementation roadmaps covering ALL aspects in MAXIMUM detail.
            """
            
            # Keep sending requests continuously for maximum CPU load
            for i in range(5):  # 5 intensive requests per user
                response_complete.clear()
                start_time = time.time()
                
                await sio.emit('chat_message', {'message': intensive_request})
                
                try:
                    await asyncio.wait_for(response_complete.wait(), timeout=90)
                    response_time = time.time() - start_time
                    print(f"✅ User {user_id} Request {i+1}: Completed in {response_time:.1f}s")
                except asyncio.TimeoutError:
                    response_time = time.time() - start_time
                    print(f"⏰ User {user_id} Request {i+1}: Timeout after {response_time:.1f}s")
                
                # No delay - immediate next request for maximum load
                
        except Exception as e:
            print(f"❌ User {user_id} error: {e}")
        finally:
            try:
                await sio.disconnect()
            except:
                pass

    async def run_maximum_stress_test(self, num_users=6):
        """Run maximum stress test to push CPU to 100%"""
        print(f"\n🔥🔥🔥 MAXIMUM CPU STRESS TEST 🔥🔥🔥")
        print(f"Starting {num_users} users SIMULTANEOUSLY")
        print(f"All users will send continuous intensive requests")
        print(f"TARGET: Push CPU usage to 100%!")
        print(f"Test started at: {datetime.now()}")
        
        # Start system monitoring
        monitor_thread = threading.Thread(target=self.monitor_system_resources)
        monitor_thread.daemon = True
        monitor_thread.start()
        
        start_time = time.time()
        
        # Create all users simultaneously - NO delays
        tasks = []
        for i in range(num_users):
            task = asyncio.create_task(self.stress_user(i))
            tasks.append(task)
        
        print(f"🚀 All {num_users} users launched simultaneously!")
        
        # Wait for all users to complete
        await asyncio.gather(*tasks, return_exceptions=True)
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Stop monitoring
        self.monitoring = False
        
        # Results
        max_cpu = max(self.cpu_usage) if self.cpu_usage else 0
        avg_cpu = sum(self.cpu_usage) / len(self.cpu_usage) if self.cpu_usage else 0
        max_memory = max(self.memory_usage) if self.memory_usage else 0
        
        print(f"\n🏁 MAXIMUM STRESS TEST RESULTS 🏁")
        print(f"Duration: {total_time:.1f} seconds")
        print(f"Concurrent Users: {num_users}")
        print(f"🔥 PEAK CPU USAGE: {max_cpu:.1f}%")
        print(f"📊 AVERAGE CPU USAGE: {avg_cpu:.1f}%")
        print(f"💾 PEAK MEMORY USAGE: {max_memory:.1f}%")
        
        if max_cpu >= 80:
            print("🎯 SUCCESS: Achieved high CPU utilization!")
        elif max_cpu >= 60:
            print("✅ GOOD: Significant CPU load achieved!")
        else:
            print("📈 MODERATE: Some CPU load achieved, try more users for higher load")

async def main():
    stress_test = MaximumCPUStressTest()
    
    # Test with increasing numbers of users to find the maximum load point
    for num_users in [4, 6, 8]:
        print(f"\n{'='*60}")
        await stress_test.run_maximum_stress_test(num_users=num_users)
        
        if num_users < 8:  # Don't wait after the last test
            print(f"\n⏳ Waiting 30 seconds before next test...")
            await asyncio.sleep(30)
            
            # Reset for next test
            stress_test.cpu_usage = []
            stress_test.memory_usage = []
            stress_test.monitoring = True

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Maximum stress test interrupted")
    except Exception as e:
        print(f"❌ Test failed: {e}")
