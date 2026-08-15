# Study responses go here

Drop each participant's JSON in this folder, then:

```bash
python model/human_baseline.py score responses/*.json
```

**The contents of this folder are gitignored.** Only this README is tracked.
The repository is public, and a stray `git add -A` would otherwise publish
participant data. `score` also refuses to run on any file git is tracking, so
the mistake fails loudly rather than silently.

## What a response actually contains

The whole payload, and nothing else:

```json
{
  "seed": 7,
  "n": 60,
  "profile": { "years": 7, "paid": true },
  "answers": [ { "id": 0, "choice": 1, "ms": 4210 } ]
}
```

No name. No email. No IP address — the quiz runs entirely in the browser and
makes no request. No device or browser fingerprint. No free text, so nobody can
accidentally type something identifying. `ms` is elapsed time on that item, not
a wall-clock timestamp, so it does not reveal when anyone was working.

This matters for two reasons. It is why the file is safe to send over ordinary
email, and it is why participants can be told truthfully that the only thing
they are handing over is sixty binary choices and how long each took.

## Keep the key out of circulation

`data/processed/human_key.json` holds the answers. It is gitignored and must
never be sent to a participant, posted, or committed. Anyone holding it can
score perfectly, which would quietly destroy the study.

The quiz file contains no answers — verified — so distributing
`human_quiz.html` is safe.

## Naming

Anything ending `.json`. Something like `p01.json`, `p02.json` is enough; there
is no need to name the file after the person, and better not to.
