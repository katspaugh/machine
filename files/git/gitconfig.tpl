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
