"""Smoke test: architecture instantiates, runs, and honours its constraints."""

import torch

from architecture import ModelConfig, ResonanceNet, describe_constraints

cfg = ModelConfig(n_features=48)
m = ResonanceNet(cfg)

print(m.capacity_report(n_train_clusters=5791))
print()
print(describe_constraints())
print()

x = torch.randn(8, cfg.n_features)
aud = torch.randint(0, cfg.n_audiences, (8,))
out = m(x, aud)

print("score shape     :", tuple(out["score"].shape))
print("modules         :", list(out["modules"].keys()))
print("arousal optimum : {:.3f}".format(float(out["arousal_optimum"])))
print()

print("--- constraint signs (must hold at every point in training) ---")
checks = [
    ("C1 arousal quadratic  (< 0)", float(m.arousal_quad), lambda v: v < 0),
    ("C2 arousal->encoding  (>=0)", float(m.arousal_to_encoding), lambda v: v >= 0),
    ("C4 fluency weight     (>=0)", float(m.fluency_w), lambda v: v >= 0),
    ("C5 cognitive load     (<=0)", float(m.load_w), lambda v: v <= 0),
]
ok = True
for label, val, test in checks:
    good = test(val)
    ok &= good
    print("  {:<28} {:+.4f}  {}".format(label, val, "OK" if good else "VIOLATED"))

# Adversarial check: hammer the raw parameters and confirm the constrained
# properties still cannot flip sign. This is what "by construction" must mean.
print()
print("--- adversarial: force raw params to extreme values ---")
with torch.no_grad():
    m._arousal_quad.fill_(-50.0)
    m._arousal_to_encoding.fill_(-50.0)
    m._fluency_w.fill_(-50.0)
    m._load_w.fill_(-50.0)
post = [
    ("C1 quad  still < 0", float(m.arousal_quad), lambda v: v < 0),
    ("C2 gate  still >=0", float(m.arousal_to_encoding), lambda v: v >= 0),
    ("C4 fluen still >=0", float(m.fluency_w), lambda v: v >= 0),
    ("C5 load  still <=0", float(m.load_w), lambda v: v <= 0),
]
for label, val, test in post:
    good = test(val)
    ok &= good
    print("  {:<28} {:+.6f}  {}".format(label, val, "HELD" if good else "BROKEN"))

print()
print("SMOKE TEST:", "PASS" if ok else "FAIL")
