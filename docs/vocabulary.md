# Scientific Vocabulary

These terms are separate claim dimensions. Evidence for one must not be used as
evidence for another without an explicit argument.

| Dimension | Operational question |
| --- | --- |
| Computability | Is there a finite effective procedure? |
| Complexity | How do required resources scale? |
| Learnability | What evidence and resources acquire the behaviour? |
| Generality | Across which heterogeneous task families does it transfer? |
| Autonomy | How long can it act and learn without external intervention? |
| Efficiency | How much declared capability is delivered per resource unit? |
| Physical realizability | Can the computation be embodied within physical constraints? |

## Claim strength

Use the strongest label justified by the artifact, in descending order:
`theorem`, `asymptotic_separation`, `bound_separation`,
`verified_algorithmic_advantage`, or `empirical_pareto_dominance`. Empirical
dominance is never described as a proof.

## Baselines

Every comparison names and pins a baseline manifest. The initial families are
Transformers, recurrent and convolutional neural networks, state-space models,
and neural-memory systems. “DNN” alone is not a reproducible baseline.
