import os

from dotenv import load_dotenv

import reflex as rx

# Charge .env en local ; sur Reflex Cloud, DATABASE_URL est deja
# dans l'environnement (variable configuree sur le dashboard).
load_dotenv()

config = rx.Config(
    app_name="pdc_swim",
    app_title="PdC Swim",
    db_url=os.environ.get("DATABASE_URL"),
    # Tous les champs pilotes par on_change ont desormais un setter explicite
    # dans State (voir pdc_swim.py) - plus besoin des setters auto-generes.
    state_auto_setters=False,
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
    ]
)