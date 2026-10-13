# home-server

Home Server deployed by doco-cd.

## .bashrc aliases

```bash
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
   ```bash
   mkdir -p $HOME/.config/sops/age && cp sops_age_key.txt $HOME/.config/sops/age/keys.txt
   ```
1. Edit encrypted file by running
   ```bash
   cd media-server
   sops edit .enc.env
   ```

**Tip:** if you want to rotate a key, or lost (access to) a private age key you likely want to add a new fingerprint/public age key and remove the old one. To do so, get onto a machine that still has a valid private age key, then remove the old fingerprint/public key from `.sops.yml` except the fingerprint of the machine you're currently using. Optionally, add any new fingerprints of age keys you want to start using. Then re-encrypt all files. After that, you can edit the files using `sops edit` and start rotating secrets.

TODO: split the tip above into 2 use cases (rotating keys after breach & adding a new keypair to a key group)

## Local Testing

### Quick Start with Containerized NFS

To test locally without pushing to GitHub, you need a real NFS server. Use `nfs-ganesha` in Docker:

1. Start a containerized NFS server
```bash
docker run -d \
  --name local-nfs-server \
  --privileged \
  -p 2049:2049 \
  -p 111:111/udp \
  -v /tmp/nfs-root:/shared-dir \
  -e SHARED_DIRECTORY=/shared-dir \
  itsthenetwork/nfs-server-alpine:latest
```
2. Create the export paths the stack expects
```bash
mkdir -p /tmp/nfs-root/volume1/media-server-storage /tmp/nfs-root/volume1/downloads
```
3. Get the NFS server IP
```bash
export NFS_SERVER_ADDR=$(docker inspect -f '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}' local-nfs-server)
echo "NFS server at: $NFS_SERVER_ADDR"
```
4. Test NFS connectivity
```bash
cd nfs-test
NFS_SERVER_ADDR="$NFS_SERVER_ADDR" docker compose up
# Should complete successfully if the NFS mount works
```

### Testing Individual Workloads

Once NFS is running, test a specific workload:

```bash
cd media-server
sops decrypt .enc.env > .env
export NFS_SERVER_ADDR="<test-nfs-ip>"
docker compose up -d
docker ps  # Check container health
docker logs <container_name>  # View logs
```

### Testing doco-cd Locally (GitOps)

Test doco-cd repository polling against your local checkout without pushing to GitHub:

```bash
# Ensure NFS server is running (see Quick Start above)
export NFS_SERVER_ADDR="<test-nfs-ip>"

# Run doco-cd in one-shot mode pointing to local repo
REPO_URL=file:///repo RUN_ONCE=true docker compose up -d

# Inspect deployment logs
docker logs -f home-server
```

### Cleanup

```bash
# Stop and remove the local NFS server
docker stop local-nfs-server
docker rm local-nfs-server
rm -rf /tmp/nfs-export
```

### Important Notes

- Docker NFS volumes require real NFS support on the host; this is not a workaround or fake implementation.
- The containerized NFS server exports from `/tmp/nfs-export` by default; adjust paths in the `docker run` command if needed.
- Production uses hardcoded NFS address `192.168.1.111`; local testing overrides it via `NFS_SERVER_ADDR`.
- Use `RUN_ONCE=true` during local testing to run doco-cd once instead of continuously polling.
```
