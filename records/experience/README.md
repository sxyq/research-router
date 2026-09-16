# Experience Records

This directory stores local JSONL observations derived from completed route records.

- `skills/<skill-id>.jsonl`: query patterns, execution outcomes, source limits, and failures for one Skill.
- `platforms/<platform-id>.jsonl`: access behavior, Skill order, source coverage, and route outcomes for one platform.

Generate entries with:

```bash
python3 scripts/update-experience.py records/routes/YYYY-MM-DD/<route>.json
```

Each entry uses `route_id + subject_id` as its stable local identity. Keep credentials, cookies, raw page bodies, and private research notes outside this directory.
