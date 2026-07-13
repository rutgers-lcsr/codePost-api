# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
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
        # Note: self.extension usually doesn't have dot if passed directly, or does if parsed?
        # In models.py: extension = match.group(1) which includes dot (e.g. '.pdf')
        # So 'pdf' check needs to handle dot or not.
        # models.py logic: self.extension.lower().endswith(ext)
        # if ext is 'pdf', endswith('pdf') works for 'file.pdf' but not '.pdf' unless normalized.
        # Wait, regex match.group(1) on 'file.pdf' returns '.pdf'.
        # '.pdf'.endswith('pdf') is True.
        
        if not self.data.startswith('data:'):
            if '\\r\\n' in self.data:
                self.data = self.data.replace("\\r\\n", "\\n")
        
        # Ensure utf-8 encoding (base64 is ascii safe)
        self.data = self.data.encode('utf-8').decode('utf-8')
        self.hash = hashlib.sha256(self.data.encode('utf-8')).hexdigest()
        # ----------------------------
        
        return self.data

# Test Data
pdf_data_base64 = "JVBERi0xLjYNJeLjz9MNCjEwIDAgb2Jj..." # Contains \r\n (encoded as text it might appear?)


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
