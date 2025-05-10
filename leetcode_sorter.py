import requests
import json
import os
import time
import math
import csv

# --- Configuration ---
CACHE_FILE = "leetcode_problems_cache.json" # Cache filename for API responses
CACHE_EXPIRY_DAYS = 1  # How old the cache can be before refreshing
OUTPUT_CSV_FILE = "leetcode_sorted_problems.csv" # Output filename for sorted problems
LEETCODE_PROBLEMS_ALL_URL = "https://leetcode.com/api/problems/all/" # API endpoint

# --- SCORING SYSTEM ---

# 1. Base scores for LeetCode's difficulty categories.
# These establish initial tiers; modifiers can shift problems across them.
DIFFICULTY_SCORE_BASE_MAP = {
    "Easy": 80,
    "Medium": 200,
    "Hard": 450
}

# 2. Weights for modifier factors.
# These are applied to normalized 0-1 values of various problem statistics.
WEIGHTS = {
    # acceptance_rate_impact: Applied to (1.0 - acceptanceRate).
    # Higher value means lower acceptance rate significantly increases score.
    "acceptance_rate_impact": 300,

    # low_total_accepted_penalty: Applied to (1.0 - log_norm_total_accepted).
    # Increases score for problems with very few absolute solves.
    "low_total_accepted_penalty": 150,

    # high_popularity_discount: Applied to log_norm_total_submissions (value is negative).
    # Decreases score for very popular problems (assumed more resources available).
    "high_popularity_discount": -80,

    # newness_premium: Applied to norm_frontend_id.
    # Increases score for newer problems (assumed more novel or less discussed).
    "newness_premium": 70,
}

# Mapping from LeetCode API's numeric difficulty to string representation.
DIFFICULTY_API_MAP = {
    1: "Easy",
    2: "Medium",
    3: "Hard"
}

# --- Helper Functions ---

