rm ../db.sqlite3

python3 ../manage.py makemigrations core
python3 ../manage.py migrate

python3 ../manage.py shell < ../util/db_push_to_codepost_script.py
