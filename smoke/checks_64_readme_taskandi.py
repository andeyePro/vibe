"""README describes the Task&I integration end to end (2026-10-31, /vsss iter 8).

The client and harness are pinned by checks_50..63; this guards the one place a
new user reads first, so a later README edit cannot silently drop a behaviour.
"""
from smoke._core import *

README = REPO / "README.md"


def test_readme_taskandi_section():
    print("\n[readme-taskandi] README's Task&I section names every user-facing behaviour")
    text = README.read_text()
    start = text.find("### Work from Task&I (optional)")
    check("[readme-taskandi] the section exists", start >= 0, "")
    end = text.find("\n### ", start + 1)
    section = text[start:end if end > start else None] if start >= 0 else ""
    for needle in (".vibe/taskandi-descriptor.json", "chmod 600", "vibe --task", "vibe://open?project=",
                   "taskandi-harness.md", "Next task", "Questions go to you", "Silence", "Budget", "80%",
                   "proposes tasks", "keep or remove", "Repeating tasks", "Unbound projects behave exactly as before",
                   "docs/taskandi-client.md", "MANUAL-TESTS.md"):
        check(f"[readme-taskandi] the section mentions {needle!r}", needle in section, "")
    # Control: the section is bounded by the next heading, so a phrase that
    # lives only in another section ("Second brain") does not count here.
    check("[readme-taskandi] control: the section ends before the next heading", "Second brain" not in section, "")
