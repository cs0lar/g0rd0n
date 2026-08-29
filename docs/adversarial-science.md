# Adversarial Science Loop

The Phase 11 loop treats generator, critic, falsifier, and replicator as
epistemic roles carried by `RoleAssignment` data. One backend may perform every
role; no agent topology is implied.

For each novel candidate, the loop records the strongest competing explanation,
hidden assumptions, known failure modes, and critic objections. It selects the
cheapest proposed falsifier, applies an explicit Bayesian evidence-weight
update, stops rejected programs before replication, and requires an agreeing
replication plus a declared posterior threshold before promotion.

Novelty uses normalized token-set similarity. It prevents obvious duplicate
spending but is not a semantic novelty proof. Likelihoods are declared inputs,
not objective truth; calibration is therefore a later empirical obligation.

The synthetic comparison seeds confounded hypotheses and gives adversarial and
confirmation-only policies the same one-unit experimental cost. It tests the
orchestration claim that searching for confounders rejects more seeded flaws;
it does not establish performance on real scientific work.
