# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
rm ../db.sqlite3

python3 ../manage.py makemigrations core
python3 ../manage.py migrate

python3 ../manage.py shell < ../util/db_push_to_codepost_script.py
