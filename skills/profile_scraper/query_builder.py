"""
query_builder.py — Smart Boolean Query Ingestion & Search Dork Generator.

Supports:
1. Direct raw Boolean search strings (e.g. '("SailPoint" OR "CyberArk") AND ("IAM Engineer" OR "Architect")').
2. Simple domain/technology inputs (automatic multi-tier role & technology boolean expansion).
3. Interactive CLI prompting when arguments are omitted.
"""

import re
from typing import List, Dict, Any, Tuple
from loguru import logger

import skills.profile_scraper.role_expansion as role_expansion

BOOLEAN_OPERATORS = [r'\bOR\b', r'\bAND\b', r'\bNOT\b']


def is_raw_boolean_query(query: str) -> bool:
    """
    Detects whether the input string contains explicit Boolean logic syntax
    (e.g., AND, OR, NOT, grouping parentheses, or quoted phrases).
    """
    if not query:
        return False

    q_stripped = query.strip()

    # Check for boolean operators
    has_operator = any(re.search(op, q_stripped) for op in BOOLEAN_OPERATORS)
    has_parentheses = "(" in q_stripped and ")" in q_stripped
    has_quotes = q_stripped.count('"') >= 2

    # A raw boolean query typically has operators and grouping or quotes
    return has_operator or (has_parentheses and has_quotes)


OPEN_TO_WORK_DORK_CLAUSE = '("open to work" OR "#opentowork" OR "actively looking" OR "seeking opportunities" OR "immediate joiner")'
OPEN_TO_WORK_GH_CLAUSE = '("available for hire" OR "seeking opportunities" OR "open to work")'


def is_open_to_work_query(query: str) -> bool:
    """Checks if the query already explicitly mentions Open to Work terminology."""
    if not query:
        return False
    clean = query.lower()
    return any(term in clean for term in ["open to work", "#opentowork", "opentowork", "open_to_work", "open-to-work", "actively looking", "immediate joiner"])


def build_search_dorks(
    query: str,
    target_count: int = 10,
    mode: str = "linkedin",
    require_open_to_work: bool = True
) -> List[str]:
    """
    Generates an array of multi-angle Google search dorks tailored to either:
    - User's raw Boolean query (preserving exact logic).
    - Automatically expanded domain/technology taxonomy.

    If require_open_to_work is True (default), injects Open to Work keywords
    so Google/Serper only returns candidates actively seeking employment.
    """
    clean_q = query.strip()
    is_boolean = is_raw_boolean_query(clean_q)
    dorks: List[str] = []

    already_has_otw = is_open_to_work_query(clean_q)
    if require_open_to_work and not already_has_otw:
        otw_clause = f" {OPEN_TO_WORK_DORK_CLAUSE}" if mode == "linkedin" else f" {OPEN_TO_WORK_GH_CLAUSE}"
    else:
        otw_clause = ""

    if mode == "linkedin":
        base_prefix = "site:linkedin.com/in/"
        negatives = "-inurl:dir -inurl:jobs -inurl:company -inurl:pulse"
    else:
        base_prefix = "site:github.com"
        negatives = "-inurl:orgs -inurl:repositories -inurl:stars"

    # US Regional Clusters to expand search recall
    us_regions = [
        '"USA" OR "United States"',
        '"California" OR "Texas" OR "New York" OR "Washington"',
        '"Virginia" OR "Maryland" OR "Washington DC" OR "Florida" OR "North Carolina"',
        '"Illinois" OR "Massachusetts" OR "Georgia" OR "Colorado" OR "Ohio"',
        '"San Francisco" OR "Austin" OR "Seattle" OR "Boston" OR "New York City"'
    ]

    if is_boolean:
        logger.info(f"[QueryBuilder] Detected raw Boolean search query: {clean_q} (require_open_to_work={require_open_to_work})")
        # Build core query with geographic pivoting
        for region in us_regions:
            dorks.append(f"{base_prefix} ({clean_q}){otw_clause} ({region}) {negatives}")
        # Add broad baseline
        dorks.append(f"{base_prefix} ({clean_q}){otw_clause} {negatives}")
        return dorks

    # Standard query: Perform automatic domain and technology expansion
    logger.info(f"[QueryBuilder] Expanding domain/technology query: '{clean_q}' (require_open_to_work={require_open_to_work})")
    expansion = role_expansion.classify_and_expand_query(clean_q)
    classification = expansion.get("classification", "DOMAIN")
    category = expansion.get("category", "GENERAL")
    tech_constraint = expansion.get("tech_constraint")
    expanded_titles = expansion.get("expanded_list", [])

    # Group expanded titles into compound OR chunks of 3-4 roles
    chunk_size = 3
    role_chunks = [
        expanded_titles[i:i + chunk_size]
        for i in range(0, len(expanded_titles), chunk_size)
    ]

    for chunk in role_chunks:
        if not chunk:
            continue
        role_or_group = " OR ".join([f'"{r}"' for r in chunk])
        role_expression = f"({role_or_group})"

        if tech_constraint and tech_constraint.lower() not in role_or_group.lower():
            combined_tech_role = f'"{tech_constraint}" {role_expression}'
        else:
            combined_tech_role = role_expression

        # Distribute across regions for deep candidate discovery
        for region in us_regions[:3]:
            dorks.append(f"{base_prefix} {combined_tech_role}{otw_clause} ({region}) {negatives}")

    # Fallback / baseline dork
    dorks.append(f'{base_prefix} "{clean_q}"{otw_clause} ("USA" OR "United States") {negatives}')
    return list(dict.fromkeys(dorks))


