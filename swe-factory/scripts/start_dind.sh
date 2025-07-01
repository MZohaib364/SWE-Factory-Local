#!/bin/bash

# SWE-Factory Docker-in-Docker Startup Script

set -e

echo "🚀 Starting SWE-Factory with Docker-in-Docker..."

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker first."
    exit 1
fi

# Build the DinD image
echo "📦 Building Docker-in-Docker image..."
docker-compose -f docker-compose.dind.yml build

# Start the DinD container
echo "🔧 Starting Docker-in-Docker container..."
docker-compose -f docker-compose.dind.yml up -d

# Wait for Docker daemon to be ready
echo "⏳ Waiting for Docker daemon to be ready..."
sleep 10

# Check if the container is running
if docker ps | grep -q swe-factory-dind; then
    echo "✅ SWE-Factory DinD is running!"
    echo "📊 Container status:"
    docker ps | grep swe-factory-dind
    
    echo ""
    echo "🔗 You can now run commands inside the DinD container:"
    echo "   docker exec -it swe-factory-dind bash"
    echo ""
    echo "📁 Your data is mounted at:"
    echo "   - /app/data_collection (data_collection/)"
    echo "   - /app/output (output/)"
    echo "   - /app/evaluation (evaluation/)"
    echo ""
    echo "🛑 To stop: docker-compose -f docker-compose.dind.yml down"
else
    echo "❌ Failed to start SWE-Factory DinD container"
    docker-compose -f docker-compose.dind.yml logs
    exit 1
fi 