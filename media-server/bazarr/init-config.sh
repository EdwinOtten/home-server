#!/bin/bash

CONFIG_DIR="/config/config"
CONFIG_FILE="${CONFIG_DIR}/config.yaml"

update_section() {
  SECTION="$1"
  KEY="$2"
  VALUE="$3"

  # Skip if variable is empty
  [ -z "VALUE" ] && return

  # Create file if missing
  [ ! -f "$CONFIG_FILE" ] && mkdir -p $CONFIG_DIR && touch "$CONFIG_FILE"

  # Create section if missing
  if ! grep -q "^${SECTION}:" "$CONFIG_FILE"; then
    echo -e "\n${SECTION}:\n  ${KEY}: ${VALUE}" >> "$CONFIG_FILE"
    return
  fi

  # If key exists inside section → replace it
  if sed -n "/^${SECTION}:/,/^[^[:space:]]/p" "$CONFIG_FILE" | grep -q "^[[:space:]]*${KEY}:"; then
    sed -i "/^${SECTION}:/,/^[^[:space:]]/ s|^[[:space:]]*${KEY}:.*|  ${KEY}: ${VALUE}|" "$CONFIG_FILE"
  else
    # Insert key-value pair directly after section header
    sed -i "/^${SECTION}:/a\  ${KEY}: ${VALUE}" "$CONFIG_FILE"
  fi
}

update_section "auth"    "apikey" "$BAZARR_API_KEY"
update_section "general" "use_sonarr" "true"
update_section "general" "use_radarr" "true"

update_section "radarr"  "apikey" "$RADARR_API_KEY"
update_section "sonarr"  "apikey" "$SONARR_API_KEY"
update_section "radarr"  "port"   "$RADARR_PORT"
update_section "sonarr"  "port"   "$SONARR_PORT"

chown ${PUID:-1000}:${PGID:-1000} "$CONFIG_FILE"

echo "API keys synchronized."
