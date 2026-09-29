"""Read final evidence CSVs."""
import csv, glob, os

results_dir = "evidence"
csvs = sorted(glob.glob(os.path.join(results_dir, "*.csv")))

for path in csvs:
    base = os.path.basename(path)
    rows = list(csv.DictReader(open(path, "r", encoding="utf-8")))
    temps = [float(x["temperature"]) for x in rows if x.get("temperature")]
    volts = [float(x["voltage"]) for x in rows if x.get("voltage")]
    fails = [x for x in rows if "FAILURE" in x.get("event", "")]
    decisions = [x["decision"] for x in rows if x.get("decision")]
    local_count = decisions.count("LOCAL")
    offload_count = decisions.count("OFFLOAD")
    reject_count = decisions.count("REJECT")
    throttle_count = decisions.count("THROTTLE")

    if temps and volts:
        print(base)
        print(f"  Temp:  {min(temps):.1f} - {max(temps):.1f} C")
        print(f"  Volt:  {min(volts):.3f} - {max(volts):.3f} V")
        print(f"  Fails: {len(fails)}")
        print(f"  Local={local_count}  Offload={offload_count}  "
              f"Reject={reject_count}  Throttle={throttle_count}")
        print()
