"""Deprecated Faker seeder; use the paired HMA-content/RF-placement flow."""

if __name__ == "__main__":
    raise SystemExit(
        "Faker seeding is disabled for the placement comparison. "
        "Generate B candidates with database\\generate_rf_honeytokens.py "
        "after HMA candidates, trained RF metadata, and department risk history exist."
    )
