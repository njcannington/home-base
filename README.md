# Home Base

A tiny personal ledger plus a Claude Code skill that turns it into a daily
brief. You tell Claude about projects, deadlines and things you're waiting
on; it records them with `hb`. When you say "home base" or "brief me", it
shows only what actually needs you today, and most days that's nothing.

Requires Python 3.11+ (standard library only) and Claude Code.

## Install

1. Put this folder at `~/code/home-base` (the skill expects that path; if
   you put it elsewhere, edit the path at the top of `skill/SKILL.md`).
2. Install the skill:

       mkdir -p ~/.claude/skills/home-base
       cp ~/code/home-base/skill/SKILL.md ~/.claude/skills/home-base/

3. Check it works:

       cd ~/code/home-base && python3 -m unittest discover -s tests -t .
       ./bin/hb list

4. Start Claude Code and say "home base". `entries/` starts empty; just
   tell Claude what you've got going on and it will log it.

`docs/running.md` and `etc/` cover the optional setup for using it from
your phone (`claude remote-control` as a systemd user service). Skip them
if you only use it at the desk.

## Layout

- `bin/hb`: the CLI. `hb add|touch|state|set|done|retire|list|brief`
- `homebase/`: the engine (decay, brief selection, storage)
- `entries/`: your ledger, one TOML-fronted Markdown file per item
- `graveyard/`: retired entries
