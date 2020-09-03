pybabel extract -F babel.cfg -o messages.pot .
# pybabel init -i messages.pot -d translations -l ru
# pybabel init -i messages.pot -d translations -l en
pybabel update -i messages.pot -d translations -l ru
pybabel update -i messages.pot -d translations -l en
pause