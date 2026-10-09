# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.

# Size limits. Per-file limits are measured in decoded bytes (a base64 data: URI is
# decoded first), so "10 MB" means the same thing for a PDF as for a .py file.
# Every layer that caps request size (nginx client_max_body_size, Django's
# DATA_UPLOAD_MAX_MEMORY_SIZE, the UI's pre-checks via /system/uploadLimits/) derives
# from these constants — change them here, nowhere else.
MAX_FILE_SIZE = 10 * 1024 * 1024       # 10MB — upload limit for submission files
MAX_ASSIGNMENT_FILE_SIZE = MAX_FILE_SIZE  # 10MB — assignment starter/test files (bigger inputs go in datasets)
# Inline-JSON submissions carry every file in one body, base64-inflated (~4/3) for
# binaries: 30 MiB decoded is ~40 MiB on the wire, safely under MAX_REQUEST_BODY_BYTES.
MAX_SUBMISSION_TOTAL_SIZE = 30 * 1024 * 1024  # 30MB — all files in one student submission
MAX_OUTPUT_SIZE = 1024 * 1024           # 1MB  — stdout/stderr cap from container execution
MAX_DATASET_SIZE = 1024 * 1024 * 1024   # 1GB  — upload limit for assignment datasets
MAX_COURSE_FILE_SIZE = 25 * 1024 * 1024  # 25MB — upload limit for course files (stored as DB base64)
MAX_QUIZ_IMAGE_SIZE = 5 * 1024 * 1024    # 5MB  — quiz question images (multipart)
# Whole-request cap for JSON bodies: Django's DATA_UPLOAD_MAX_MEMORY_SIZE and nginx's
# client_max_body_size (nginx.conf here and deploy/proxy.conf.template in the codePost
# repo) must all equal this. Multipart file bytes (datasets, QTI, images) don't count.
MAX_REQUEST_BODY_BYTES = 50 * 1024 * 1024  # 50MB
MAX_QTI_IMPORT_BYTES = 50 * 1024 * 1024  # 50MB — upload limit for a QTI / Common Cartridge export
# Total inflated XML a QTI import will decompress across all members — a decompression-bomb
# guard (a small zip can expand to gigabytes of XML). Only .xml members are read.
MAX_QTI_UNCOMPRESSED_BYTES = 200 * 1024 * 1024  # 200MB

# Anti-hardcoding variant reruns (AssignmentDataSet.autogradeAllVariants): rerun a finalized
# submission against at most this many OTHER variants (a random sample), rather than every
# variant in the pool — the pool can be up to MAX_SPLIT_CHUNKS (200), and a sample gives
# strong hardcoding signal without one full container run per variant per submission.
DATASET_VARIANT_RERUN_SAMPLE_SIZE = 5

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
