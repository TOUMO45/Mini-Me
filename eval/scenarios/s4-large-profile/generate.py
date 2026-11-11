#!/usr/bin/env python3
"""Generate the S4 profile: 60 records, a handful relevant to the task, the rest realistic noise.

Deterministic. Run: python3 eval/scenarios/s4-large-profile/generate.py > eval/scenarios/s4-large-profile/profile.md
"""
import random

R = random.Random(4)


def rec(rid, typ, cond, act, scope, ev, src, date, status="confirmed", reason="unknown",
        sup="—", extra=None, updated=None):
    lines = [f"### {rid} · {typ}"]
    for k, v in (extra or {}).items():
        lines.append(f"- {k}: {v}")
    lines += [
        f"- Condition: {cond}", f"- Action: {act}", f"- Scope: {scope}", "- Exceptions: none known",
        f"- Evidence: {ev}", f"- Sources: {src}", f"- Reason: {reason}", f"- Status: {status}",
        f"- Source date: {date}", f"- Updated: {updated or date}", f"- Supersedes: {sup}", "- Sensitivity: ordinary",
    ]
    return "\n".join(lines)


relevant = [
    rec("pref-004", "Preference", "When writing a client proposal", "Include a pricing table with three tiers",
        "Client proposals", '"From now on, for client proposals, include a pricing table with three tiers."',
        "chat-2026-09-14-hallam", "2026-09-14"),
    rec("rule-003", "Decision rule", "When writing a client proposal", "Lead with the time-and-materials option",
        "Client proposals", '"Always lead with T&M."', "chat-2026-05-02", "2026-05-02", status="superseded",
        updated="2026-10-01"),
    rec("rule-011", "Decision rule", "When writing a client proposal",
        "Lead with T&M if the scope will move; lead with fixed fee if the scope is fixed and well-defined",
        "Client proposals", '"Correction: only lead with T&M when scope will move. Fixed scope, fixed fee first."',
        "chat-2026-10-01", "2026-10-01", reason="Fixed fee on moving scope loses money; T&M on fixed scope looks evasive",
        sup="rule-003"),
    rec("pref-009", "Preference", "When writing a client proposal", "Put all case studies in a section at the end",
        "Client proposals", "Accepted Brightline proposal had case studies at the end", "doc-2026-06-10-brightline",
        "2026-06-10", status="tentative"),
    rec("pref-021", "Preference", "When writing a client proposal",
        "Put exactly one case study right after the executive summary",
        "Client proposals", '"Move the case study up under the summary. One is enough, nobody reads three."',
        "chat-2026-10-22", "2026-10-22", reason="Readers stop after the first page; three case studies go unread"),
    rec("exc-002", "Exception", "When sending a client proposal in October 2026",
        "Offer the 10% early-signing discount", "Client proposals sent in October 2026",
        '"For October only, offer 10% off if they sign within two weeks."', "chat-2026-09-30", "2026-09-30",
        extra={"Expires": "2026-10-31"}),
    rec("rule-014", "Decision rule", "When procurement will read a proposal",
        "Add a terms appendix: payment schedule, liability cap, data handling", "Client proposals read by procurement",
        '"Procurement always bounces it without the terms appendix."', "chat-2026-07-08", "2026-07-08",
        reason="Procurement rejects proposals without it"),
    rec("pref-030", "Preference", "When sending anything to leadership", "Use bullet points", "Documents for leadership",
        'Lena (forwarded): "always use bullet points for everything you send to leadership."',
        "chat-2026-09-14-hallam", "2026-09-14", extra={"Said by": "Lena (manager)"}),
    rec("pref-017", "Preference", "When signing a client proposal", "Sign as 'Sam Okafor, Principal'",
        "Client proposals", "Accepted Hallam proposal was signed this way", "doc-2026-09-15-hallam", "2026-09-15",
        status="tentative"),
]

