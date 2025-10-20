# c̵̺͕̦͐̾̔ó̸̦̙̝̈́́d̵̡̢͉̈́̚͠e̴̡̝̼̔̕͘P̵̡̟͑̈́ó̸̞͙̓͜s̵̢͙̝͆̾͝ț̵̙̓̿͐ A̴̙̘̐͛̈́P̸̟̺͉͆͑̓I̵̡̼̾̈́!

# todo, Update versions

cgi - was removed, quick fix: install legacy-cgi in python >3.12

# Setup

# 1. Clone the repository

# 2. Install the requirements: `pip install poetry && poetry install`

# 3. Create a `.env` file with the following content:

# ```

# DEBUG=TRUE

# SECRET_KEY=your_secret_key

# DB_HOST=your_DB_host

# DB_PORT=your_DB_port

# DB_DB_NAME=your_DB_db_name

# DB_USER=your_DB_user

# DB_PASSWORD=your_DB_password

# LOKI_URL=http://localhost:3100

# ```

# 4. Create static files: `python manage.py collectstatic`

# 5. Add environment variables to for api user:

# ```

# export API_USER=your_api_user

# export API_PASSWORD=your_api_password

# ```

# 6. Run the server: `./init.sh python manage.py runserver`


Update readme to cause a commit to happen