def fetch_problems_from_api_rest():
    """Fetches all problem data from the LeetCode REST API."""
    print(f"Fetching problems from LeetCode API: {LEETCODE_PROBLEMS_ALL_URL}")
    try:
        headers = { # Standard headers to mimic a browser request
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Referer': 'https://leetcode.com/problemset/all/', # Referer can sometimes be important
        }
        response = requests.get(LEETCODE_PROBLEMS_ALL_URL, headers=headers)
        response.raise_for_status() # Raises HTTPError for bad responses (4XX or 5XX)
        data = response.json()
        if "stat_status_pairs" in data: # Main list of problems
            return data["stat_status_pairs"]
        print("API response structure unexpected: 'stat_status_pairs' not found.")
        return None
    except requests.exceptions.RequestException as e:
        print(f"API request failed: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"Failed to parse API response JSON: {e}")
        return None

def load_problems_from_cache():
    """Loads problems from a local cache file if it exists and is not expired."""
    if os.path.exists(CACHE_FILE):
        cache_mod_time = os.path.getmtime(CACHE_FILE)
        # Check if cache is within expiry period
        if (time.time() - cache_mod_time) < (CACHE_EXPIRY_DAYS * 24 * 60 * 60):
            print(f"Loading problems from cache: {CACHE_FILE}")
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            print("Cache expired.")
    return None

def save_problems_to_cache(problems):
    """Saves the fetched problem data to a local cache file."""
    print(f"Saving {len(problems)} problems to cache: {CACHE_FILE}")
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(problems, f, indent=2) # Indent for readability

def process_problems(raw_problems_list):
    """
    Filters and transforms raw problem data into a structured format.
    Also collects maximum values for normalization purposes.
    """
    processed = []
    if not raw_problems_list:
        return [], 0, 0, 0 # problems, max_id, max_subs, max_acs

    max_frontend_id = 0
    max_submissions = 0
    max_accepted = 0

    for prob_data in raw_problems_list:
        stat = prob_data.get('stat')
        difficulty_info = prob_data.get('difficulty')

        if not stat or not difficulty_info: continue # Skip if essential data blocks are missing
        if prob_data.get('paid_only', False): continue # Skip paid problems

        try:
            frontend_id = int(stat.get('frontend_question_id', 0))
            title = stat.get('question__title', 'N/A')
            slug = stat.get('question__title_slug', 'N/A')
            total_accepted_val = int(stat.get('total_acs', 0))
            total_submitted_val = int(stat.get('total_submitted', 0))
            difficulty_level = int(difficulty_info.get('level', 0)) # 1:E, 2:M, 3:H

            # Skip if core identifiers or difficulty are missing/invalid
            if slug == 'N/A' or frontend_id == 0 or difficulty_level == 0: continue

            acceptance_rate = (total_accepted_val / total_submitted_val) if total_submitted_val > 0 else 0.0
            difficulty_str = DIFFICULTY_API_MAP.get(difficulty_level, "Unknown")
            if difficulty_str == "Unknown": continue # Skip if difficulty level is not recognized

            processed.append({
                "id": frontend_id,
                "title": title,
                "slug": slug,
                "difficulty": difficulty_str,
                "totalAccepted": total_accepted_val,
                "totalSubmissions": total_submitted_val,
                "acceptanceRate": acceptance_rate,
                "url": f"https://leetcode.com/problems/{slug}/"
            })

            # Update max values for normalization
            max_frontend_id = max(max_frontend_id, frontend_id)
            max_submissions = max(max_submissions, total_submitted_val)
            max_accepted = max(max_accepted, total_accepted_val)

        except (TypeError, ValueError) as e: # Catch potential errors during data conversion
            print(f"Warning: Data parsing error for problem '{stat.get('question__title_slug', 'Unknown')}': {e}")
            continue
    
    # Ensure max values are at least 1 to prevent division by zero during normalization
    return processed, max(1, max_frontend_id), max(1, max_submissions), max(1, max_accepted)

def calculate_true_difficulty_score(problem, max_frontend_id, max_submissions_log, max_accepted_log):
    """Calculates a composite 'true difficulty' score for a given problem."""
    score = 0.0

    # 1. Base Score from LeetCode's Stated Difficulty
    score += DIFFICULTY_SCORE_BASE_MAP.get(problem['difficulty'], 0)

    # --- Modifier Factors ---

    # 2. Acceptance Rate Impact: (1.0 - acceptanceRate) gives 0 for 100% acc, 1 for 0% acc.
    acceptance_factor = (1.0 - problem['acceptanceRate'])
    score += acceptance_factor * WEIGHTS["acceptance_rate_impact"]

    # 3. Low Total Accepted Penalty: Penalizes problems solved by very few.
    #    Uses log1p for normalization to handle 0 counts and dampen large values.
    if problem['totalAccepted'] >= 0 and max_accepted_log > 0:
        # log_norm_accepted is ~0 for 0 solves, approaches 1 for max solves.
        log_norm_accepted = math.log1p(problem['totalAccepted']) / max_accepted_log
        # low_accepted_factor is ~1 for 0 solves, approaches 0 for max solves.
        low_accepted_factor = (1.0 - log_norm_accepted)
        score += low_accepted_factor * WEIGHTS["low_total_accepted_penalty"]

    # 4. High Popularity (Total Submissions) Discount: Reduces score for highly submitted problems.
    #    WEIGHTS["high_popularity_discount"] is negative.
    if problem['totalSubmissions'] > 0 and max_submissions_log > 0:
        # log_norm_submissions is ~0 for 0 subs, approaches 1 for max subs.
        log_norm_submissions = math.log1p(problem['totalSubmissions']) / max_submissions_log
        score += log_norm_submissions * WEIGHTS["high_popularity_discount"]

    # 5. Newness Premium: Adds a premium for newer problems.
    #    Normalized problem ID (0 for oldest, 1 for newest approx).
    if max_frontend_id > 0 :
        norm_id = problem['id'] / max_frontend_id
        score += norm_id * WEIGHTS["newness_premium"]
    
    problem['trueDifficultyScore'] = round(score, 2) # Store the calculated score
    return problem

# --- Main Execution Logic ---
def main():
    print("LeetCode Problem Sorter by True Difficulty")
    print("=" * 40)

    # Attempt to load problems from cache first
    raw_problems_list = load_problems_from_cache()
    if not raw_problems_list: # If cache miss or expired
        fetched_data = fetch_problems_from_api_rest()
        if fetched_data:
            save_problems_to_cache(fetched_data)
            raw_problems_list = fetched_data
        else:
            print("Failed to fetch problems and no cache available. Exiting.")
            return

    if not raw_problems_list: # Should not happen if fetch was successful
        print("No problem data found. Exiting.")
        return

    print(f"Processing {len(raw_problems_list)} raw problem entries...")
    problems, max_id, max_subs, max_acs = process_problems(raw_problems_list)
    
    if not problems: # If all problems were filtered out (e.g., all paid)
        print("No processable problems found. Exiting.")
        return
        
    print(f"Filtered to {len(problems)} free, valid problems.")
    print(f"Max ID: {max_id}, Max Submissions: {max_subs:,}, Max Accepted: {max_acs:,}")

    # Pre-calculate log of max values for normalization (used in score calculation)
    # math.log1p(x) is log(1+x), good for values that can be 0.
    max_submissions_log_val = math.log1p(max_subs) if max_subs > 0 else 1.0
    max_accepted_log_val = math.log1p(max_acs) if max_acs > 0 else 1.0

    # Calculate true difficulty score for each problem
    scored_problems = []
    for problem in problems:
        scored_problems.append(calculate_true_difficulty_score(
            problem, max_id, max_submissions_log_val, max_accepted_log_val
        ))

    # Sort problems by the calculated score in descending order (hardest first)
    sorted_problems = sorted(scored_problems, key=lambda p: p['trueDifficultyScore'], reverse=True)

    # --- Output Results ---
    print("\n--- Top 20 Hardest Problems (Calculated Score) ---")
    # Header for console output
    print(f"{'ID':<5} | {'Title':<40} | {'LDiff':<6} | {'Acc%':<5} | {'Subs(k)':<7} | {'Acs(k)':<7} | {'Score':<8}")
    print("-" * 100) # Separator line
    for p in sorted_problems[:20]: # Display top 20
        acc_rate_str = f"{p['acceptanceRate']*100:.1f}"
        subs_str = f"{p['totalSubmissions']/1000:.1f}" # Submissions in thousands
        acs_str = f"{p['totalAccepted']/1000:.1f}"     # Accepted in thousands
        print(f"{p['id']:<5} | {p['title'][:38]:<40} | {p['difficulty']:<6} | {acc_rate_str:<5} | {subs_str:<7} | {acs_str:<7} | {p['trueDifficultyScore']:<8.2f}")

    # Export all sorted problems to a CSV file
    if OUTPUT_CSV_FILE:
        print(f"\nExporting {len(sorted_problems)} sorted problems to {OUTPUT_CSV_FILE}...")
        fieldnames = [ # Define CSV column headers
            'id', 'title', 'difficulty', 'acceptanceRate',
            'totalAccepted', 'totalSubmissions', 'trueDifficultyScore', 'url'
        ]
        try:
            with open(OUTPUT_CSV_FILE, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                for p_dict in sorted_problems:
                    # Prepare a row dictionary, ensuring only specified fieldnames are written
                    row_to_write = {key: p_dict.get(key) for key in fieldnames}
                    # Format acceptance rate for CSV
                    if isinstance(row_to_write['acceptanceRate'], (float, int)):
                         row_to_write['acceptanceRate'] = f"{row_to_write['acceptanceRate']*100:.2f}%"
                    writer.writerow(row_to_write)
            print(f"Successfully exported to {OUTPUT_CSV_FILE}")
        except IOError as e:
            print(f"Error writing CSV file: {e}")
        except Exception as e: # Catch any other unexpected errors during export
            print(f"An unexpected error occurred during CSV export: {e}")

    print("\nDone.")

if __name__ == "__main__":
    main()