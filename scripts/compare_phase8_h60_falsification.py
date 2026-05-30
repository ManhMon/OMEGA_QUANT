"""h=60 falsification."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

real = json.load(open(ROOT / ".ly_state/session/phase8_h60_1B.json"))["baseline"]
shuf = json.load(open(ROOT / ".ly_state/session/phase8_h60_1B_shuffle.json"))["baseline"]

print("h=60 falsification (1B, y-shuffle within each date):")
print(f"  median IC:        real {real['median_test_ic']:+.4f}   shuf {shuf['median_test_ic']:+.4f}")
print(f"  fold SR_ann:      real {real['fold_dsr']['sr_mean_annualized']:+.3f}   shuf {shuf['fold_dsr']['sr_mean_annualized']:+.3f}")
print(f"  fold DSR:         real {real['fold_dsr']['dsr']:.4f}   shuf {shuf['fold_dsr']['dsr']:.4f}")
print(f"  pool SR_ann:      real {real['dsr_sr_ann']:+.3f}   shuf {shuf['dsr_sr_ann']:+.3f}")
print()
ic_drop = abs(shuf["median_test_ic"]) / max(abs(real["median_test_ic"]), 1e-9)
sr_drop = abs(shuf["fold_dsr"]["sr_mean_annualized"]) / max(abs(real["fold_dsr"]["sr_mean_annualized"]), 1e-9)
ic_signflip = real["median_test_ic"] * shuf["median_test_ic"] < 0
print(f"  IC magnitude collapse: {ic_drop*100:.1f}% of real (sign flip: {ic_signflip})")
print(f"  SR magnitude collapse: {sr_drop*100:.1f}% of real")
print()
verdict = "PASS" if (sr_drop < 0.30 and (ic_signflip or ic_drop < 0.50)) else "FAIL"
print(f"  Falsification verdict: {verdict}")
