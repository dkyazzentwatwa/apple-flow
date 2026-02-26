## 2025-02-17 - [AppleScript Ingress Optimization]
**Learning:** In AppleScript, iterating over large strings character-by-character (e.g., for JSON escaping) is extremely slow and can block the main daemon loop. Using `text item delimiters` to perform bulk replacements and switching to tab-delimited output for communication with Python is orders of magnitude faster.
**Action:** Always prefer tab-delimited output and bulk string sanitization in AppleScript handlers for data extraction.