def prompt_interactive_query() -> Tuple[str, int, str]:
    """
    Prompts the user interactively via console when CLI arguments are omitted.
    """
    print("\n" + "=" * 70)
    print("      PROFILE SCRAPING AGENT — RECRUITMENT SOURCING SETUP")
    print("=" * 70)
    print("You can enter:")
    print("  • A simple job role or technology (e.g. 'IAM Engineer', 'Python')")
    print("  • OR a full Boolean query (e.g. '(\"SailPoint\" OR \"CyberArk\") AND \"Architect\"')")
    print("  • Target Filter: STRICTLY OPEN TO WORK CANDIDATES ONLY\n")

    user_query = input("Enter Role, Domain, or Boolean Query: ").strip()
    while not user_query:
        user_query = input("Query cannot be empty. Please enter a role or Boolean string: ").strip()

    count_str = input("\nEnter target candidate count [default: 10]: ").strip()
    try:
        target_count = int(count_str) if count_str else 10
    except ValueError:
        target_count = 10

    mode_str = input("\nEnter sourcing mode [linkedin / github, default: linkedin]: ").strip().lower()
    mode = "github" if mode_str == "github" else "linkedin"

    print("\n" + "-" * 70)
    print(f"Configured: Query='{user_query}', Target Count={target_count}, Mode={mode}, Filter=OPEN_TO_WORK_ONLY")
    print("-" * 70 + "\n")

    return user_query, target_count, mode


def repair_cli_argv(raw_args: List[str]) -> List[str]:
    """
    Intelligently recovers and recombines Boolean or multi-word search queries
    that get split across whitespace by Windows Command Prompt (cmd.exe) when single
    quotes are used.
    """
    if not raw_args or any(a in raw_args for a in ("-h", "--help")):
        return raw_args

    flags: List[str] = []
    positional: List[str] = []
    i = 0
    while i < len(raw_args):
        arg = raw_args[i]
        if arg in ("--mode", "--profile-url"):
            flags.append(arg)
            if i + 1 < len(raw_args):
                flags.append(raw_args[i + 1])
                i += 2
                continue
            i += 1
        elif arg.startswith("-"):
            flags.append(arg)
            i += 1
        else:
            positional.append(arg)
            i += 1

    if len(positional) <= 2:
        cleaned_pos = []
        for p in positional:
            if not p.isdigit():
                if p.startswith("'") and p.endswith("'"):
                    cleaned_pos.append(p[1:-1].strip())
                elif p.startswith("'"):
                    cleaned_pos.append(p.lstrip("'").strip())
                elif p.endswith("'"):
                    cleaned_pos.append(p.rstrip("'").strip())
                else:
                    cleaned_pos.append(p)
            else:
                cleaned_pos.append(p)
        return cleaned_pos + flags

    last_arg = positional[-1]
    if last_arg.isdigit():
        num_arg = last_arg
        query_parts = positional[:-1]
    else:
        num_arg = None
        query_parts = positional

    recombined_query = " ".join(query_parts).strip()
    if recombined_query.startswith("'") and recombined_query.endswith("'"):
        recombined_query = recombined_query[1:-1].strip()
    elif recombined_query.startswith("'"):
        recombined_query = recombined_query.lstrip("'").strip()
    elif recombined_query.endswith("'"):
        recombined_query = recombined_query.rstrip("'").strip()

    result = [recombined_query]
    if num_arg is not None:
        result.append(num_arg)
    return result + flags
