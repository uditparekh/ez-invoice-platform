from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

from PIL import Image, ImageDraw, ImageFont


OUT_DIR = Path(__file__).resolve().parent

COLORS = {
    "ink": "#08111F",
    "indigo": "#4F46E5",
    "indigo_2": "#6366F1",
    "cyan": "#06B6D4",
    "cyan_soft": "#67E8F9",
    "cloud": "#F8FAFC",
    "card": "#FFFFFF",
    "border": "#E6EAF2",
    "slate": "#667085",
    "muted": "#98A2B3",
    "dark_bg": "#070B15",
    "dark_card": "#0B1020",
    "dark_surface": "#111827",
    "dark_border": "#202A46",
    "dark_text": "#F8FAFC",
    "dark_muted": "#A5B4C8",
    "green": "#16A34A",
    "green_bg": "#DCFCE7",
    "amber": "#D97706",
    "amber_bg": "#FEF3C7",
    "red": "#DC2626",
    "red_bg": "#FEE2E2",
}

FONT_REGULAR = "/System/Library/Fonts/Supplemental/Arial.ttf"
FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
FONT_BLACK = "/System/Library/Fonts/Supplemental/Arial Black.ttf"


def font(size: int, weight: str = "regular") -> ImageFont.FreeTypeFont:
    path = FONT_BLACK if weight == "black" else FONT_BOLD if weight == "bold" else FONT_REGULAR
    return ImageFont.truetype(path, size)


def rounded(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    radius: int,
    fill: str,
    outline: str | None = None,
    width: int = 1,
) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    value: str,
    size: int,
    fill: str,
    weight: str = "regular",
    anchor: str | None = None,
) -> None:
    draw.text(xy, value, font=font(size, weight), fill=fill, anchor=anchor)


