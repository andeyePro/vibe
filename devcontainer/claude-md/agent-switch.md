# Switching Vibe's lead agent

To switch on the user's request, save work and finish or stop autonomous runs, then run `vibe-agent codex` or `vibe-agent claude`. Tell the user to exit normally; Vibe reopens with that agent and remembers it. Never kill the session or clear ambiguous supervisor state. The request grants no credentials. Histories stay separate; leave a repository handoff when needed.

For “help”, briefly explain /vs, /vss, /vsss and switching. Consult installed commands. Codex's reliable forms are $vs/$vss/$vsss; its composer may intercept bare slashes, while a leading space passes them through.
