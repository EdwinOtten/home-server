#!/bin/bash

# Default values
USER_NAME="rogs"
GROUP_NAME="rogs"

# Check for command-line arguments
if [[ ! -z "$1" ]]; then
    USER_NAME="$1"
fi

if [[ ! -z "$2" ]]; then
    GROUP_NAME="$2"
fi

# Example chown commands
chown "$USER_NAME:$GROUP_NAME" /path/to/file1
chown "$USER_NAME:$GROUP_NAME" /path/to/file2

# Additional commands can follow...