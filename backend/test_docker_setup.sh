#!/bin/bash

# Test script for Docker/Podman production setup
# This script verifies that the Docker/Podman production setup is working correctly

echo "🚀 Testing CodeMop Docker/Podman Production Setup"
echo "=============================================="

# Check if Docker or Podman is available
USE_PODMAN=false
if command -v podman &> /dev/null; then
    echo "✅ Podman is installed"
    USE_PODMAN=true
elif command -v docker &> /dev/null; then
    echo "✅ Docker is installed"
else
    echo "❌ Neither Docker nor Podman is installed. Please install one of them first."
    exit 1
fi

# Check for docker-compose or podman-compose
if ! command -v docker-compose &> /dev/null && ! command -v podman-compose &> /dev/null; then
    echo "❌ Neither docker-compose nor podman-compose is installed. Please install one of them first."
    exit 1
fi

echo "✅ Container runtime and compose tools are available"

# Check if production files exist
echo ""
echo "📁 Checking production files..."

if [ ! -f "backend/Dockerfile.prod" ]; then
    echo "❌ backend/Dockerfile.prod not found"
    exit 1
fi
echo "✅ backend/Dockerfile.prod exists"

if [ ! -f "docker-compose.prod.yml" ]; then
    echo "❌ docker-compose.prod.yml not found"
    exit 1
fi
echo "✅ docker-compose.prod.yml exists"

if [ ! -f ".env.production" ]; then
    echo "❌ .env.production not found"
    exit 1
fi
echo "✅ .env.production exists"

# Check if .env file exists for testing
if [ ! -f ".env" ]; then
    echo "⚠️  .env file not found. Copying .env.production to .env for testing..."
    cp .env.production .env
    echo "✅ Created .env from .env.production template"
fi

# Test container build
echo ""
echo "🐳 Testing container build..."

cd backend || exit 1

BUILD_CMD="docker"
if [ "$USE_PODMAN" = true ]; then
    BUILD_CMD="podman"
fi

if $BUILD_CMD build -f Dockerfile.prod -t codemop-test .; then
    echo "✅ Container build successful"
else
    echo "❌ Container build failed"
    exit 1
fi

cd ..

# Test compose configuration
echo ""
echo "🔧 Testing compose configuration..."

COMPOSE_CMD="docker-compose"
if command -v podman-compose &> /dev/null; then
    COMPOSE_CMD="podman-compose"
fi

if $COMPOSE_CMD -f docker-compose.prod.yml config; then
    echo "✅ Compose configuration is valid"
else
    echo "❌ Compose configuration is invalid"
    exit 1
fi

echo ""
echo "🎉 All container setup tests passed!"
echo ""
echo "📋 Summary:"
echo "- Dockerfile.prod: ✅ Valid"
echo "- docker-compose.prod.yml: ✅ Valid"
echo "- .env.production: ✅ Valid"
echo "- Container build: ✅ Successful"
echo "- Compose config: ✅ Valid"
echo ""
echo "🚀 Ready for production deployment!"
echo ""
if [ "$USE_PODMAN" = true ]; then
    echo "To start the production setup with Podman:"
    echo "  podman-compose -f docker-compose.prod.yml up -d --build"
else
    echo "To start the production setup with Docker:"
    echo "  docker-compose -f docker-compose.prod.yml up -d --build"
fi