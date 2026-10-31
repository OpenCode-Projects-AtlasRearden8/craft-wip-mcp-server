"""Comes seeded with friendly sample projects so the craft room is never empty."""

SCARF_DONE = 120
SCARF_TOTAL = 180


def sample_store() -> dict:
    """A fresh store with three sample WIPs, a small stash, and two deadlines."""
    return {
        "version": 1,
        "wips": [
            {
                "id": "w-1",
                "name": "Cranberry cable scarf",
                "craft_type": "knit",
                "pattern_notes": "Cable pattern repeats every 12 rows. Check row 96 switch to 2x2 rib for the block-in rows.",
                "total_units": SCARF_TOTAL,
                "done_units": SCARF_DONE,
                "needs": [
                    {"name": "merino worsted - cranberry", "per_unit": 0.5}
                ],
                "deadlines": [
                    {"id": "d-1", "recipient": "Niece Rori", "event_date": "2099-12-14", "lead_time_days": 21}
                ],
            },
            {
                "id": "w-2",
                "name": "FFXIV sprout embroidery hoop",
                "craft_type": "embroidery",
                "pattern_notes": "Sprout buddy in a 6-inch hoop. Stem uses split stitch; leaf outline is backstitch.",
                "total_units": 1000,
                "done_units": 250,
                "needs": [
                    {"name": "embroidery floss - sprout green", "per_unit": 0.05}
                ],
                "deadlines": [],
            },
            {
                "id": "w-3",
                "name": "Nurse badge ribbon lanyards",
                "craft_type": "sewing",
                "pattern_notes": "Ribbon + retractable clip. Last lanyard is sage, needs the clip sewn on.",
                "total_units": 6,
                "done_units": 5,
                "needs": [],
                "deadlines": [
                    {"id": "d-2", "recipient": "Unit 4 coworkers", "event_date": "2099-11-20", "lead_time_days": 10}
                ],
            },
        ],
        "stash": [
            {
                "id": "s-1",
                "material": "merino worsted - cranberry",
                "quantity": 40,
                "unit": "grams",
                "dye_lot": "LT-2214",
                "note": "Enough for about 80 more rows of the scarf.",
            },
            {
                "id": "s-2",
                "material": "merino worsted - sage",
                "quantity": 90,
                "unit": "grams",
                "dye_lot": "LT-1188",
                "note": "",
            },
            {
                "id": "s-3",
                "material": "embroidery floss - sprout green",
                "quantity": 6,
                "unit": "skeins",
                "dye_lot": "D-7",
                "note": "",
            },
            {
                "id": "s-4",
                "material": "ribbon - sage botanical print",
                "quantity": 12,
                "unit": "feet",
                "dye_lot": "",
                "note": "Matches the lanyard ribbon.",
            },
        ],
        "deadlines": [],
    }
