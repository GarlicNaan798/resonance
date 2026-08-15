# Background reading

The PDFs that used to sit in this directory were removed before the repository
was made public. Redistributing publishers' PDFs is not ours to do, and at
~13 MB they were half the repo. They are cited here instead.

DOIs marked **verified** were read from the file's own XMP metadata. One is
marked *inferred*. It follows the publisher's standard identifier pattern but
was not confirmed against the document, so check it before quoting it.

| Work | Where | Identifier |
|---|---|---|
| Telematics and Informatics Reports (2026) | Elsevier | `10.1016/j.teler.2026.100332`, **verified** |
| Cognitive Neurodynamics (2021) | Springer | `10.1007/s11571-021-09693-y`, **verified** |
| F1000Research, article 168220 | F1000Research | `10.12688/f1000research.168220.1`, *inferred from the filename* |
| "The role of neuromarketing in decoding brain stimuli and consumer behaviour" | IJCRSEE | no DOI recovered |
| IJNRD paper `IJNRD2504243` | IJNRD | no DOI; `ijnrd.org/papers/IJNRD2504243.pdf` |

These were orientation reading on neuromarketing and consumer neuroscience.
None of them is load-bearing for the model. A good thing, given how much of
that literature this project ended up rejecting. `MacLean`'s triune brain and
left/right hemisphere dominance are excluded on purpose; both are discredited
as neuroscience despite their popularity in neuromarketing writing. See
`FUNDAMENTALS.md`.

## What the system actually rests on

These three are load-bearing, and are cited properly because the numbers in
this repository depend on them.

**Upworthy Research Archive**, 32,487 randomised A/B tests. The training data,
and the only public corpus pairing randomised copy variants with real click
outcomes.
J. N. Matias, K. Munger, M. Le Quere, C. Ebersole (2021). *The Upworthy
Research Archive: A time series of 32,487 experiments in U.S. media.*
Scientific Data 8, 195. `10.1038/s41597-021-00934-7`

**Warriner norms**, valence, arousal and dominance for 13,905 words, including
separate ratings by gender, age band and education. The demographic
conditioning comes from here.
A. B. Warriner, V. Kuperman, M. Brysbaert (2013). *Norms of valence, arousal,
and dominance for 13,915 English lemmas.* Behavior Research Methods 45,
1191–1207. `10.3758/s13428-012-0314-x`

**Brysbaert concreteness norms**, 39,954 words.
M. Brysbaert, A. B. Warriner, V. Kuperman (2014). *Concreteness ratings for
40 thousand generally known English word lemmas.* Behavior Research Methods 46,
904–911. `10.3758/s13428-013-0403-5`

Each carries its own licence. The repository ships *derived* values,
per-construct aggregates in `resonance/lib/inference/norms.json`, not the
source datasets, but if you intend commercial use, read the originals' terms
rather than relying on this project's MIT licence, which covers only the code.
