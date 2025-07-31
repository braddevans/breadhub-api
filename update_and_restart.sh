#!/bin/bash

# Set the repository directory
REPO_DIR="/app"
# Set the branch to check (e.g., main, master, etc.)
BRANCH="main"
# Set the container name
CONTAINER_NAME="breadhub-api-web-1"

# Log function
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1"
}

# Main function
main() {
    cd "$REPO_DIR" || exit 1
    
    # Fetch the latest changes from the remote
    git fetch origin "$BRANCH"
    
    # Get the current and latest commit hashes
    CURRENT_HASH=$(git rev-parse HEAD)
    LATEST_HASH=$(git rev-parse "origin/$BRANCH")
    
    # Compare the hashes
    if [ "$CURRENT_HASH" != "$LATEST_HASH" ]; then
        log "New changes detected. Updating and restarting..."
        
        # Pull the latest changes
        git pull origin "$BRANCH"
        
        # Install any new dependencies
        pip install -r requirements.txt
        
        # Restart the container
        docker-compose restart $CONTAINER_NAME
        
        log "Update and restart completed."
    else
        log "No new changes detected."
    fi
}

# Run the main function and log to a file
main >> /var/log/update_script.log 2>&1
