# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
import hashlib
import re

class MockFile:
    def __init__(self, name, data, extension=None):
        self.name = name
        self.data = data
        self.extension = extension
        self.code = None # deprecated
    
    def save(self):
        # Infer extension
        if not self.extension:
            match = re.search(r'(\.[^.]+)$', self.name)
            if match:
                self.extension = match.group(1).lstrip('.') # lstrip to match usual behavior if any, but let's assume it grabs .pdf
            
        
        # --- LOGIC FROM models.py ---
        # Normalize newlines, but only for text files
        BINARY_EXTENSIONS = ['pdf', 'png', 'jpg', 'jpeg', 'ipynb']
        # Note: self.extension usually doesn't have dot if passed directly, or does if parsed?
        # In models.py: extension = match.group(1) which includes dot (e.g. '.pdf')
        # So 'pdf' check needs to handle dot or not.
        # models.py logic: self.extension.lower().endswith(ext)
        # if ext is 'pdf', endswith('pdf') works for 'file.pdf' but not '.pdf' unless normalized.
        # Wait, regex match.group(1) on 'file.pdf' returns '.pdf'.
        # '.pdf'.endswith('pdf') is True.
        
        if not any(self.extension.lower().endswith(ext) for ext in BINARY_EXTENSIONS):
            if '\\r\\n' in self.data:
                self.data = self.data.replace("\\r\\n", "\\n")
        
        # Ensure utf-8 encoding (base64 is ascii safe)
        self.data = self.data.encode('utf-8').decode('utf-8')
        self.hash = hashlib.sha256(self.data.encode('utf-8')).hexdigest()
        # ----------------------------
        
        return self.data

# Test Data
pdf_data_base64 = "JVBERi0xLjYNJeLjz9MNCjEwIDAgb2Jj..." # Contains \r\n (encoded as text it might appear?)
# Actually base64 string itself shouldn't contain escaped \r\n unless it's a string literal in code.
# But if it does (e.g. from a POST body where newlines are literal \r\n), we want to preserve them if they are part of the base64 structure or just let them be.
# Wait, base64 ignores whitespace usually.
# However, if the CONTENT of the file (before base64) had newlines, base64 encodes them safely.
# If the base64 STRING itself has newlines, replacing them might corrupt the base64 string if not done carefully?
# Actually, replacing \r\n in base64 string with \n is fine for base64 decoders (they ignore whitespace).
# BUT, if we have a PDF file that ISN'T base64 encoded (uploaded as raw text/bytes but models.py thinks it's text),
# modifying bytes \r\n (0D 0A) to \n (0A) corrupts the PDF xref table byte offsets.
# THAT is the real danger.
# If the frontend sends base64, it's an ASCII string. Replacing \r\n with \n in the base64 string is HARMLESS.
# BUT, if the user uploads a PDF *content* directly (e.g. raw string via API), we must NOT touch it.
# The user's request is "id like to files to be able to have base64 data in there data as well as what were doing right now".
# So they want to store base64 in the `data` field.
# If they store base64, newline replacement is harmless.
# HOWEVER, if they upload a "text" file like code, we WANT replacement.
# If they upload a PDF, they might upload it as... what?
# If effectively we want to support PDF rendering, we assume the `data` field contains something the frontend can render.
# If frontend uses `react-pdf`, it takes base64.
# So `data` = base64 string.
# Is there ANY harm in replacing `\r\n` linked to `\n` in a base64 string?
# Base64 strings use `\r\n` for line wrapping (MIME). Removing `\r` is generally fine.
# But why take the risk?
# And crucially, if we identify it as a BINARY file (pdf), we shouldn't act like it's text we need to normalize.
# So avoiding the replace is correct principle.

test_data = "Line1\\r\\nLine2"
file_pdf = MockFile("test.pdf", test_data, ".pdf")
output_pdf = file_pdf.save()
print(f"PDF Output (Should denote '\\r\\n'): {repr(output_pdf)}")

file_txt = MockFile("test.txt", test_data, ".txt")
output_txt = file_txt.save()
print(f"TXT Output (Should denote '\\n'): {repr(output_txt)}")

assert output_pdf == "Line1\\r\\nLine2"
assert output_txt == "Line1\\nLine2"
print("Verification Successful")
