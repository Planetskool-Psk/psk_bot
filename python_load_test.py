import asyncio
import socketio
import time
import json
import sys
from datetime import datetime

class ChatbotLoadTest:
    def __init__(self, base_url="http://localhost:5173"):
        self.base_url = base_url
        self.results = []
        
    async def test_socketio_connection(self, user_id):
        """Test SocketIO chat functionality"""
        sio = socketio.AsyncClient()
        user_results = []
        
        try:
            start_connect = time.time()
            await sio.connect(self.base_url)
            connect_time = time.time() - start_connect
            print(f"User {user_id}: Connected in {connect_time:.2f}s")
            
            # Test messages
            messages = [
                "Hello",
                "What is maternity leave?",
                "List all holidays",
                "What are employee responsibilities?",
                "Tell me about leave policy"
            ]
            
            for msg in messages:
                start_time = time.time()
                await sio.emit('message', {'message': msg})
                await asyncio.sleep(1)  # Wait for response
                response_time = time.time() - start_time
                result = {
                    'user_id': user_id,
                    'message': msg,
                    'response_time': response_time,
                    'timestamp': datetime.now().isoformat()
                }
                user_results.append(result)
                print(f"User {user_id}: '{msg}' - Response time: {response_time:.2f}s")
                
                # Small delay between messages
                await asyncio.sleep(2)
                
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

    async def run_load_test(self, num_users=5, test_name="Load Test"):
        """Run load test with multiple concurrent users"""
        print(f"\n=== {test_name} ===")
        print(f"Starting with {num_users} concurrent users")
        print(f"Test started at: {datetime.now()}")
        
        start_time = time.time()
        tasks = []
        
        for i in range(num_users):
            task = asyncio.create_task(self.test_socketio_connection(i))
            tasks.append(task)
            await asyncio.sleep(0.2)  # Stagger connections
            
        # Wait for all tasks to complete
        all_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Process results
        successful_tests = 0
        failed_tests = 0
        total_response_time = 0
        response_times = []
        
        for user_results in all_results:
            if isinstance(user_results, list):
                for result in user_results:
                    if 'response_time' in result:
                        successful_tests += 1
                        total_response_time += result['response_time']
                        response_times.append(result['response_time'])
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
        
        print(f"\n=== {test_name} Results ===")
        print(f"Total test duration: {total_time:.2f}s")
        print(f"Successful requests: {successful_tests}")
        print(f"Failed requests: {failed_tests}")
        print(f"Average response time: {avg_response_time:.2f}s")
        print(f"Min response time: {min_response_time:.2f}s")
        print(f"Max response time: {max_response_time:.2f}s")
        print(f"Success rate: {(successful_tests/(successful_tests+failed_tests)*100):.1f}%" if (successful_tests+failed_tests) > 0 else "0%")
        
        return {
            'test_name': test_name,
            'num_users': num_users,
            'total_time': total_time,
            'successful_tests': successful_tests,
            'failed_tests': failed_tests,
            'avg_response_time': avg_response_time,
            'min_response_time': min_response_time,
            'max_response_time': max_response_time
        }

async def main():
    load_test = ChatbotLoadTest()
    
    # Run progressive load tests
    test_results = []
    
    # Test 1: Light load
    result1 = await load_test.run_load_test(num_users=3, test_name="Light Load Test")
    test_results.append(result1)
    
    print("\nWaiting 10 seconds before next test...")
    await asyncio.sleep(10)
    
    # Test 2: Medium load
    result2 = await load_test.run_load_test(num_users=5, test_name="Medium Load Test")
    test_results.append(result2)
    
    print("\nWaiting 10 seconds before next test...")
    await asyncio.sleep(10)
    
    # Test 3: Heavy load
    result3 = await load_test.run_load_test(num_users=8, test_name="Heavy Load Test")
    test_results.append(result3)
    
    # Summary
    print("\n" + "="*50)
    print("LOAD TESTING SUMMARY")
    print("="*50)
    
    for result in test_results:
        print(f"\n{result['test_name']}:")
        print(f"  Users: {result['num_users']}")
        print(f"  Duration: {result['total_time']:.2f}s")
        print(f"  Success Rate: {(result['successful_tests']/(result['successful_tests']+result['failed_tests'])*100):.1f}%" if (result['successful_tests']+result['failed_tests']) > 0 else "0%")
        print(f"  Avg Response Time: {result['avg_response_time']:.2f}s")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nLoad test interrupted by user")
    except Exception as e:
        print(f"Load test failed: {e}")
