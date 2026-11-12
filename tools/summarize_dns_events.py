"""Summarize the sanitized local evidence. No ADB, network, or writes."""
from pathlib import Path
import argparse
from collections import Counter
import json

def summarize(data):
    events=data["events"]
    if not events:
        raise ValueError("No sampled lookups")
    queries=[q for event in events for q in event["queries"]]
    return {
        "sampled_lookup_count":len(events),
        "query_attempt_count":len(queries),
        "lookup_return_codes":dict(sorted(Counter(str(e["return_code"]) for e in events).items())),
        "query_linux_errnos":dict(sorted(Counter(str(q["linux_errno"]) for q in queries).items())),
        "query_record_types":dict(sorted(Counter(str(q["record_type"]) for q in queries).items())),
        "query_rcodes":dict(sorted(Counter(str(q["rcode"]) for q in queries).items())),
        "network_types":dict(sorted(Counter(e["network_type"]["name"] for e in events).items())),
        "lookup_latency_us":{"min":min(e["latency_us"] for e in events),"max":max(e["latency_us"] for e in events)},
        "sampling_weighting_applied":False,
    }

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path",nargs="?",type=Path,default=Path(__file__).resolve().parents[1]/"evidence"/"dns-events.sanitized.json")
    args=parser.parse_args()
    data=json.loads(args.path.read_text(encoding="utf-8"))
    print(json.dumps(summarize(data),ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
