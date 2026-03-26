# ADR 0001: Prefer API-based Configuration Over Config File Injection

## Status

Accepted

## Context

When deploying containerized services, there are typically two ways to apply configuration:

1. **Config file injection** – mounting or writing a configuration file into the container's volume, which the application reads on startup.
2. **API-based configuration** – using the service's HTTP/REST API (or equivalent) to apply settings after the container is running.

Config files are primarily an internal concern of the application. They are typically part of the container image's implementation detail and may change structure, key names, or format between image versions without notice. When we inject or overwrite these files, we couple ourselves to the application's internal file format, making upgrades riskier and harder to maintain.

APIs, on the other hand, are explicitly versioned contracts that the container image authors are far less likely to break between releases. They are designed for external consumers and offer a stable interface for configuration.

A real-world example of this tension exists with **Bazarr**: there is no documented environment-variable interface for all settings, so the current approach is to inject values directly into its `config.yaml` via a shell script (`bazarr/init-config.sh`). This works but is fragile.

## Decision

**Prefer configuring containers via their API** rather than injecting or modifying config files in the container's volume.

When an API is available, use it as the primary method to configure a service. Reserve config file injection only for cases where the API is not yet available at startup time (i.e., bootstrapping), such as setting an initial API key or enabling a feature that must be present before the API becomes reachable.

When config file injection cannot be avoided entirely:
- Inject only the **bare minimum** required (e.g., the API key so subsequent API calls can be authenticated).
- Use the API for everything else once the service is running.

## Consequences

**Positive:**
- Configuration is decoupled from the internal file format of each container image, reducing the risk of breakage on image upgrades.
- API-based configuration is self-documenting through the API schema/docs provided by the service.
- It becomes clearer which settings are "bootstrap" (injected once) versus "managed" (applied via API and potentially tracked as code).

**Negative / Trade-offs:**
- API configuration may require an additional init step (e.g., a sidecar container, an init script, or a startup hook) to apply settings after the service is healthy.
- For services that have no API (or a very limited one), config file injection remains the only option and must be maintained carefully.

## Examples in This Repository

| Service   | Bootstrap via config/env | Further config via API |
|-----------|--------------------------|------------------------|
| Sonarr    | API key via env var (`SONARR__AUTH__APIKEY`) | All other settings (indexers, quality profiles, etc.) via Sonarr API |
| Radarr    | API key via env var (`RADARR__AUTH__APIKEY`) | All other settings via Radarr API |
| Prowlarr  | API key via env var (`PROWLARR__AUTH__APIKEY`) | All other settings via Prowlarr API |
| Bazarr    | API key + minimal bootstrap via `init-config.sh` (no full API for bootstrap) | Remaining settings should be applied via Bazarr API where possible |
