# home-server
Home Server deployed by doco-cd.

## .bashrc aliases
```
alias d=docker
alias dlogsa="docker logs home-server 2>&1 | jq ."
alias dlogs="docker logs --since 5m home-server 2>&1 | jq ."
alias l='ls -lra --color=auto'
```

## Encrypting secrets using SOPS and age
1. Install age:
  ```bash
  sudo apt install age
  ```
1. [Install sops](https://github.com/getsops/sops/releases)
