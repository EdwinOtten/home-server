This home server project is based on Docker Compose files and is deployed in a GitOps fashion using Doco-CD. The `.doco-cd.yml` file in the root of the repo specifies which workloads. Each workload is in its own directory.

## Repository structure
```
- media-server
  |- docker-compose.yml    # deploys a specific workload
  |- .enc.env              # SOPS-encrypted environment variables
- monitoring 
  |- docker-compose.yml    # deploys a specific workload
- tailscale 
  |- docker-compose.yml    # deploys a specific workload
- docker-compose.yml       # deploys doco-cd itself
- .doco-cd.yml             # specifies the deployments doco-cd should do
```

## Developing/implementing an issue:
1. Before making code changes, follow the testing instructions below to verify the current state of the code.
  - Only start developing the new functionality if all containers in this project are healthy or stopped with exit code 0.
  - If something is failing before you make code changes, report back to the user about what's broken (including relevant error details) and wait for instructions.
2. After verifying all containers in this project are healthy, make code changes to implement the requested functionality.
3. Use the Cleanup instructions in the README.md to redeploy from scratch. Keep iterating on code changes and testing until the requested functionality is realized.
4. Only commit changes and submit Pull Requests if you verified all containers are healthy AFTER making the changes.

## Testing locally:

1. Follow the steps in README.md to setup a local NFS server and deploy the project locally.
2. Check doco-cd deployment logs with `docker logs --since 5m home-server` to see if deployment was succesfully
3. Check container health with `docker ps`. All containers 

If needed: use `docker logs [containerName]` to review logs of specific containers.
