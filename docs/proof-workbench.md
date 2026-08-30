# Proof and Formal-Analysis Workbench

`FormalClaim` separates task family, competing architecture classes, explicit
assumptions, upper and lower complexity bounds, domain, and named proof
obligations. Proof certificates are stored as canonical, content-addressed JSON.
`VerifierRegistry` is a narrow adapter boundary for built-in or external theorem
checkers; a verifier must discharge every obligation before a claim is marked
verified.

Run the repository's toy theorem independently:

```bash
python -m g0rd0n.proofs verify proofs/toy-direct-address-membership.json
```

The theorem concerns static membership for `n` stored keys in a universe of
size `U > n`. Under a word-RAM direct-address assumption, a U-bit vector answers
with one indexed read. A deterministic ordered comparison decision tree holding
n distinct keys has capacity
`C(h) = 1 + 2 C(h-1) = 2^h - 1`, hence worst-case height at least
`ceil(log2(n+1))`. The checker validates this certificate and strictness for the
declared domain `n >= 4`; counterexample search checks concrete ranges.

This is a toy separation between deliberately restricted models. It is not a
separation from DNNs, Transformers, arbitrary programs, or unrestricted neural
architectures. The direct-address representation also spends U bits of memory,
which the theorem does not claim to improve.
