# Load Testing Guide for RAG Chatbot

## Overview
This document provides load testing commands and scripts to test the performance and scalability of the RAG Chatbot under various load conditions.

## Prerequisites
Install the required load testing tools:

```bash
# Install Apache Bench (ab)
sudo apt-get install apache2-utils

# Install wrk
sudo apt-get install wrk

# Install Artillery (Node.js required)
npm install -g artillery

# Install Python requests for custom scripts
pip install requests aiohttp asyncio
```

## Test Scenarios

### 1. Basic HTTP Load Test with Apache Bench (ab)

Test the health endpoint:
```bash
# 100 requests, 10 concurrent users
ab -n 100 -c 10 http://localhost:5173/

# 1000 requests, 50 concurrent users
ab -n 1000 -c 50 http://localhost:5173/
```

### 2. WebSocket Load Test with Artillery

Create an Artillery configuration file:

**artillery-config.yml:**
```yaml
config:
  target: 'ws://localhost:5173'
  phases:
    - duration: 30
      arrivalRate: 5
      name: "Warm up"
    - duration: 60
      arrivalRate: 10
      name: "Ramp up load"
    - duration: 150
      arrivalRate: 20
      name: "Sustained load"
  socketio:
    transports: ['websocket']

scenarios:
  - name: "Chat conversation"
    weight: 50
    engine: socketio
    flow:
      - emit:
          channel: "message"
          data:
            message: "What is maternity leave?"
      - think: 2
      - emit:
          channel: "message"
          data:
            message: "List all holidays"
      - think: 3
      - emit:
          channel: "message"
          data:
            message: "What are employee responsibilities?"
      - think: 2
```

Run Artillery test:
```bash
# Run the load test
artillery run artillery-config.yml

# Generate HTML report
artillery run --output report.json artillery-config.yml
artillery report report.json
```

### 3. Custom Python Load Test Script

Create a Python script for more control:

**load_test.py:**
```python
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
```

Run the Python load test:
```bash
python load_test.py
```

### 4. HTTP API Load Test with wrk

```bash
# Basic GET request test
wrk -t12 -c400 -d30s http://localhost:5173/

# POST request test (if you have HTTP endpoints)
wrk -t12 -c400 -d30s -s post.lua http://localhost:5173/api/chat
```

Create a Lua script for POST requests (**post.lua**):
```lua
wrk.method = "POST"
wrk.body   = '{"message": "What is maternity leave?"}'
wrk.headers["Content-Type"] = "application/json"
```

### 5. Comprehensive Load Test Script

**comprehensive_load_test.sh:**
```bash
#!/bin/bash

echo "=== RAG Chatbot Load Testing ==="
echo "Starting comprehensive load test..."

# Check if server is running
curl -f http://localhost:5173/ > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "Error: Chatbot server is not running on localhost:5173"
    exit 1
fi

echo "Server is running. Starting tests..."

# Test 1: Light load
echo "Test 1: Light load (10 users, 60 seconds)"
artillery quick --count 10 --num 60 ws://localhost:5173

# Test 2: Medium load
echo "Test 2: Medium load (50 users, 120 seconds)"
artillery quick --count 50 --num 120 ws://localhost:5173

# Test 3: Heavy load
echo "Test 3: Heavy load (100 users, 300 seconds)"
artillery quick --count 100 --num 300 ws://localhost:5173

# Test 4: Stress test
echo "Test 4: Stress test (200 users, 180 seconds)"
artillery quick --count 200 --num 180 ws://localhost:5173

echo "Load testing completed!"
```

Make it executable and run:
```bash
chmod +x comprehensive_load_test.sh
./comprehensive_load_test.sh
```

### 6. Monitoring Commands

Monitor system resources during load testing:

```bash
# Monitor CPU, memory, and disk usage
htop

# Monitor network connections
netstat -an | grep :5173

# Monitor Python processes
ps aux | grep python

# Monitor logs in real-time
tail -f run.log

# Monitor system resources with iostat
iostat -x 1

# Check memory usage
free -h

# Monitor disk I/O
iotop
```

### 7. Performance Metrics to Monitor

During load testing, monitor these key metrics:

- **Response Time**: Time taken for each chat response
- **Throughput**: Messages processed per second
- **CPU Usage**: Server CPU utilization
- **Memory Usage**: RAM consumption
- **Disk I/O**: Vector store read/write operations
- **Error Rate**: Failed requests or timeouts
- **Connection Count**: Active WebSocket connections

### 8. Expected Performance Baselines

Based on your current CPU-based setup:

- **Light Load (1-10 users)**: < 5 seconds response time
- **Medium Load (10-50 users)**: < 10 seconds response time
- **Heavy Load (50+ users)**: May require optimization
- **Memory Usage**: ~2-4GB for basic operation
- **CPU Usage**: Should not exceed 80% sustained

### 9. Optimization Tips

If load tests reveal performance issues:

1. **Scale Azure VM**: Upgrade to larger VM (D16 v4, D32 v4)
2. **Optimize LLM**: Use smaller/faster models
3. **Cache Responses**: Implement response caching
4. **Load Balancing**: Deploy multiple instances
5. **Database Optimization**: Optimize FAISS index
6. **Connection Pooling**: Limit concurrent connections

## Running Load Tests

1. Ensure your chatbot is running:
```bash
python run.py
```

2. Choose your preferred load testing method
3. Monitor system resources during tests
4. Analyze results and optimize as needed

## Notes
- Start with small loads and gradually increase
- Monitor server resources to avoid crashes
- Test during off-peak hours if possible
- Document results for capacity planning
