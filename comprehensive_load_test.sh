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
echo "Test 1: Light load (5 users, 30 seconds)"
artillery quick --count 5 --num 30 ws://localhost:5173

sleep 10

# Test 2: Medium load
echo "Test 2: Medium load (10 users, 60 seconds)"
artillery quick --count 10 --num 60 ws://localhost:5173

sleep 10

# Test 3: Heavy load
echo "Test 3: Heavy load (20 users, 120 seconds)"
artillery quick --count 20 --num 120 ws://localhost:5173

echo "Load testing completed!"
