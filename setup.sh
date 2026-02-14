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

# create config directories
mkdir /opt/home-server-data
mkdir /opt/configarr-cache
mkdir /opt/sonarr-config

# set owner on config directories
chown -R "$USER_NAME:$GROUP_NAME" /opt/home-server-data
chown -R "$USER_NAME:$GROUP_NAME" /opt/configarr-cache
chown -R "$USER_NAME:$GROUP_NAME" /opt/sonarr-cache


# Additional commands can follow...
#cp ./media-server/config /opt/media-server-config