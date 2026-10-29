import sys
from pathlib import Path
from playwright.sync_api import sync_playwright
d = Path(sys.argv[1])
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    for name in sys.argv[2:]:
        pg = b.new_page(device_scale_factor=2, viewport={"width": 1800, "height": 1000})
        pg.goto((d / f"{name}.html").as_uri())
        pg.locator("#root").screenshot(path=str(d / f"{name}.png"))
    b.close()
