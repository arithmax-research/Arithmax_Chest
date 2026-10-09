#!/bin/bash

echo "Starting KDB-X Ecosystem Automation..."

# 1. Start the VS Code Data process on port 6003 in the background
echo "Initializing VS Code data node on port 6003 (Background)..."
q -p 6003 > /dev/null 2>&1 &

# Save the background process ID so we can track it
Q_DATA_PID=$!

# Give it 2 seconds to bind to the port cleanly before moving on
sleep 2

# 2. Shift context to dashboards folder and launch the interface
echo "Launching KX Dashboards on port 10001 (Foreground)..."
echo "After booting, open: http://localhost:10001/edit/#dashboard"
echo "--------------------------------------------------------"

# Save your current project folder location
PROJECT_DIR=$(pwd)

# Jump into dashboards folder so dash.q can find go.q_
cd /Users/misango/.kx/dashboards/

# Launch dashboards
q dash.q -p 10001 -u 1 2>/dev/null

# 3. Clean up the background process when you exit the script
echo "Dashboard closed. Stopping background data node (PID: $Q_DATA_PID)..."
kill $Q_DATA_PID

# Jump back to your project directory
cd "$PROJECT_DIR"
echo "Everything stopped cleanly."
