# Template for the VM's ~/.gitconfig. Rendered by bin/machine
# (render_git_templates) with host values for name/email and the chosen SSH
# signing pubkey. Commit + tag signing are on by default.
[user]
  name = __GIT_NAME__
  email = __GIT_EMAIL__
  signingkey = __GIT_SIGNING_KEY__

[gpg]
  format = ssh

[gpg "ssh"]
  program = ssh-keygen
  allowedSignersFile = ~/.config/git/allowed_signers

[commit]
  gpgsign = true
[tag]
  gpgsign = true

[init]
  defaultBranch = main
[pull]
  rebase = true
[fetch]
  prune = true
