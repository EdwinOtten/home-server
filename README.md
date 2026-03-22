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
1. Install age:
   ```bash
   sudo apt install age
   ```
1. [Install sops](https://github.com/getsops/sops/releases)
1. Follow [encryption instructions by doco-cd](https://github.com/kimdre/doco-cd/wiki/Encryption)
