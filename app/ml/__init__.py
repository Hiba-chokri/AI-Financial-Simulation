"""
Dataset-agnostic ML pipeline for the GDV (price/m2) valuation.

The workflow is fixed (ingest -> validate -> clean/feature-engineer -> split ->
train N models -> evaluate -> tune -> persist -> predict); only the *config*
(app/ml/config.py) changes when the dataset changes. This lets us swap the
current Kaggle data for scraped data later without touching the pipeline code.
"""
