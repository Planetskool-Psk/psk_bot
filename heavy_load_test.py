import asyncio
import socketio
import time
import json
import sys
import threading
from datetime import datetime
import psutil
import os

class HeavyChatbotLoadTest:
    def __init__(self, base_url="http://localhost:5173"):
        self.base_url = base_url
        self.results = []
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
            print(f"CPU: {cpu_percent}% | Memory: {memory.percent}% | Available: {memory.available // (1024**3)}GB")
            time.sleep(2)
    
    async def test_socketio_connection(self, user_id):
        """Test SocketIO chat functionality with more intensive messaging"""
        sio = socketio.AsyncClient()
        user_results = []
        
        try:
            start_connect = time.time()
            await sio.connect(self.base_url)
            connect_time = time.time() - start_connect
            print(f"User {user_id}: Connected in {connect_time:.2f}s")
            
            # Track response data
            response_complete = asyncio.Event()
            full_response = ""
            
            @sio.on('stream_response')
            def on_stream_response(data):
                nonlocal full_response
                if 'token' in data:
                    full_response += data['token']
            
            @sio.on('stream_end')
            def on_stream_end():
                response_complete.set()
            
            # MAXIMUM RESOURCE UTILIZATION - Ultra-intensive 15,000+ word requests
            messages = [
                "What are the key HR policies and procedures outlined in this document? Please provide a comprehensive overview including employee responsibilities, leave policies, and benefits.",
                "Can you explain the maternity leave policy in detail, including eligibility requirements, duration, benefits, and the application process?",
                "What are the different types of leave available to employees and what are the procedures for applying for each type?",
                "What is the notice period policy for resignation and what are the exit procedures that need to be followed?"
            ]
            
            for i, msg in enumerate(messages):
                start_time = time.time()
                full_response = ""  # Reset for each message
                response_complete.clear()  # Reset event
                
                await sio.emit('chat_message', {'message': msg})
                
                # Wait for response to complete (with longer timeout for intensive requests)
                try:
                    await asyncio.wait_for(response_complete.wait(), timeout=180)  # 3 minute timeout for ultra-intensive requests
                    response_time = time.time() - start_time
                    
                    result = {
                        'user_id': user_id,
                        'message_num': i + 1,
                        'message': msg[:50] + "..." if len(msg) > 50 else msg,
                        'response_time': response_time,
                        'response_length': len(full_response),
                        'timestamp': datetime.now().isoformat()
                    }
                    user_results.append(result)
                    print(f"User {user_id} Msg {i+1}: Response time: {response_time:.2f}s, Length: {len(full_response)} chars")
                    
                except asyncio.TimeoutError:
                    response_time = time.time() - start_time
                    result = {
                        'user_id': user_id,
                        'message_num': i + 1,
                        'message': msg[:50] + "..." if len(msg) > 50 else msg,
                        'response_time': response_time,
                        'response_length': len(full_response),
                        'timeout': True,
                        'timestamp': datetime.now().isoformat()
                    }
                    user_results.append(result)
                    print(f"User {user_id} Msg {i+1}: TIMEOUT after {response_time:.2f}s, Length: {len(full_response)} chars")
                
                # NO DELAY between messages - keep maximum load constantly
                # await asyncio.sleep(0.5)
                
        except Exception as e:
            print(f"User {user_id} error: {e}")
            user_results.append({
                'user_id': user_id,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            })
        finally:
            try:
                await sio.disconnect()
            except:
                pass
            
        return user_results

    async def run_heavy_load_test(self, num_users=5, test_name="Heavy Load Test"):
        """Run intensive load test with many concurrent users"""
        print(f"\n=== {test_name} ===")
        print(f"Starting HEAVY LOAD with {num_users} concurrent users")
        print(f"Each user will send 10 requests for detailed 10,000-word responses")
        print(f"Test started at: {datetime.now()}")
        
        # Start system monitoring in a separate thread
        monitor_thread = threading.Thread(target=self.monitor_system_resources)
        monitor_thread.daemon = True
        monitor_thread.start()
        
        start_time = time.time()
        tasks = []
        
        # Create all users SIMULTANEOUSLY for maximum concurrent load
        for i in range(num_users):
            task = asyncio.create_task(self.test_socketio_connection(i))
            tasks.append(task)
            # NO DELAY - all users start at exactly the same time
            
        print(f"All {num_users} users created, waiting for completion...")
        
        # Wait for all tasks to complete
        all_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Stop monitoring
        self.monitoring = False
        
        # Process results
        successful_tests = 0
        failed_tests = 0
        timeout_tests = 0
        total_response_time = 0
        response_times = []
        response_lengths = []
        
        for user_results in all_results:
            if isinstance(user_results, list):
                for result in user_results:
                    if 'response_time' in result:
                        if result.get('timeout', False):
                            timeout_tests += 1
                        else:
                            successful_tests += 1
                        total_response_time += result['response_time']
                        response_times.append(result['response_time'])
                        if 'response_length' in result:
                            response_lengths.append(result['response_length'])
                    elif 'error' in result:
                        failed_tests += 1
            else:
                failed_tests += 1
        
        # Calculate statistics
        if response_times:
            avg_response_time = sum(response_times) / len(response_times)
            min_response_time = min(response_times)
            max_response_time = max(response_times)
        else:
            avg_response_time = min_response_time = max_response_time = 0
            
        if response_lengths:
            avg_response_length = sum(response_lengths) / len(response_lengths)
            min_response_length = min(response_lengths)
            max_response_length = max(response_lengths)
        else:
            avg_response_length = min_response_length = max_response_length = 0
        
        # System resource statistics
        max_cpu = max(self.cpu_usage) if self.cpu_usage else 0
        avg_cpu = sum(self.cpu_usage) / len(self.cpu_usage) if self.cpu_usage else 0
        max_memory = max(self.memory_usage) if self.memory_usage else 0
        
        print(f"\n=== {test_name} Results ===")
        print(f"Total test duration: {total_time:.2f}s")
        print(f"Concurrent users: {num_users}")
        print(f"Total messages sent: {num_users * 5}")
        print(f"Successful requests: {successful_tests}")
        print(f"Timeout requests: {timeout_tests}")
        print(f"Failed requests: {failed_tests}")
        print(f"Average response time: {avg_response_time:.2f}s")
        print(f"Min response time: {min_response_time:.2f}s")
        print(f"Max response time: {max_response_time:.2f}s")
        print(f"Success rate: {(successful_tests/(successful_tests+failed_tests+timeout_tests)*100):.1f}%" if (successful_tests+failed_tests+timeout_tests) > 0 else "0%")
        print(f"Average response length: {avg_response_length:.0f} characters")
        print(f"Min response length: {min_response_length:.0f} characters")
        print(f"Max response length: {max_response_length:.0f} characters")
        print(f"\n=== System Resource Usage ===")
        print(f"Peak CPU usage: {max_cpu:.1f}%")
        print(f"Average CPU usage: {avg_cpu:.1f}%")
        print(f"Peak Memory usage: {max_memory:.1f}%")
        
        return {
            'test_name': test_name,
            'num_users': num_users,
            'total_time': total_time,
            'successful_tests': successful_tests,
            'failed_tests': failed_tests,
            'avg_response_time': avg_response_time,
            'min_response_time': min_response_time,
            'max_response_time': max_response_time,
            'peak_cpu': max_cpu,
            'avg_cpu': avg_cpu,
            'peak_memory': max_memory
        }

