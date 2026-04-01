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
