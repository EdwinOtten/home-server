# Copilot cloud-agent instructions

This repository is a GitOps-managed home server. Doco-CD reads `.doco-cd.yml` and deploys each workload from its own directory:

- `media-server/`: media services and encrypted `.enc.env`
- `monitoring/`: monitoring services
- `tailscale/`: currently disabled; do not enable it unless requested
- `docker-compose.yml`: Doco-CD itself

## Secrets and setup

The `SOPS_AGE_KEY` environment variable is available to the agent, but not to the setup workflow. Before running Docker Compose or any command that needs SOPS, ensure the local key file exists with mode `600`:

```bash
if [[ -f sops_age_key.txt ]]; then
  chmod 600 sops_age_key.txt
elif [[ -n "${SOPS_AGE_KEY:-}" ]]; then
  (umask 077 && printf '%s' "$SOPS_AGE_KEY" > sops_age_key.txt)
else
  echo "Missing SOPS key material" >&2
  exit 1
fi
```

Never print or disclose `SOPS_AGE_KEY`. Verify only that `sops_age_key.txt` exists and has mode `600`.

## Required development workflow

1. Read and follow the local testing and cleanup procedures in `README.md`.
2. Before editing, run the documented local deployment and verify the baseline:
   - `docker logs --since 5m home-server` shows no deployment errors.
   - `docker ps` shows expected containers running.
   - Every container with a healthcheck is `healthy`; containers intended to exit have exit code `0`.
   - There are no unexpected restart loops or fatal container errors.
3. If the baseline has an unexpected failure, collect the relevant container status and logs, report the failure, and stop. Do not modify unrelated infrastructure to work around it.
4. Make the smallest change that implements the request.
5. Use the README cleanup procedure, redeploy from scratch, and repeat the verification checks. Use `docker logs [containerName]` when a deployment or healthcheck fails.
6. Commit changes only after the post-change verification passes. Create a pull request only when requested.
