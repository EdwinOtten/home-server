#!/usr/bin/env bash

mkdir /opt/home-server-data
mkdir /opt/configarr-cache
mkdir /opt/sonarr-config

chown -R rogs:rogs /opt/home-server-data
chown -R rogs:rogs /opt/configarr-cache
chown -R rogs:rogs /opt/sonarr-config

#cp ./media-server/config /opt/media-server-config

