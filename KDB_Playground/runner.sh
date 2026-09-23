#!/bin/bash

# Configuration
PORT=6003
PID_FILE="./kdb_q.pid"
LOG_FILE="./kdb_q.log"

# Helper function to get real PIDs bound to the port
get_port_pids() {
    # Finds all PIDs (q and VS Code helpers) listening or established on the port
    lsof -t -i :$PORT 2>/dev/null
}

start_q() {
    # Check physical port usage first, then PID file
    PORT_PIDS=$(get_port_pids)
    if [ ! -z "$PORT_PIDS" ]; then
        echo "❌ Port $PORT is already in use by PIDs: $(echo $PORT_PIDS | tr '\n' ' ')"
        echo "💡 Run '$0 stop' first to clear it."
        exit 1
    fi

    echo "🚀 Starting KDB-X engine on port $PORT in the background..."
    
    nohup q -p $PORT > "$LOG_FILE" 2>&1 &
    KDB_PID=$!
    echo $KDB_PID > "$PID_FILE"
    disown $KDB_PID
    
    sleep 1
    if kill -0 $KDB_PID 2>/dev/null; then
        echo "✅ KDB-X started cleanly! (PID: $KDB_PID)"
        echo "📝 Logs: $LOG_FILE"
        echo "💡 Point your VS Code Connection to localhost:$PORT"
    else
        echo "❌ Failed to start. Run 'cat $LOG_FILE' to see why."
        rm -f "$PID_FILE"
    fi
}

stop_q() {
    echo "🛑 Scanning port $PORT for active processes..."
    PORT_PIDS=$(get_port_pids)

    if [ -z "$PORT_PIDS" ] && [ ! -f "$PID_FILE" ]; then
        echo "🟢 Port $PORT is already clean. Nothing to stop."
        return 0
    fi

    # Terminate everything on that port (Matches your manual kill sequence)
    if [ ! -z "$PORT_PIDS" ]; then
        for pid in $PORT_PIDS; do
            echo "Killing process $pid handling port $PORT..."
            kill $pid 2>/dev/null
            sleep 0.5
            # Force kill if it refuses to release the socket
            kill -0 $pid 2>/dev/null && kill -9 $pid 2>/dev/null
        done
    fi

    # Clean up track file
    rm -f "$PID_FILE"
    echo "✅ Port $PORT has been fully cleared and reset."
}

status_q() {
    PORT_PIDS=$(get_port_pids)
    if [ ! -z "$PORT_PIDS" ]; then
        echo "🟢 KDB-X / Port $PORT is ACTIVE"
        echo "Processes tracking on port:"
        lsof -i :$PORT
    else
        echo "🔴 KDB-X / Port $PORT is STOPPED"
    fi
}

case "$1" in
    start)   start_q ;;
    stop)    stop_q ;;
    status)  status_q ;;
    *)       echo "Usage: $0 {start|stop|status}"; exit 1 ;;
esac
