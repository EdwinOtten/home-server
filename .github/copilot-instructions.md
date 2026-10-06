This home server project is based on Docker Compose files.

In production, doco-cd is used to deploy in a GitOps fashion. The `.doco-cd.yml` file in the root of the repo specifies which workloads are deployed in production. Each workload is in its own directory.

## Repository structure
```
- media-server
  |- docker-compose.yml    # deploys a specific workload
  |- .enc.env              # SOPS-encrypted environment variables
- monitoring 
  |- docker-compose.yml    # deploys a specific workload
- tailscale 
  |- docker-compose.yml    # deploys a specific workload
- nfs-test
  |- docker-compose.yml    # test stack to verify NFS volume mounting
- docker-compose.yml       # deploys doco-cd itself
- .doco-cd.yml             # specifies the deployments doco-cd should do
```

## Developing/implementing an issue:
1. Before making code changes, follow the testing instructions below to verify the current state of the code.
  - Only start developing the new functionality if all containers are healthy or stopped with exit code 0.
  - If something is failing before you make code changes, report back to the user about what's broken (including relevant error details) and wait for instructions.
2. After verifying all containers in the relevant workload are healthy, make code changes to implement the requested functionality.
3. Run `docker compose up -d` again to deploy the changes. Keep iterating on code changes and testing until the requested functionality is realized.
4. Only submit Pull Requests if all containers are healthy.

## Testing locally:

### NFS Configuration
Docker volumes using `driver_opts: type: nfs` rely on host kernel NFS support. For local testing:
- Run a real NFS-compatible test service/container or VM exporting:
  - `:/volume1/media-server-storage`
  - `:/volume1/downloads`
- Set `NFS_SERVER_ADDR` to the IP or hostname of your test NFS server (defaults to production IP `192.168.1.111` when unset).
- Verify NFS connectivity using the `nfs-test` stack:
  ```bash
  cd nfs-test
  NFS_SERVER_ADDR=<test-nfs-ip> docker compose up
  ```

### Testing a specific workload directly:
1. `cd` into the directory of the specific workload (for example: `media-server/`).
2. Run `sops decrypt .enc.env > .env` to decrypt the dotenv file with sops (requires age key configured).
3. If the workload uses NFS volumes (e.g. `media-server`), ensure `NFS_SERVER_ADDR` is set in the environment or `.env`.
4. Run `docker compose up -d` to deploy the workload.
5. Check container health with `docker ps`.
6. Use `docker logs [containerName]` to review container logs.

### Testing doco-cd continuous deployment locally:
You can test doco-cd locally without pushing commits to GitHub:
1. The root `docker-compose.yml` mounts the local repository to `/repo:ro` (controlled by `REPO_DIR`, defaults to `.`).
2. Point doco-cd to the local repository using `REPO_URL=file:///repo`.
3. Set `RUN_ONCE=true` to perform a single deployment pass instead of continuously polling while iterating.
4. Run:
   ```bash
   REPO_URL=file:///repo RUN_ONCE=true NFS_SERVER_ADDR=<test-nfs-ip> docker compose up -d
   ```
5. Check doco-cd logs:
   ```bash
   docker logs -f home-server
   ```
