import re

# --- generate_snapshot.py: pull meeting_date into both consensus dicts ---
gs_path = "generate_snapshot.py"
content = open(gs_path).read()

for bank in ("BOC", "FED"):
    old = f'''    cursor.execute("""
        SELECT outcome, probability
        FROM rate_probabilities
        WHERE central_bank = '{bank}'
        ORDER BY asof_date DESC, meeting_date ASC
        LIMIT 1
    """)'''
    new = f'''    cursor.execute("""
        SELECT outcome, probability, meeting_date
        FROM rate_probabilities
        WHERE central_bank = '{bank}'
        ORDER BY asof_date DESC, meeting_date ASC
        LIMIT 1
    """)'''
    assert old in content, f"{bank} query block not found"
    content = content.replace(old, new)

for var, dict_name in (("boc_result", "boc_consensus"), ("fed_result", "fed_consensus")):
    old = f'''    if {var}:
        outcome, prob = {var}
        {dict_name} = {{
            "outcome": outcome,
            "probability": prob
        }}'''
    new = f'''    if {var}:
        outcome, prob, meeting_date = {var}
        {dict_name} = {{
            "outcome": outcome,
            "probability": prob,
            "meeting_date": meeting_date
        }}'''
    assert old in content, f"{var} unpack block not found"
    content = content.replace(old, new)

open(gs_path, "w").write(content)
print("generate_snapshot.py patched")

# --- dashboard.html: add flag + meeting_date to both policy tile pushes ---
dh_path = "dashboard.html"
content = open(dh_path).read()

for bank, flag, label in (("boc", "🇨🇦", "BoC"), ("fed", "🇺🇸", "Fed")):
    old = f'''                if (data.{bank}_consensus && data.{bank}_consensus.outcome) {{
                    policyTiles.push({{
                        series_key: "{bank}.consensus",
                        label: "{label} Next Decision",
                        value: data.{bank}_consensus.outcome.toUpperCase(),
                        value_pct: (data.{bank}_consensus.probability * 100).toFixed(1),
                        obs_date: "Market Consensus",
                    }});
                }}'''
    new = f'''                if (data.{bank}_consensus && data.{bank}_consensus.outcome) {{
                    policyTiles.push({{
                        series_key: "{bank}.consensus",
                        label: "{label} Next Decision",
                        flag: "{flag}",
                        value: data.{bank}_consensus.outcome.toUpperCase(),
                        value_pct: (data.{bank}_consensus.probability * 100).toFixed(1),
                        meeting_date: data.{bank}_consensus.meeting_date,
                        obs_date: "Market Consensus",
                    }});
                }}'''
    assert old in content, f"{bank} policyTiles push block not found"
    content = content.replace(old, new)

# --- dashboard.html: render flag header + meeting date in the policy tile template ---
old_render = '''                            if (d.value_pct) {
                                return `
                                    <div class="tile">
                                        <div class="tile-label">${d.label}</div>
                                        <div class="tile-value">${d.value}</div>
                                        <div class="tile-date">${d.value_pct}% confidence</div>
                                    </div>
                                `;
                            }'''
new_render = '''                            if (d.value_pct) {
                                return `
                                    <div class="tile">
                                        <div class="tile-header">
                                            <div class="tile-label">${d.label}</div>
                                            <div class="tile-flag">${d.flag || ""}</div>
                                        </div>
                                        <div class="tile-value">${d.value}</div>
                                        <div class="tile-date">${d.value_pct}% confidence \\u00b7 meeting ${d.meeting_date || "TBD"}</div>
                                    </div>
                                `;
                            }'''
assert old_render in content, "policy tile render template not found"
content = content.replace(old_render, new_render)

open(dh_path, "w").write(content)
print("dashboard.html patched")
