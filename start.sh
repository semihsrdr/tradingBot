#!/bin/bash

# --- Log Management ---
# Create logs directory if it doesn't exist
mkdir -p logs

# Define a log file with the current date, e.g., logs/scalping-2025-11-11.log
LOG_FILE="logs/scalping-$(date +%Y-%m-%d).log"

# Clean up log files older than 5 days
# -mtime +4 means "modified more than 4*24 hours ago"
echo "Cleaning up logs older than 5 days..."
find logs -type f -name "scalping-*.log" -mtime +4 -delete

echo "Logging all output to: $LOG_FILE"
# --- End Log Management ---


# This script runs both the web server and the worker.
# It's designed to be used as the start command in Coolify
# and also works for local development.

# Define a function to be called on script exit
cleanup() {
    echo "Termination signal received. Shutting down all child processes..."
    # A SIGTERM is sent to all processes in the process group.
    kill 0
    echo "Shutdown complete."
}

# Set the trap: when the script receives SIGINT (Ctrl+C) or SIGTERM, run the cleanup function
trap cleanup SIGINT SIGTERM

# Start Gunicorn in the background.
# Output is piped through a while-read loop to prepend a timestamp to each line.
echo "Starting Gunicorn web server in the background..."
gunicorn app:app --bind 0.0.0.0:${PORT:-3000} 2>&1 | while IFS= read -r line; do echo "[$(date '+%Y-%m-%d %H:%M:%S')] $line"; done >> "$LOG_FILE" &

# Start the worker process in the background
# Output is piped through a while-read loop to prepend a timestamp to each line.
echo "Starting worker process in the background..."
python3 -u worker.py 2>&1 | while IFS= read -r line; do echo "[$(date '+%Y-%m-%d %H:%M:%S')] $line"; done >> "$LOG_FILE" &

# Start the strategist process in the background
# Output is piped through a while-read loop to prepend a timestamp to each line.
echo "Starting strategist process in the background..."
python3 -u strategist.py 2>&1 | while IFS= read -r line; do echo "[$(date '+%Y-%m-%d %H:%M:%S')] $line"; done >> "$LOG_FILE" &

# Wait for all background jobs to complete.
# The script will pause here. When it receives a signal (like from Coolify's
# stop button or a new deployment), the trap will fire, killing all
# child processes, which will cause wait to return and the script to exit.
echo "Application is running. Stop with Ctrl+C (local) or via the Coolify UI (deployment)."
echo "You can monitor the logs in real-time with: tail -f $LOG_FILE"
wait
