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

## Docker registry authentication

`DOCKER_PAT` is a read-only personal access token supplied to the cloud-agent
environment. Before any Docker command that can fetch an image, authenticate
all registries referenced by the Compose files:

```bash
: "${DOCKER_PAT:?DOCKER_PAT must be set}"
DOCKER_USERNAME="${DOCKER_USERNAME:-EdwinOtten}"
for registry in docker.io ghcr.io lscr.io; do
  printf '%s' "$DOCKER_PAT" |
    docker login "$registry" --username "$DOCKER_USERNAME" --password-stdin
done
```

Use the Docker/GitHub account associated with the token by setting
`DOCKER_USERNAME` when the default is not correct. Never print the token or
pass it as a command-line argument. This login must happen before the
baseline deployment, redeployment, cleanup commands that may pull images, or
any standalone `docker run`/`docker compose` command.

## Required development workflow

1. Read and follow the local testing and cleanup procedures in `README.md`.
   The cloud agent checkout may be shallow, while normal developer checkouts
   usually are not. Before local Doco-CD deployment, if
   `git rev-parse --is-shallow-repository` returns `true`, run
   `git fetch --unshallow` so Doco-CD can resolve the complete local Git
   source.
2. Authenticate Docker registries as described above, then run the documented
   local deployment and verify the baseline:
   - `docker logs --since 5m home-server` shows no deployment errors.
   - `docker ps` shows expected containers running.
   - Every container with a healthcheck is `healthy`; containers intended to exit have exit code `0`.
   - There are no unexpected restart loops or fatal container errors.
3. If the baseline has an unexpected failure, collect the relevant container status and logs, analyse them, then report the failure + suggested next steps and stop. Do not modify unrelated infrastructure to work around it.
4. Make the smallest change that implements the request.
5. Use the README cleanup procedure, redeploy from scratch, and repeat the verification checks. Use `docker logs [containerName]` when a deployment or healthcheck fails.
6. Commit changes only after the post-change verification passes. Create a pull request only when requested.
