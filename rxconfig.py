import reflex as rx

config = rx.Config(
    app_name="pdc_swim",
    app_title="PdC Swim",
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
    ]
)