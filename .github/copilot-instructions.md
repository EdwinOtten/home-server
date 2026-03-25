This home server project is based on docker compose files.

In production, doco-cd is used to deploy in a GitOps fashion. The `.doco-cd.yml` file in the root of the repo specifies which workloads are deployed in production. Each workload is in it's own directory.

## Repository structure
```
- media-server
  |- docker-compose.yml    # deploys a specific workload
  |- .enc.env
- monitoring 
  |- docker-compose.yml    # deploys a specific workload
- tailscale 
  |- docker-compose.yml    # deploys a specific workload
- docker-compose.yml       # deploys doco-cd itself
- .doco-cd.yml             # specifies the deployments doco-cd should do
```

## Developing/implementing an issue:
1. Before making code changes, follow the testing instructions below to verify if the current state of the code runs and all containers are healthy.
2. After verifying all containers in the relevant workload are healthy, make code changes to implement the requested functionality.
3. Run `docker compose up -d` again to deploy the changes. Keep iterating on code changes and testing until the requested functionality is realized.
4. Only submit Pull Requests if all containers are healthy.

## Testing locally:
1. `cd` into the directory of the specific workload (for example: /media-server)
2. run `sops decrypt .enc.env > .env` to decrypt the dotenv file with sops.
3. run `docker compose up -d` to deploy the docker-compose.yml
4. to check container health, run `docker ps` every 30 seconds.
5. use `docker logs [containerName]` to review the logs of a container 