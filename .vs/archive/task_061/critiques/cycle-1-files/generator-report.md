# Generator report, cycle 1, task_061

Changed: devcontainer/taskandi-client.mjs (v2.1 contract, LEGACY pin keeps v1), devcontainer/taskandi-usage.mjs (--task, resolveTask), docs/taskandi-client.md, CHANGELOG.md, smoke/checks_28/29 (pin + unbound ask shape only).
All ACs implemented (AC1-AC13). Scratch test: .vs/cycle-1/scratch-tests/v2.mjs (passes).
Notes: complete(completed:true) and release delete `claimed` unconditionally (literal spec). Flush checks all queued jobs' bindings before dispatching any.
Commands: code-check.py exit 0; checks_28 exit 0; checks_29 exit 0; smoke-test.py < /dev/null exit 0.
