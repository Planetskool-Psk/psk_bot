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
                "Please provide an EXTREMELY COMPREHENSIVE and DETAILED analysis of ALL HR policies, procedures, guidelines, and documentation in the entire document. I need a complete 15,000+ word executive report covering EVERY SINGLE aspect including: policy details, procedures, requirements, benefits, eligibility criteria, implementation guidelines, compliance requirements, legal considerations, process flows, documentation requirements, approval hierarchies, timelines, exceptions, special cases, examples, scenarios, best practices, and complete step-by-step instructions. Include ALL sections, subsections, rules, exceptions, examples, explanations, and cross-references in EXHAUSTIVE detail with comprehensive analysis and commentary.",
                "Generate a COMPLETE and EXHAUSTIVE 15,000+ word comprehensive enterprise-level guide on maternity leave policy covering EVERY possible detail including: eligibility requirements, duration calculations, benefit structures, procedures, documentation requirements, pay structure analysis, job protection mechanisms, return-to-work policies, career impact considerations, legal compliance, international comparisons, edge cases, special circumstances, administrative processes, approval workflows, communication protocols, manager responsibilities, HR procedures, benefits coordination, and ALL related provisions. Provide EXTENSIVE explanations covering ALL possible scenarios, edge cases, and implementation details.",
                "Create an ULTRA-COMPREHENSIVE 15,000+ word enterprise document listing, explaining, and analyzing ALL holidays, leave policies, vacation entitlements, sick leave provisions, personal time off, emergency leave, bereavement policies, sabbatical options, unpaid leave, family leave, military leave, jury duty, religious accommodations, and ALL time-off related benefits. Include DETAILED descriptions, eligibility requirements, approval processes, documentation needs, pay implications, accrual calculations, carry-over policies, blackout periods, coverage requirements, manager approvals, HR procedures, legal compliance, and comprehensive implementation guidelines for EACH type.",
                "Please write an EXTREMELY DETAILED 15,000+ word comprehensive analysis of ALL employee responsibilities, duties, obligations, performance expectations, behavioral guidelines, code of conduct, workplace policies, compliance requirements, professional standards, ethics guidelines, conflict of interest policies, confidentiality requirements, social media policies, dress codes, attendance expectations, communication standards, teamwork requirements, leadership expectations, customer service standards, quality requirements, safety obligations, and environmental responsibilities. Cover EVERY aspect of what is expected from employees with detailed examples, scenarios, and implementation guidance.",
                "Generate a COMPREHENSIVE 15,000+ word executive-level explanation of leave travel allowance policy, vacation benefits, travel reimbursements, allowable expenses, documentation requirements, approval processes, payment schedules, eligibility criteria, geographic restrictions, family provisions, booking procedures, travel insurance, emergency protocols, expense reporting, audit requirements, tax implications, policy violations, and ALL related travel and vacation policies. Include detailed procedures, forms, examples, and comprehensive implementation guidelines.",
                "Provide a COMPLETE 15,000+ word enterprise guide on relocation policies covering benefits, allowances, reimbursements, support services, documentation requirements, timelines, eligibility criteria, geographic considerations, family provisions, temporary housing, permanent housing assistance, moving services, travel expenses, storage costs, utility connections, school assistance, spouse employment support, cultural adaptation, tax implications, policy exceptions, and ALL aspects of employee relocation assistance programs with comprehensive procedures and examples.",
                "Create an EXTENSIVE 15,000+ word document about notice period requirements, resignation procedures, termination policies, exit processes, final settlements, knowledge transfer requirements, documentation handover, asset return procedures, access revocation, benefit continuation, reference policies, non-compete obligations, confidentiality continuation, and ALL employment separation guidelines for different employee levels, situations, and circumstances. Include detailed procedures, timelines, checklists, and comprehensive guidance.",
                "Write a DETAILED 15,000+ word comprehensive analysis of performance evaluation criteria, review processes, goal setting methodologies, feedback mechanisms, rating systems, improvement plans, career development paths, promotion criteria, succession planning, talent management, skill assessment, competency frameworks, 360-degree feedback, peer reviews, self-assessments, and ALL performance management policies and procedures with detailed implementation guidelines and examples.",
                "Generate a COMPREHENSIVE 15,000+ word executive explanation of compensation structure, salary components, benefits packages, incentives, bonuses, allowances, deductions, pay scales, review processes, market analysis, equity considerations, performance linkages, promotion impacts, benefit enrollment, insurance options, retirement planning, stock options, profit sharing, and ALL financial benefits and policies for employees with detailed calculations and examples.",
                "Please provide an EXHAUSTIVE 15,000+ word enterprise guide on training and development opportunities, skill enhancement programs, career advancement paths, educational support, certification assistance, mentoring programs, leadership development, technical training, soft skills development, conference attendance, online learning, tuition reimbursement, sabbatical programs, cross-functional training, and ALL learning and development initiatives available to employees with comprehensive procedures and implementation guidelines."
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

    async def run_heavy_load_test(self, num_users=20, test_name="Heavy Load Test"):
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
        print(f"Total messages sent: {num_users * 10}")
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
    
    # Single maximum resource utilization test with 50 concurrent users
    test_results = []
    result = await load_test.run_heavy_load_test(num_users=50, test_name="15K Words - 50 Users MAXIMUM CONCURRENCY")
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
