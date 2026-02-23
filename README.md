# home-server
Home Server deployed by doco-cd.

## .bashrc aliases
```
alias d=docker
alias dlogsa="docker logs home-server 2>&1 | jq ."
alias dlogs="docker logs --since 5m home-server 2>&1 | jq ."
alias l='ls -lra --color=auto'
```
