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
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
    ]
)