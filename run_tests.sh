PYTHONPATH=. python -m pytest tests \
    --cov jsonlitedb \
    --cov tests \
    --cov-report term \
    --cov-report html
