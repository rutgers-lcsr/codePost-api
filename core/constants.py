# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial Licensed, included with this software.

# Extensions whose file data is stored as base64 and should skip text normalization
# (e.g. CRLF -> LF conversion). Used in File.save(), encoded_zip(), and download handlers.
# This is the single source of truth — do not duplicate this list elsewhere.
BINARY_EXTENSIONS = ['pdf', 'png', 'jpg', 'jpeg', 'db']

# Size limits
MAX_FILE_SIZE = 10 * 1024 * 1024       # 10MB — upload limit for submission files
MAX_OUTPUT_SIZE = 1024 * 1024           # 1MB  — stdout/stderr cap from container execution
MAX_DATASET_SIZE = 1024 * 1024 * 1024   # 1GB  — upload limit for assignment datasets

# External service default URLs
DEFAULT_OLLAMA_URL = 'http://localhost:11434'
DEFAULT_PORTKEY_URL = 'https://api.portkey.ai/v1'

# Extensions for non-code files — used to skip files during language detection,
# requirements scanning, and main-file scoring. Stored without leading dots;
# consumers that need dotted variants should derive them.
NON_CODE_EXTENSIONS = {
    'pdf', 'txt', 'log', 'csv', 'tsv',
    'png', 'jpg', 'jpeg', 'gif', 'bmp', 'svg', 'webp',
    'zip', 'tar', 'gz', 'rar',
    'docx', 'xlsx', 'pptx', 'doc', 'xls',
    'md', 'rst',
    'db',
}
