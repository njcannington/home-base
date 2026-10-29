# Running Home Base

The engine is `./bin/hb`. Everything else is reached through Claude.

## From the desk
    /home-base          pull the brief
    ./bin/hb list       the raw ledger

## From the phone
Claude iOS app -> Code -> the `home-base` session. Say "home base" or
"/home-base". Capture anything by just saying it.

## The service

The source of truth for the unit file is `etc/claude-remote-control.service`
in this repo — not the copy under `~/.config/systemd/user/`, which is
untracked and lost on a machine rebuild. After editing the tracked copy,
install it with:

    cp etc/claude-remote-control.service ~/.config/systemd/user/ && systemctl --user daemon-reload

Day-to-day:

    systemctl --user status claude-remote-control
    systemctl --user restart claude-remote-control
    journalctl --user -u claude-remote-control -n 50

If the phone cannot see the session, check the service first, then that
`loginctl show-user $USER --property=Linger` says `Linger=yes`.

## First-run workspace trust

If `systemctl --user status claude-remote-control` shows a restart loop
with `Error: Workspace not trusted` in the journal, Claude Code has never
had its one-time trust dialog accepted for `~/code/home-base`. This is a
per-directory, per-machine thing and only needs doing once. Fix it by
hand (it needs an actual terminal, not the service):

    cd ~/code/home-base
    claude
    # accept the trust prompt, then exit (Ctrl-D or /exit)
    systemctl --user restart claude-remote-control
    systemctl --user status claude-remote-control --no-pager

Once accepted, the service comes up clean on its own from then on,
including across reboots.

## Pinned node path

The service's `PATH` is pinned to a specific nvm-managed node install:
`~/.nvm/versions/node/v22.22.2/bin`. This is needed because `claude
remote-control` is a general-purpose session (MCP servers, `npx`, etc.),
not just `bin/hb`, and a phone-driven session has no terminal on which
to notice a missing-binary failure — it would just silently fail.

If node gets upgraded via nvm, this path goes stale silently. Update it
with:

    readlink -f "$(command -v node)"

and edit the `Environment=PATH` line in the tracked
`etc/claude-remote-control.service` (see "The service" above) to match
the new `.../bin` directory, then install it and restart the service.
