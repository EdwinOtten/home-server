#!/bin/bash

# Define the config path
CONFIG_FILE="/config/config.yaml"

# Check if the BAZARR_API_KEY environment variable is provided
if [ -n "$BAZARR_API_KEY" ]; then
    echo "Updating Bazarr API key in config.yaml..."

    # Create the config file if it doesn't exist
    if [ ! -f "$CONFIG_FILE" ]; then
        echo "auth:" > "$CONFIG_FILE"
        echo "  apikey: $BAZARR_API_KEY" >> "$CONFIG_FILE"
    else
        # Ensure the 'auth:' header exists in the file
        if ! grep -q "^auth:" "$CONFIG_FILE"; then
            echo "auth:" >> "$CONFIG_FILE"
        fi

        # Check if 'apikey:' already exists under 'auth:'
        if grep -q "  apikey:" "$CONFIG_FILE"; then
            # Update existing key using sed
            sed -i "s/  apikey:.*/  apikey: $BAZARR_API_KEY/" "$CONFIG_FILE"
        else
            # Append apikey under the auth: line
            sed -i "/^auth:/a \  apikey: $BAZARR_API_KEY" "$CONFIG_FILE"
        fi
    fi
    
    # Optional: Fix permissions to match LinuxServer PUID/PGID
    chown ${PUID:-1000}:${PGID:-1000} "$CONFIG_FILE"
    echo "API key successfully synchronized."
else
    echo "BAZARR_API_KEY not set, skipping configuration."
fi
