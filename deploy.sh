#!/bin/bash

# Load environment variables from .env file
if [[ -f .env ]]; then
    while IFS='=' read -r key value; do
        if [[ ! -z "$key" && ! $key =~ ^# ]]; then
            export $key="$value"
        fi
    done < <(grep -v '^#' .env)
fi

# Log in to VPS via SSH and execute commands
ssh $VPS_USERNAME@$VPS_IP << EOF

# Change directory to specified path
echo "Changing directory to $VPS_PROJECT_PATH..."
cd $VPS_PROJECT_PATH

# Execute git commands
echo "Executing git checkout..."
git checkout staging
echo "Pulling latest changes from git repository..."
git pull

# Rebuild Docker containers with new changes
echo "Rebuilding Docker containers with new changes..."
docker compose -p $CONTAINER_NAME -f $DOCKER_COMPOSE_FILE up --build -d

# Clean up unused Docker resources without asking for confirmation
echo "Cleaning up unused Docker resources..."
docker system prune -af

EOF