def pill(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    label: str,
    fg: str,
    bg: str,
    w: int | None = None,
) -> None:
    x, y = xy
    tw = int(draw.textlength(label, font=font(15, "bold")))
    width = w or tw + 32
    rounded(draw, (x, y, x + width, y + 34), 17, bg)
    text(draw, (x + width // 2, y + 17), label, 15, fg, "bold", anchor="mm")


def logo(draw: ImageDraw.ImageDraw, x: int, y: int, dark: bool = False) -> None:
    rounded(draw, (x, y, x + 46, y + 46), 12, COLORS["indigo"])
    text(draw, (x + 23, y + 23), ">", 30, COLORS["cyan_soft"], "black", anchor="mm")
    text(draw, (x + 60, y + 13), "Sift", 25, COLORS["dark_text"] if dark else COLORS["ink"], "black")
    text(draw, (x + 112, y + 13), "Entry", 25, COLORS["cyan"] if dark else COLORS["indigo"], "black")


def line(draw: ImageDraw.ImageDraw, xy: tuple[int, int, int, int], fill: str, width: int = 1) -> None:
    draw.line(xy, fill=fill, width=width)


def draw_sidebar(draw: ImageDraw.ImageDraw, dark: bool, active: str = "Inbox") -> None:
    bg = COLORS["dark_card"] if dark else COLORS["card"]
    border = COLORS["dark_border"] if dark else COLORS["border"]
    fg = COLORS["dark_text"] if dark else COLORS["ink"]
    muted = COLORS["dark_muted"] if dark else COLORS["slate"]
    active_bg = "#111B35" if dark else "#EEF2FF"
    active_fg = COLORS["cyan_soft"] if dark else COLORS["indigo"]
    draw.rectangle((0, 0, 260, 920), fill=bg)
    line(draw, (259, 0, 259, 920), border)
    logo(draw, 30, 30, dark)
    text(draw, (30, 126), "WORKFLOW", 12, COLORS["muted"], "bold")
    items = ["Inbox", "Review", "Approvals", "Posted", "Exceptions"]
    y = 158
    for item in items:
        is_active = item == active
        if is_active:
            rounded(draw, (20, y - 8, 238, y + 40), 12, active_bg)
            draw.rectangle((20, y - 8, 24, y + 40), fill=active_fg)
        text(draw, (42, y + 7), item[:2].upper(), 11, active_fg if is_active else muted, "bold")
        text(draw, (76, y + 4), item, 17, active_fg if is_active else fg, "bold")
        y += 56
    text(draw, (30, y + 20), "ACCOUNTING", 12, COLORS["muted"], "bold")
    for item in ["Tally", "QuickBooks", "Zoho Books", "SAP"]:
        y += 54
        text(draw, (42, y + 7), item[:2].upper(), 11, muted, "bold")
        text(draw, (76, y + 4), item, 17, fg, "bold")
    text(draw, (30, 842), "Connection health", 13, muted, "bold")
    pill(draw, (30, 868), "Tally live", COLORS["green"], "#052E1B" if dark else COLORS["green_bg"])


def metric_card(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    title: str,
    value: str,
    helper: str,
    dark: bool = False,
    accent: str | None = None,
) -> None:
    card = COLORS["dark_surface"] if dark else COLORS["card"]
    border = COLORS["dark_border"] if dark else COLORS["border"]
    fg = COLORS["dark_text"] if dark else COLORS["ink"]
    muted = COLORS["dark_muted"] if dark else COLORS["slate"]
    rounded(draw, box, 14, card, border)
    x1, y1, _, _ = box
    text(draw, (x1 + 24, y1 + 24), title.upper(), 12, COLORS["muted"], "bold")
    text(draw, (x1 + 24, y1 + 58), value, 34, accent or fg, "black")
    text(draw, (x1 + 24, y1 + 104), helper, 15, muted, "regular")


def draw_header(draw: ImageDraw.ImageDraw, title: str, subtitle: str, dark: bool = False) -> None:
    bg = COLORS["dark_bg"] if dark else COLORS["cloud"]
    border = COLORS["dark_border"] if dark else COLORS["border"]
    fg = COLORS["dark_text"] if dark else COLORS["ink"]
    muted = COLORS["dark_muted"] if dark else COLORS["slate"]
    draw.rectangle((260, 0, 1440, 92), fill=bg)
    line(draw, (260, 91, 1440, 91), border)
    text(draw, (310, 28), title, 30, fg, "black")
    title_width = int(draw.textlength(title, font=font(30, "black")))
    text(draw, (310 + title_width + 10, 34), f"/ {subtitle}", 21, muted, "bold")
    rounded(draw, (775, 24, 1090, 66), 11, COLORS["dark_card"] if dark else COLORS["card"], border)
    text(draw, (800, 35), "Search invoices, vendors, or ledgers", 16, muted)
    rounded(draw, (1112, 24, 1244, 66), 11, COLORS["dark_card"] if dark else COLORS["card"], border)
    text(draw, (1150, 35), "Filter", 16, muted, "bold")
    rounded(draw, (1268, 22, 1392, 68), 12, COLORS["indigo"])
    text(draw, (1330, 45), "Upload", 17, "#FFFFFF", "bold", anchor="mm")


def invoice_queue(dark: bool = False) -> Image.Image:
    bg = COLORS["dark_bg"] if dark else COLORS["cloud"]
    img = Image.new("RGB", (1440, 920), bg)
    draw = ImageDraw.Draw(img)
    draw_sidebar(draw, dark, "Inbox")
    draw_header(draw, "Inbox", "Invoice queue", dark)

    surface = COLORS["dark_bg"] if dark else COLORS["cloud"]
    draw.rectangle((260, 92, 1440, 920), fill=surface)

    cards = [
        ("Uploaded", "42", "PDFs received", None),
        ("Extracted", "39", "93% automation", COLORS["indigo_2"]),
        ("Ready to post", "31", "After validation", COLORS["green"]),
        ("Exceptions", "8", "Need review", COLORS["amber"]),
    ]
    for i, (title, value, helper, accent) in enumerate(cards):
        metric_card(draw, (310 + i * 270, 130, 550 + i * 270, 260), title, value, helper, dark, accent)

    table_card = COLORS["dark_card"] if dark else COLORS["card"]
    border = COLORS["dark_border"] if dark else COLORS["border"]
    fg = COLORS["dark_text"] if dark else COLORS["ink"]
    muted = COLORS["dark_muted"] if dark else COLORS["slate"]
    rounded(draw, (310, 298, 830, 840), 16, table_card, border)
    text(draw, (336, 326), "Invoices to review", 22, fg, "black")
    text(draw, (336, 362), "Newest documents that need accounting confirmation.", 15, muted)
    row_y = 410
    rows = [
        ("2690013015", "Garden Silk Mills Private Limited", "INR 1,267,058", "Ready", COLORS["green"], "#DCFCE7"),
        ("INV-3", "Pragati Enterprises", "INR 567,580", "Validate", COLORS["amber"], COLORS["amber_bg"]),
        ("2620002662", "Madelin Enterprises Private Limited", "INR 633,912", "Posted", COLORS["cyan"], "#CFFAFE"),
        ("MUM000092", "Pawan Chemicals", "INR 445,450", "Review", COLORS["red"], COLORS["red_bg"]),
    ]
    for idx, row in enumerate(rows):
        y = row_y + idx * 96
        if idx == 0:
            rounded(draw, (334, y, 806, y + 78), 12, "#111B35" if dark else "#EEF2FF", "#22345E" if dark else "#C7D2FE")
        text(draw, (356, y + 18), row[0], 20, fg, "black")
        text(draw, (356, y + 48), row[1], 15, muted)
        text(draw, (648, y + 20), row[2], 18, fg, "bold")
        pill(draw, (704, y + 45), row[3], row[4], "#102F38" if dark and row[3] == "Posted" else ("#11271A" if dark else row[5]), 84)

    rounded(draw, (862, 298, 1390, 840), 16, table_card, border)
    text(draw, (892, 326), "Review invoice", 12, COLORS["muted"], "bold")
    text(draw, (892, 366), "2690013015", 42, fg, "black")
    text(draw, (892, 424), "Garden Silk Mills Private Limited", 18, muted, "bold")
    fact_titles = ["Invoice date", "Due date", "Currency", "Total", "Line items", "Target"]
    fact_values = ["25-May-2026", "25-May-2026", "INR", "1,267,058.00", "1", "Tally"]
    for i, (title, value) in enumerate(zip(fact_titles, fact_values)):
        x = 892 + (i % 3) * 160
        y = 474 + (i // 3) * 105
        rounded(draw, (x, y, x + 142, y + 82), 10, COLORS["dark_surface"] if dark else "#FFFFFF", border)
        text(draw, (x + 16, y + 16), title.upper(), 11, COLORS["muted"], "bold")
        text(draw, (x + 16, y + 46), value, 18, fg, "bold")
    line(draw, (892, 700, 1358, 700), border)
    text(draw, (892, 724), "Line items", 22, fg, "black")
    rounded(draw, (892, 766, 1358, 818), 10, COLORS["dark_surface"] if dark else "#FFFFFF", border)
    text(draw, (912, 785), "RMPTA04 (IMPORTED)", 15, fg, "bold")
    text(draw, (1150, 785), "17,319 KG", 15, muted, "bold")
    text(draw, (1278, 785), "INR 1.27M", 15, fg, "bold")
    return img


def analytics_sample(dark: bool = False) -> Image.Image:
    bg = COLORS["dark_bg"] if dark else COLORS["cloud"]
    img = Image.new("RGB", (1440, 920), bg)
    draw = ImageDraw.Draw(img)
    draw_sidebar(draw, dark, "Posted")
    draw_header(draw, "Analytics", "AP performance", dark)
    card = COLORS["dark_card"] if dark else COLORS["card"]
    border = COLORS["dark_border"] if dark else COLORS["border"]
    fg = COLORS["dark_text"] if dark else COLORS["ink"]
    muted = COLORS["dark_muted"] if dark else COLORS["slate"]

    for i, item in enumerate([
        ("Total spend", "INR 12.8M", "58 invoices"),
        ("Posted", "41 / 58", "71% complete"),
        ("Avg processing", "42s", "From upload to ready"),
        ("Exceptions", "8", "4 ledger, 4 tax"),
    ]):
        metric_card(draw, (310 + i * 270, 130, 550 + i * 270, 260), item[0], item[1], item[2], dark, COLORS["cyan"] if i == 1 else None)

    rounded(draw, (310, 300, 860, 590), 16, card, border)
    text(draw, (340, 330), "Spend by vendor", 18, fg, "black")
    vendors = [
        ("Garden Silk Mills", 0.92, "INR 4.6M"),
        ("Madelin Enterprises", 0.62, "INR 3.1M"),
        ("Pawan Chemicals", 0.38, "INR 1.9M"),
    ]
    y = 382
    for name, ratio, amount in vendors:
        text(draw, (340, y), name, 16, muted, "bold")
        rounded(draw, (560, y + 5, 780, y + 17), 6, "#1F2937" if dark else "#E6EAF2")
        rounded(draw, (560, y + 5, int(560 + 220 * ratio), y + 17), 6, COLORS["indigo"])
        text(draw, (790, y - 2), amount, 15, fg, "bold")
        y += 56

    rounded(draw, (890, 300, 1390, 590), 16, card, border)
    text(draw, (920, 330), "Exception mix", 18, fg, "black")
    center = (1058, 450)
    draw.ellipse((970, 362, 1146, 538), fill=COLORS["indigo"])
    draw.pieslice((970, 362, 1146, 538), start=276, end=360, fill=COLORS["amber"])
    draw.ellipse((1018, 410, 1098, 490), fill=card)
    text(draw, center, "71%", 24, fg, "black", anchor="mm")
    text(draw, (1190, 410), "● Ledger mapping 71%", 15, COLORS["indigo"], "bold")
    text(draw, (1190, 454), "● Tax handling 29%", 15, COLORS["amber"], "bold")

    for i, (title, value) in enumerate([
        ("Top account", "Purchases A/C"),
        ("Top item", "Purified Terephthalic Acid"),
        ("Primary ERP", "Tally + QuickBooks"),
    ]):
        x = 310 + i * 360
        rounded(draw, (x, 630, x + 320, 800), 16, card, border)
        text(draw, (x + 26, 660), title.upper(), 12, COLORS["muted"], "bold")
        text(draw, (x + 26, 704), value, 22, fg, "black")
        text(draw, (x + 26, 754), "Live from invoice activity", 14, muted)
    return img


def mobile_sample() -> Image.Image:
    img = Image.new("RGB", (430, 932), COLORS["dark_bg"])
    draw = ImageDraw.Draw(img)
    logo(draw, 26, 28, True)
    rounded(draw, (298, 32, 398, 72), 12, COLORS["indigo"])
    text(draw, (348, 52), "Approve", 15, "#FFFFFF", "bold", anchor="mm")
    text(draw, (26, 112), "Review", 13, COLORS["muted"], "bold")
    text(draw, (26, 142), "Madelin invoice", 34, COLORS["dark_text"], "black")
    text(draw, (26, 188), "Ready for posting after one ledger confirmation.", 15, COLORS["dark_muted"])
    rounded(draw, (26, 230, 404, 372), 16, COLORS["dark_surface"], COLORS["dark_border"])
    text(draw, (50, 258), "TOTAL", 12, COLORS["dark_muted"], "bold")
    text(draw, (50, 298), "INR 633,912", 32, COLORS["dark_text"], "black")
    text(draw, (50, 342), "Purchase voucher", 15, COLORS["dark_muted"])
    rounded(draw, (26, 398, 404, 540), 16, COLORS["dark_surface"], COLORS["dark_border"])
    text(draw, (50, 426), "CONFIDENCE", 12, COLORS["dark_muted"], "bold")
    text(draw, (50, 466), "96%", 32, COLORS["cyan"], "black")
    text(draw, (50, 510), "Fields and tax validated", 15, COLORS["dark_muted"])
    rounded(draw, (26, 574, 404, 790), 18, COLORS["dark_card"], COLORS["dark_border"])
    text(draw, (50, 602), "Accounting entry", 20, COLORS["dark_text"], "black")
    entries = [("Vendor", "Madelin Enterprises"), ("Ledger", "Purchases A/C"), ("Tax", "IGST A/C"), ("System", "TallyPrime")]
    y = 648
    for label, value in entries:
        text(draw, (50, y), label.upper(), 11, COLORS["muted"], "bold")
        text(draw, (172, y - 3), value, 17, COLORS["dark_text"], "bold")
        y += 42
    rounded(draw, (26, 820, 404, 880), 16, COLORS["indigo"])
    text(draw, (215, 850), "Post to Tally", 19, "#FFFFFF", "bold", anchor="mm")
    text(draw, (215, 910), "Secure connector online", 14, COLORS["cyan_soft"], "bold", anchor="mm")
    return img


def main() -> None:
    outputs = [
        ("siftentry-invoice-queue-light.png", invoice_queue(False)),
        ("siftentry-invoice-queue-dark.png", invoice_queue(True)),
        ("siftentry-analytics-light.png", analytics_sample(False)),
        ("siftentry-mobile-approval-dark.png", mobile_sample()),
    ]
    for filename, image in outputs:
        image.save(OUT_DIR / filename)
        print(OUT_DIR / filename)


if __name__ == "__main__":
    main()