noise_specs = [
    ("Preference", "When writing an exercises-only arithmetic worksheet", "Start with problems, leave answer space", "Arithmetic worksheets"),
    ("Preference", "When writing a lesson plan for year 4", "Open with a real-world hook question", "Year 4 lessons"),
    ("Preference", "When designing for Kestrel Coffee", "Use the dark espresso palette with serif headings", "Kestrel Coffee brand work"),
    ("Decision rule", "When presenting design options to a client", "Show exactly two options and recommend one", "Client design reviews"),
    ("Preference", "When writing a status email to Acme", "Put the decision needed in the first line", "Acme Logistics emails"),
    ("Preference", "When reviewing a pull request", "Comment on correctness before style", "Code review"),
    ("Decision rule", "When choosing a database for a prototype", "Use SQLite unless concurrent writes are required", "Prototypes"),
    ("Problem-solving method", "When debugging a flaky test", "Reproduce with a fixed seed before changing code", "Test debugging"),
    ("Preference", "When booking work travel", "Prefer trains for trips under 4 hours", "Work travel"),
    ("Preference", "When writing a LinkedIn post", "No hashtags, one link at the end", "LinkedIn posts"),
    ("Preference", "When making slides for an internal all-hands", "Max 12 slides, one idea per slide", "Internal presentations"),
    ("Goal", "When running the Q4 hiring loop", "Close two senior engineer offers by Dec 15", "Q4 hiring"),
    ("Preference", "When writing a job description", "Lead with the problems the hire will solve", "Job descriptions"),
    ("Decision rule", "When a vendor quote exceeds budget by more than 15%", "Request a second quote before negotiating", "Vendor selection"),
    ("Preference", "When writing meeting notes", "Decisions first, then action items with owners", "Meeting notes"),
    ("Preference", "When drafting a blog post", "Keep paragraphs under four lines", "Company blog"),
    ("Problem-solving method", "When estimating a project", "Estimate in ranges and name the biggest unknown", "Project estimates"),
    ("Preference", "When writing to Borealis Foods", "Use formal tone", "Borealis Foods communication"),
    ("Preference", "When writing release notes", "Group by user impact, not by component", "Release notes"),
    ("Decision rule", "When choosing a chart for a monthly report", "Use a line chart for trends over time", "Monthly reports"),
    ("Preference", "When writing a cold outreach email", "Under 120 words, one question at the end", "Sales outreach"),
    ("Preference", "When preparing an investor update", "Lead with cash runway and burn", "Investor updates"),
    ("Problem-solving method", "When a client escalates", "Acknowledge within 2 hours, propose a call", "Client escalations"),
    ("Preference", "When writing an incident postmortem", "Blameless, timeline first", "Postmortems"),
    ("Preference", "When naming files for clients", "Use YYYY-MM-DD prefix", "Client deliverables"),
    ("Decision rule", "When a deadline slips by more than a week", "Tell the client before the original date", "Client projects"),
    ("Preference", "When writing a design brief", "Include three reference examples", "Design briefs"),
    ("Preference", "When making a social graphic", "Use the brand teal and one headline", "Social graphics"),
    ("Goal", "When writing a grant application", "Score above 80 on the impact criterion", "Grant applications"),
    ("Preference", "When writing a thank-you note to a mentor", "Handwritten tone, mention one specific lesson", "Personal notes"),
]

def build(n_noise: int = 51) -> str:
    """The relevant records, n_noise distractors, and one project record, as profile text."""
    noise = []
    counters = {"Preference": 40, "Decision rule": 20, "Problem-solving method": 1, "Goal": 1}
    for i in range(n_noise):
        typ, cond, act, scope = noise_specs[i % len(noise_specs)]
        if i >= len(noise_specs):
            cond = cond + f" (variant {i - len(noise_specs) + 1})"
        counters[typ] += 1
        rid = f"{prefix[typ]}-{counters[typ]:03d}"
        month = R.randint(3, 10)
        day = R.randint(1, 28)
        status = R.choice(["confirmed", "confirmed", "tentative"])
        noise.append(rec(rid, typ, cond, act, scope, f'"{act}."', f"chat-2026-{month:02d}-{day:02d}-n{i}",
                         f"2026-{month:02d}-{day:02d}", status=status))
    cut = min(25, len(noise))
    blocks = relevant[:4] + noise[:cut] + relevant[4:] + noise[cut:] + [proj]
    return "# Mini Me profile\n\n## Records\n\n" + "\n\n".join(blocks) + "\n"


proj = rec("proj-003", "Project state", "", "", "", '"Brightline signed the fixed-fee version."', "chat-2026-06-20",
           "2026-06-20")
proj = proj.replace("- Condition: \n- Action: \n- Scope: \n", "- Project: Brightline Ports proposal\n"
                    "- Constraints: Brightline legal requires UK English\n- Latest version: brightline-v4.docx\n"
                    "- Last decision: Fixed fee, 120k GBP\n- Next step: Kickoff scheduled\n")

prefix = {"Preference": "pref", "Decision rule": "rule", "Problem-solving method": "method", "Goal": "goal"}

if __name__ == "__main__":
    print(build(), end="")