async def main():
    load_test = HeavyChatbotLoadTest()
    
    print("🔥 MAXIMUM RESOURCE UTILIZATION TESTING 🔥")
    print("This will push the system to use ALL available resources!")
    print("Multiple concurrent users requesting 15,000-word responses!")
    print("ALL USERS STARTING SIMULTANEOUSLY for MAXIMUM LOAD!")
    print("Monitoring CPU and memory usage during maximum load...")
    
    # Single maximum resource utilization test with 5 concurrent users
    test_results = []
    result = await load_test.run_heavy_load_test(num_users=5, test_name="15K Words - 5 Users MAXIMUM CONCURRENCY")
    test_results.append(result)
    print("\n" + "="*60)
    print("🔥 MAXIMUM RESOURCE UTILIZATION FINAL SUMMARY 🔥")
    print("="*60)
    for result in test_results:
        print(f"\n{result['test_name']}:")
        print(f"  👥 Concurrent Users: {result['num_users']}")
        print(f"  ⏱️  Duration: {result['total_time']:.2f}s")
        print(f"  ✅ Success Rate: {(result['successful_tests']/(result['successful_tests']+result['failed_tests']+1e-9)*100):.1f}%" if (result['successful_tests']+result['failed_tests']) > 0 else "0%")
        print(f"  🚀 Avg Response Time: {result['avg_response_time']:.2f}s")
        print(f"  🔥 Peak CPU: {result['peak_cpu']:.1f}%")
        print(f"  📊 Avg CPU: {result['avg_cpu']:.1f}%")
        print(f"  💾 Peak Memory: {result['peak_memory']:.1f}%")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Heavy load test interrupted by user")
    except Exception as e:
        print(f"❌ Heavy load test failed: {e}")
