# Automated Research-Program Lifecycle

`ResearchProgramSpec` declares the question, candidate hypotheses, ordered
experiment queue, multidimensional program budget, review requirements, retry
limits, and escalation policy. Every experiment carries an estimate, maximum,
expected value, and stop condition.

`ProgramJournal` is an append-only, hash-chained sequence of complete session
checkpoints. A new process resumes only by replaying and validating that
journal. State is checkpointed after initialization, session start, every
experiment result or failure, review and budget decisions, pause, escalation,
and completion.

The lifecycle preflights each experiment at its maximum cost. Human-gated work
waits without invoking the executor. Failed experiments retain their queue
position only within the declared retry allowance; budget denial, review
rejection, excessive failures, and provider maximum-cost violations follow the
explicit escalation policy.

Every exit returns the same report shape: question, hypotheses, experiments,
observations, evidence, claim changes, failures, money, tokens, compute, energy,
human attention, unresolved uncertainty, and best next question. Unexpected
executor exceptions have unknown cost and are recorded as failures; adapters
should return structured failed results whenever actual cost is known.
