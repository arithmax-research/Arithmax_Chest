#!/bin/bash

# Configuration (KDB-X handles standard positive ports safely)
PORT=6003
PID_FILE="./kdb_q.pid"
LOG_FILE="./kdb_q.log"

start_q() {
    # Check if already running
    if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
        echo "❌ KDB-X is already running on port $PORT. (PID: $(cat "$PID_FILE"))"
        exit 1
    fi

    echo "🚀 Starting KDB-X engine on port $PORT in the background..."
    
    # Start q with a standard positive port, redirect log, and run as background daemon
    nohup q -p $PORT > "$LOG_FILE" 2>&1 &
    
    # Capture the process ID
    KDB_PID=$!
    echo $KDB_PID > "$PID_FILE"
    
    # Free up the terminal shell completely
    disown $KDB_PID
    
    sleep 1
    if kill -0 $KDB_PID 2>/dev/null; then
        echo "✅ KDB-X started cleanly! (PID: $KDB_PID)"
        echo "📝 Logs: $LOG_FILE"
        echo "💡 Terminal is free. Point your VS Code Connection to localhost:$PORT"
    else
        echo "❌ Failed to start. Run 'cat $LOG_FILE' to see why."
        rm -f "$PID_FILE"
    fi
}

stop_q() {
    if [ ! -f "$PID_FILE" ]; then
        echo "⚠️ No active PID file tracker found."
        exit 1
    fi

    PID=$(cat "$PID_FILE")
    if kill -0 $PID 2>/dev/null; then
        echo "🛑 Terminating KDB-X instance (PID: $PID)..."
        kill $PID
        rm -f "$PID_FILE"
        echo "✅ Engine shut down completely."
    else
        echo "⚠️ Stale tracking profile found. Cleaning up."
        rm -f "$PID_FILE"
    fi
}

status_q() {
    if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
        echo "🟢 KDB-X is RUNNING (PID: $(cat "$PID_FILE")) on port $PORT"
    else
        echo "🔴 KDB-X is STOPPED"
    fi
}

case "$1" in
    start)   start_q ;;
    stop)    stop_q ;;
    status)  status_q ;;
    *)       echo "Usage: $0 {start|stop|status}"; exit 1 ;;
esac
