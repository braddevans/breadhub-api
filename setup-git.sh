#!/bin/bash

# Create .gitignore_global
echo "*~" > /root/.gitignore_global
echo ".DS_Store" >> /root/.gitignore_global

# Copy Git config
if [ -f "/app/.gitconfig" ]; then
    cp /app/.gitconfig /root/.gitconfig
fi

# Set up Git credentials if they exist
if [ -f "/app/.git-credentials" ]; then
    cp /app/.git-credentials /root/.git-credentials
    chmod 600 /root/.git-credentials
    git config --global credential.helper "store --file=/root/.git-credentials"
    echo "Git credentials configured"
else
    echo "Warning: .git-credentials not found. Git operations requiring authentication may fail."
fi
