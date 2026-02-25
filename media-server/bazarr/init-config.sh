#!/bin/bash

CONFIG_FILE="/config/config/config.yaml"

update_section() {
  SECTION="$1"
  API_KEY="$2"

  # Skip if variable is empty
  [ -z "$API_KEY" ] && return

  # Create file if missing
  [ ! -f "$CONFIG_FILE" ] && touch "$CONFIG_FILE"

  # Create section if missing
  if ! grep -q "^${SECTION}:" "$CONFIG_FILE"; then
    echo -e "\n${SECTION}:\n  apikey: ${API_KEY}" >> "$CONFIG_FILE"
    return
  fi

  # If apikey exists inside section → replace it
  if sed -n "/^${SECTION}:/,/^[^[:space:]]/p" "$CONFIG_FILE" | grep -q "^[[:space:]]*apikey:"; then
    sed -i "/^${SECTION}:/,/^[^[:space:]]/ s|^[[:space:]]*apikey:.*|  apikey: ${API_KEY}|" "$CONFIG_FILE"
  else
    # Insert apikey directly after section header
    sed -i "/^${SECTION}:/a\  apikey: ${API_KEY}" "$CONFIG_FILE"
  fi
}

update_section "auth"   "$BAZARR_API_KEY"
update_section "radarr" "$RADARR_API_KEY"
update_section "sonarr" "$SONARR_API_KEY"

chown ${PUID:-1000}:${PGID:-1000} "$CONFIG_FILE"

echo "API keys synchronized."
