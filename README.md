# home-server
Home Server deployed by doco-cd.

## .bashrc aliases
```
alias l='ls -lrah --color=auto'
alias d='docker'
alias n='nano'
alias dlogsa="docker logs home-server 2>&1 | jq ."
alias dlogs="docker logs --since 5m home-server 2>&1 | jq ."
```

## Encrypting secrets using SOPS and age
1. [Install Brew](https://brew.sh) if you haven't
1. Install age via (we use HomeBrew because we need age version 1.3.1 or above, which is not yet available in the Ubuntu archive):
   ```bash
   brew install age
   ```
1. [Install sops](https://github.com/getsops/sops/releases)
1. Follow [encryption instructions by doco-cd](https://github.com/kimdre/doco-cd/wiki/Encryption), but add `-pq` to the `keygen` command to generate keys that are Post-Quantum resistant.
1. On dev machines, copy the private age key to specific location in your home directory:
   ```
   mkdir -p $HOME/.config/sops/age && cp sops_age_key.txt $HOME/.config/sops/age/keys.txt
   ```
1. Edit encrypted file by running
   ```
   cd media-server
   sops edit .enc.env
   ```

**Tip:** if you want to rotate a key, or lost (access to) a private age key you likely want to add a new fingerprint/public age key and remove the old one. To do so, get onto a machine that still has a valid private age key, then remove the old fingerprint/public key from `.sops.yml` except the fingerprint of the machine you're currently using. Optionally, add any new fingerprints of age keys you want to start using. Then re-encrypt all files. After that, you can edit the files using `sops edit` and start rotating secrets.
TODO: split the tip above into 2 use cases (rotating keys after breach & adding a new keypair to a key group) 

## Local Testing

### NFS Server Configuration
Workloads such as `media-server` and test stacks such as `nfs-test` mount remote storage using Docker NFS volumes (`driver_opts: type: nfs`). Docker volume NFS drivers rely on real host-level NFS kernel support, meaning the Docker host must be able to mount the shares over NFS.

- **Production default:** NFS server IP `192.168.1.111` is hardcoded as the default in `media-server/docker-compose.yml` and `nfs-test/docker-compose.yml`.
- **Local testing override:** Set the `NFS_SERVER_ADDR` environment variable to point to a test NFS server, container, or VM:
  ```bash
  export NFS_SERVER_ADDR=192.168.1.50 # Replace with your test NFS server IP
  ```
  The test NFS server should export:
  - `:/volume1/media-server-storage`
  - `:/volume1/downloads`

- **Verifying NFS mount:** Use the `nfs-test` stack to verify your test NFS server connection:
  ```bash
  cd nfs-test
  NFS_SERVER_ADDR=<test-nfs-ip> docker compose up
  ```

### Testing doco-cd Locally
You can test doco-cd repository polling and deployment locally without pushing commits to the remote repository.

The root `docker-compose.yml` supports parameterization through environment variables:
- `REPO_URL`: The repository URL or file path. For local testing, use a file-based Git URL such as `file:///repo` (the local directory is mounted to `/repo:ro` in the container). Defaults to `https://github.com/EdwinOtten/home-server.git`.
- `REPO_REF`: Branch or reference to deploy (defaults to `main`).
- `POLL_INTERVAL`: Interval in seconds to poll (defaults to `60`).
- `RUN_ONCE`: When set to `true`, doco-cd completes a single reconciliation run on startup instead of polling continuously. This is ideal for fast iterations during local testing.
- `REPO_DIR`: Local host directory to mount at `/repo:ro` (defaults to `.`).

Example: test a single doco-cd deployment against your local checkout:
```bash
REPO_URL=file:///repo RUN_ONCE=true NFS_SERVER_ADDR=<test-nfs-ip> docker compose up -d
```
Inspect logs:
```bash
docker logs -f home-server
```

### Testing Individual Workloads Directly
To iterate directly on a workload (e.g. `media-server`):
1. Navigate to the workload directory:
   ```bash
   cd media-server
   ```
2. Decrypt secrets:
   ```bash
   sops decrypt .enc.env > .env
   ```
3. Set `NFS_SERVER_ADDR` if not using the production default:
   ```bash
   export NFS_SERVER_ADDR=<test-nfs-ip>
   ```
4. Start the stack:
   ```bash
   docker compose up -d
   ```
5. Check status:
   ```bash
   docker ps
   docker logs <container_name>
   ``` 
