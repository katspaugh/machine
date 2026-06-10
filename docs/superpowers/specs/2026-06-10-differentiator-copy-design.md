# Differentiator-led copy for landing page + README

**Date:** 2026-06-10
**Status:** Approved

## Problem

The headline framing on both the landing page (`docs/index.html`) and the README is
"one isolated/disposable VM per project" — now the commodity claim of every sandbox
tool (microVM runtimes, devcontainers, container sandboxes). machine's actual
differentiators live below the fold: it boots a *ready-to-work* dev environment,
keeps keys/secrets on the host, and is built for agent workflows.

## Decisions

- **Framing:** no competitor names; sharpen our own copy instead of a comparison section.
- **Headline differentiators (in order):** full dev home (not a bare sandbox),
  key & secret hygiene, agent-native workflow.
- **Approach:** light-touch — rewrite lead copy in place, no structural/CSS changes.

## Changes

### Landing page (`docs/index.html`)

- `<title>`, `og:title`, `og:image:alt`: `machine — one ready-to-work Linux machine per project`
- `meta description` + `og:description`: "A full dev environment per project, not
  just a sandbox: agents preinstalled, commits signed, private keys never leave
  your Mac. machine boots ready-to-work Linux VMs where ‘yes to everything’ is safe."
- Hero eyebrow: unchanged.
- Hero h1: `One ready-to-work Linux machine per project.`
- Hero sub: "Plenty of tools can boot you an isolated VM. machine boots one your
  agent can actually work in: Docker, Node, `gh`, signed git, Claude Code with
  plugins — provisioned from version-controlled templates, disposable when it gets
  weird. Your private keys never enter the VM; secrets live in tmpfs. Saying yes
  to everything is finally a safe answer."
- "Four things" cards reordered: Agent-ready → Real boundary → Host stays clean →
  Reproducible (numbers follow). Agent card gains the auto-mode line ("safe by
  construction — nothing of yours in there to lose"); its keys sentence moves to
  the boundary card.

### README

- Title: `# machine — one ready-to-work dev VM per project`
- Intro paragraph: leads with "isolated VMs are table stakes — an empty sandbox
  still costs you an afternoon", then the provisioned-environment list, then
  no-mount/no-bleed/keys-stay-home.
- "Why" section: keeps the autonomy framing, adds "a bare sandbox fixes the safety
  problem and creates a setup problem", folds in signing-via-forwarded-agent and
  tmpfs secrets, ends on "no morning of setup".

Everything else (promise, machine room, threat model, profiles, install, docs)
stays untouched.
