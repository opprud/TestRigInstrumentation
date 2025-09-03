#!/bin/bash
# Start both Python API server and React frontend

echo "🚀 Starting Test Rig Instrumentation System"
echo "============================================="

# Check if we're in the right directory
if [ ! -d "py" ] || [ ! -d "react" ]; then
    echo "❌ Error: Run this script from the TestRigInstrumentation root directory"
    exit 1
fi

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check Python dependencies
echo "🔍 Checking Python environment..."
if ! command_exists python3; then
    echo "❌ Python 3 not found. Please install Python 3.10+"
    exit 1
fi

cd py

# Check if venv exists, if not create it
if [ ! -d ".venv" ]; then
    echo "📦 Creating Python virtual environment..."
    python3 -m venv .venv
fi

# Activate virtual environment
echo "🔧 Activating Python virtual environment..."
source .venv/bin/activate

# Install/upgrade dependencies
echo "📥 Installing Python dependencies..."
pip install -r requirements.txt

# Start Python API server in background
echo "🐍 Starting Python API server (port 8000)..."
python3 api_server.py &
API_PID=$!

# Wait a moment for API to start
sleep 3

# Check if API is running
if curl -s http://localhost:8000/api/health > /dev/null; then
    echo "✅ Python API server started successfully"
else
    echo "⚠️  Python API server may not be fully ready yet"
fi

cd ../react

# Check Node.js dependencies
echo "🔍 Checking React environment..."
if ! command_exists npm; then
    echo "❌ npm not found. Please install Node.js 18+"
    exit 1
fi

# Install React dependencies if needed
if [ ! -d "node_modules" ]; then
    echo "📦 Installing React dependencies..."
    npm install
fi

# Start React development server
echo "⚛️  Starting React frontend (port 3000)..."
npm run dev &
REACT_PID=$!

# Wait for both servers to be ready
echo ""
echo "⏳ Waiting for servers to start..."
sleep 5

echo ""
echo "🎉 System started successfully!"
echo ""
echo "📍 Available endpoints:"
echo "  • React Dashboard: http://localhost:3000"
echo "  • Python API: http://localhost:8000"
echo "  • API Documentation: http://localhost:8000/docs"
echo ""
echo "🔧 To stop the system:"
echo "  • Press Ctrl+C to stop this script"
echo "  • Or manually kill processes: $API_PID (API) and $REACT_PID (React)"
echo ""

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "🛑 Stopping services..."
    kill $API_PID 2>/dev/null
    kill $REACT_PID 2>/dev/null
    echo "✅ Services stopped"
    exit 0
}

# Set trap to cleanup on script exit
trap cleanup INT TERM

# Wait for user to stop
echo "🎯 System running. Press Ctrl+C to stop all services."
wait