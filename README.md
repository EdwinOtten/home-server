# home-server

Home Server deployed using the GitOps tool Doco-CD. Useful links:
- [Doco-CD documentation](https://doco.cd/latest/)
- [Doco-CD github repo](https://github.com/kimdre/doco-cd)


## Prerequisites
Before you can start developing, you need to have the following tools installed:

1. [Install Brew](https://brew.sh) if you haven't:
   ```bash
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   ```
   and don't forget to execute the post-installation instructions printed in your terminal.
2. Install age (we use HomeBrew because we need age version 1.3.1 or above, which is not yet available in the Ubuntu archive):
   ```bash
   brew install age
   ```
3. [Install sops](https://github.com/getsops/sops/releases)
4. Install docker if you haven't

### Docker registry authentication

If Docker Hub asks for authentication, human users can log in with their
Docker Hub username and personal access token before pulling images. The
repository's Copilot instructions contain the non-interactive login procedure
for the cloud-agent environment. Images hosted on GHCR or LSCR use separate
credentials when those registries require authentication.


## Local Testing

### Prerequisite: setup local NFS server

To test locally without pushing to GitHub, you need a real NFS server. Use the `itsthenetwork/nfs-server-alpine` image in Docker:

```bash
# Create the export paths the stack expects
rm -r /tmp/nfs-root/volume1/media-server-storage
mkdir -p /tmp/nfs-root/volume1/media-server-storage

# Remove NFS server if already running
docker ps -a | grep nfs-server && docker stop nfs-server && docker rm nfs-server

# Start NFS server
docker run -d \
--name nfs-server \
--privileged \
-p 2049:2049 \
-p 111:111/udp \
-v /tmp/nfs-root:/shared-dir \
-e SHARED_DIRECTORY=/shared-dir \
itsthenetwork/nfs-server-alpine:latest

# Get the NFS server IP
export NFS_SERVER_ADDR=$(docker inspect -f '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}' nfs-server)
echo "NFS server at: $NFS_SERVER_ADDR"
```

You can test NFS connectivity by running the command below(should complete successfully if the NFS mount works)
```bash
NFS_SERVER_ADDR="$NFS_SERVER_ADDR" docker compose -f nfs-test/docker-compose.yml up
```

### Deploying locally (via GitOps)

Once NFS is running, you can test the deployment your changes without pushing to GitHub by running:

```bash
# Create temporary location for local deployment
rm -rf /tmp/home-server-data
mkdir -p /tmp/home-server-data

# Ensure NFS server is running (see Quick Start above)
export NFS_SERVER_ADDR=$(docker inspect -f '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}' nfs-server)

# Run doco-cd in one-shot mode pointing to local repo
REPO_DIR=$PWD REPO_REF=$(git branch --show-current) NFS_SERVER_ADDR="$NFS_SERVER_ADDR" LOCAL_VOLUME_LOCATION=/tmp/home-server-data RUN_ONCE=true docker compose up -d
```


### Cleanup

After testing, and between testing multiple changes, use the commands below to cleanup 
```bash
# Stop and remove all media-server containers and its network
REPO_DIR=$PWD REPO_REF=$(git branch --show-current) NFS_SERVER_ADDR="$NFS_SERVER_ADDR" LOCAL_VOLUME_LOCATION=/tmp/home-server-data RUN_ONCE=true docker compose down
LOCAL_VOLUME_LOCATION=/tmp/home-server-data docker compose -f media-server/docker-compose.yml down
sudo rm -rf /tmp/home-server-data
```

To cleanup the NFS server as well:
```bash
# Stop and remove the local NFS server
docker stop nfs-server
docker rm nfs-server
rm -r /tmp/nfs-root/volume1/media-server-storage
```


## Encrypting secrets using SOPS and age
1. Follow [encryption instructions by doco-cd](https://github.com/kimdre/doco-cd/wiki/Encryption), but add `-pq` to the `keygen` command to generate keys that are Post-Quantum resistant.
2. On dev machines, copy the private age key to specific location in your home directory:
   ```bash
   mkdir -p $HOME/.config/sops/age && cp sops_age_key.txt $HOME/.config/sops/age/keys.txt
   ```
3. Edit encrypted file by running
   ```bash
   sops edit media-server/.enc.env
   ```

### Copilot cloud agent key source

For GitHub Copilot cloud agent tasks, configure a repository Agent secret named `SOPS_AGE_KEY`.  
The agent creates the local `sops_age_key.txt` file from that secret before running Docker Compose; the setup workflow does not receive the secret.

**Tip:** if you want to rotate a key, or lost (access to) a private age key you likely want to add a new fingerprint/public age key and remove the old one. To do so, get onto a machine that still has a valid private age key, then remove the old fingerprint/public key from `.sops.yml` except the fingerprint of the machine you're currently using. Optionally, add any new fingerprints of age keys you want to start using. Then re-encrypt all files. After that, you can edit the files using `sops edit` and start rotating secrets.

TODO: split the tip above into 2 use cases (rotating keys after breach & adding a new keypair to a key group)


## .bashrc aliases

```bash
alias l='ls -lrah --color=auto'
alias d='docker'
alias n='nano'
alias dlogsa="docker logs home-server 2>&1 | jq ."
alias dlogs="docker logs --since 5m home-server 2>&1 | jq ."
```
