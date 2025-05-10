# LeetCode Problem Sorter (Calculated Difficulty)

Sorts LeetCode problems by a calculated difficulty score based on multiple factors, not just LeetCode's assigned difficulty.

## Features

*   Fetches LeetCode problem data (with caching).
*   Calculates a composite difficulty score considering:
    *   LeetCode's assigned difficulty (Easy, Medium, Hard).
    *   Acceptance rate.
    *   Total accepted solutions.
    *   Total submissions (popularity).
    *   Problem newness.
*   Outputs the top N problems to console and all sorted problems to a CSV.

## How it Works

A base score from LeetCode's difficulty is modified by weighted factors like acceptance rate, solve counts, popularity, and newness. Weights are configurable in the script.

## Prerequisites

*   Python 3.x
*   `requests` library

## Setup & Usage

1.  **Clone:** `git clone https://github.com/Bumblebee202111/leetcode-difficulty-sorter.git && cd leetcode-difficulty-sorter`
2.  **Install:** `pip install requests`
3.  **Run:** `python leetcode_sorter.py`

    Output: Console summary & `leetcode_sorted_problems.csv`.
    Cache: `leetcode_problems_cache.json` is used for faster subsequent runs.

## Configuration

Adjust scoring logic by modifying `DIFFICULTY_SCORE_BASE_MAP` and `WEIGHTS` dictionaries at the top of `leetcode_sorter.py`.

## Disclaimer

Uses LeetCode API; use responsibly. API changes may break the script. This script was developed with AI assistance.
