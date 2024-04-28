#!/bin/bash

# Load environment variables from .env file
if [[ -f .env ]]; then
    echo "Loading environment variables from .env file..."
    export $(grep -v '^#' .env | xargs)
fi

# Log in to VPS via SSH
echo "Logging in to VPS via SSH... $VPS_USERNAME@$VPS_IP"
ssh $VPS_USERNAME@$VPS_IP

# Change directory to specified path
echo "Changing directory to $VPS_PROJECT_PATH..."
cd $VPS_PROJECT_PATH

# Execute git commands
echo "Executing git checkout..."
git checkout staging
echo "Pulling latest changes from git repository..."
git pull

# Rebuild Docker containers with new changes
echo "Rebuilding Docker containers ($CONTAINER_NAME) with new changes... docker compose file: $DOCKER_COMPOSE_FILE"
docker compose -p $CONTAINER_NAME -f $DOCKER_COMPOSE_FILE up --build -d

# Clean up unused Docker resources without asking for confirmation
echo "Cleaning up unused Docker resources..."
docker system prune -af

# Log off from SSH session
echo "Logging off from SSH session..."
exit

