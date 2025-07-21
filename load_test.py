import asyncio
import aiohttp
import socketio
import time
import json
from concurrent.futures import ThreadPoolExecutor

class ChatbotLoadTest:
    def __init__(self, base_url="http://localhost:5173"):
        self.base_url = base_url
        self.ws_url = base_url.replace('http', 'ws')
        
    async def test_socketio_connection(self, user_id):
        """Test SocketIO chat functionality"""
        sio = socketio.AsyncClient()
        
        try:
            await sio.connect(self.base_url)
            
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
                await asyncio.sleep(2)  # Wait for response
                response_time = time.time() - start_time
                print(f"User {user_id}: Message '{msg}' - Response time: {response_time:.2f}s")
                
        except Exception as e:
            print(f"User {user_id} error: {e}")
        finally:
            await sio.disconnect()

    async def run_load_test(self, num_users=10, duration=60):
        """Run load test with multiple concurrent users"""
        print(f"Starting load test with {num_users} users for {duration} seconds")
        
        tasks = []
        for i in range(num_users):
            task = asyncio.create_task(self.test_socketio_connection(i))
            tasks.append(task)
            await asyncio.sleep(0.1)  # Stagger connections
            
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    load_test = ChatbotLoadTest()
    asyncio.run(load_test.run_load_test(num_users=20, duration=120))