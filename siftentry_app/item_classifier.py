"""
Item Classifier Module for SiftEntry
=====================================
Maps extracted invoice line descriptions into generic platform categories and
client-specific accounting codes:
  1. Optional seed mappings from a CSV, disabled by default for new clients
  2. Generic keyword fallback rules for common invoice line descriptions
  3. Client GL mapping from worksheet or manual configuration

SETUP:
  Optional client mapping files can be loaded from the GL Mapping page.

USAGE:
  from item_classifier import ItemClassifier
  
  classifier = ItemClassifier()
  
  # Classify a single line item
  cat = classifier.classify("POLYETHYLENE GLYCOL", source="Contract")
  # Returns: "Materials"
  
  # Load client GL mapping from their worksheet
  classifier.load_client_mapping("client_worksheet.xlsx")
  
  # Get GL code for a line item
  gl = classifier.get_gl_code("POLYETHYLENE GLYCOL", source="Contract")
  # Returns: {"subcategory": "Materials", "gl_code": "5100", "client_name": "Raw Materials"}
"""

import csv
import os
import re


# Optional legacy seed keyword rules are intentionally empty in the universal
# client build. Client-specific categories should come from GL Mapping.
KEYWORD_RULES = []

UNIVERSAL_KEYWORD_RULES = [
    (["cgst", "sgst", "igst", "gst", "vat", "tax"], None, "Taxes"),
    (["freight", "shipping", "transport", "logistics", "delivery"], None, "Freight"),
    (["packing", "packaging", "pallet", "carton"], None, "Packing"),
    (["polyethylene", "glycol", "pta", "lldpe", "resin", "chemical", "bearing", "fastener", "steel", "material", "goods", "product"], None, "Materials"),
    (["service", "labour", "labor", "installation", "maintenance", "repair"], None, "Services"),
    (["admin", "processing", "misc", "other charges"], None, "Other Charges"),
]

# Default platform categories
PLATFORM_CATEGORIES = [
    "Materials", "Services", "Freight", "Packing", "Taxes", "Other Charges",
    "Unmapped Item",
]


class ItemClassifier:
    """
    Classifies invoice line item descriptions into platform subcategories, then
    maps those categories to client-specific GL codes.
    
    1. Optional client/industry seed CSV, when explicitly provided
    2. Keyword-based fallback rules
    3. Client GL code mapping from their worksheet
    """

    def __init__(self, subcat_path=None, use_seed_mappings=False):
        self.subcat = {}       # key: (ITEM_DESC_upper, SOURCE) -> Subcategory
        self.subcat_desc = {}  # key: ITEM_DESC_upper -> Subcategory (no source)
        self.client_map = {}   # key: subcategory -> {gl_code, client_name, ...}
        self.use_seed_mappings = bool(use_seed_mappings)
        
        if self.use_seed_mappings and subcat_path and os.path.exists(subcat_path):
            self.load_subcat(subcat_path)

    def load_subcat(self, path):
        """Load an optional client/industry seed mapping CSV."""
        with open(path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                desc = row.get("ITEM_DESC", "").strip().upper()
                source = row.get("SOURCE", "").strip()
                subcat = row.get("Subcategory", "").strip()
                if desc and subcat:
                    # Exact match with source (primary)
                    self.subcat[(desc, source)] = subcat
                    # Description-only match (fallback)
                    if desc not in self.subcat_desc:
                        self.subcat_desc[desc] = subcat
        
        print(f"Loaded {len(self.subcat)} exact mappings, "
              f"{len(self.subcat_desc)} description mappings")

    def load_client_mapping(self, xlsx_path):
        """Load client GL mapping from their filled worksheet."""
        try:
            import openpyxl
            wb = openpyxl.load_workbook(xlsx_path, read_only=True)
            ws = wb["Coding Worksheet"]
            for row in ws.iter_rows(min_row=2, values_only=True):
                if not row or not row[0]:
                    continue
                category = str(row[0]).strip()
                client_name = str(row[2]).strip() if row[2] else ""
                gl_code = str(row[3]).strip() if row[3] else ""
                tail_codes = str(row[4]).strip() if row[4] else ""
                icao_codes = str(row[5]).strip() if row[5] else ""
                
                self.client_map[category] = {
                    "gl_code": gl_code,
                    "client_name": client_name,
                    "tail_codes": tail_codes,
                    "icao_codes": icao_codes,
                }
            wb.close()
            print(f"Loaded {len(self.client_map)} client GL mappings")
        except Exception as e:
            print(f"Error loading client mapping: {e}")

    def load_client_mapping_dict(self, mapping_dict):
        """Load client mapping from a dict.
        
        mapping_dict: {subcategory: {"gl_code": "5100", "client_name": "Raw Materials"}}
        """
        self.client_map = mapping_dict

    @staticmethod
    def platform_category(subcategory):
        """Return the platform category bucket used by exports."""
        if subcategory == "Taxes":
            return "Tax Item"
        if subcategory == "Freight":
            return "Freight / Logistics"
        return "Expense Item"

    def classify(self, item_desc, source="Contract"):
        """
        Classify a line item description into a platform subcategory.
        
        Uses generic matching by default:
        1. Optional exact match from a seed CSV, when enabled
        2. Generic keyword fallback
        3. Optional legacy seed keyword fallback, when enabled
        
        Returns: subcategory string (e.g., "Materials", "Services")
        """
        if not item_desc:
            return "Unmapped Item"
        
        desc_upper = item_desc.strip().upper()
        
        # Clean description: remove leading * and trailing " - EA" type suffixes
        desc_clean = desc_upper.lstrip("*").strip()
        
        if self.use_seed_mappings:
            key = (desc_clean, source)
            if key in self.subcat:
                return self.subcat[key]
            
            for src in ["Contract", "Retail", "Services", "AVCARD"]:
                key2 = (desc_clean, src)
                if key2 in self.subcat:
                    return self.subcat[key2]
            
            if desc_clean in self.subcat_desc:
                return self.subcat_desc[desc_clean]
            
            desc_no_ea = re.sub(r"\s*-\s*EA$", "", desc_clean).strip()
            if desc_no_ea in self.subcat_desc:
                return self.subcat_desc[desc_no_ea]
        
        desc_lower = item_desc.lower()
        for keywords, source_filter, subcategory in UNIVERSAL_KEYWORD_RULES:
            if source_filter and source_filter != source:
                continue
            for kw in keywords:
                if kw.lower() in desc_lower:
                    return subcategory

        if self.use_seed_mappings:
            for keywords, source_filter, subcategory in KEYWORD_RULES:
                if source_filter and source_filter != source:
                    continue
                for kw in keywords:
                    if kw.lower() in desc_lower:
                        return subcategory
        
        return "Unmapped Item"

    def get_gl_info(self, item_desc, source="Contract"):
        """
        Get full GL mapping info for a line item.
        
        Returns dict:
        {
            "subcategory": "Materials",
            "gl_code": "5100",
            "client_name": "Raw Materials",
            "match_tier": "exact" | "desc_only" | "keyword" | "default"
        }
        """
        subcategory = self.classify(item_desc, source)
        
        # Determine match tier
        desc_upper = (item_desc or "").strip().upper().lstrip("*").strip()
        if self.use_seed_mappings and any((desc_upper, s) in self.subcat for s in ["Contract","Retail","Services","AVCARD"]):
            tier = "exact"
        elif self.use_seed_mappings and desc_upper in self.subcat_desc:
            tier = "desc_only"
        elif subcategory != "Unmapped Item":
            tier = "keyword"
        else:
            tier = "default"
        
        # Client mapping. Leave client-facing fields blank until a worksheet/manual map exists.
        client_info = self.client_map.get(subcategory)
        
        return {
            "subcategory": subcategory,
            "platform_category": self.platform_category(subcategory),
            "category": client_info.get("client_name", "") if client_info else subcategory,
            "gl_code": client_info.get("gl_code", "") if client_info else "",
            "client_name": client_info.get("client_name", "") if client_info else "",
            "tail_codes": client_info.get("tail_codes", "") if client_info else "",
            "icao_codes": client_info.get("icao_codes", "") if client_info else "",
            "match_tier": tier,
        }

    def classify_invoice_rows(self, rows, source="Contract"):
        """
        Classify all line items in a parsed invoice.
        
        Args:
            rows: list of line item dicts from your parser
            source: "Contract", "Retail", or "Services"
        
        Returns: list of dicts with added classification fields
        """
        results = []
        for row in rows:
            desc = row.get("DESCRIPTION", "")
            info = self.get_gl_info(desc, source)
            enriched = dict(row)
            enriched["SUBCATEGORY"] = info["subcategory"]
            enriched["PLATFORM_CATEGORY"] = info["platform_category"]
            enriched["CATEGORY"] = info["category"]
            enriched["GL_CODE"] = info["gl_code"]
            enriched["CLIENT_CATEGORY"] = info["client_name"]
            enriched["MATCH_TIER"] = info["match_tier"]
            results.append(enriched)
        return results

    def get_category_summary(self, rows, source="Contract"):
        """
        Summarize invoice by subcategory.
        
        Returns: dict of {subcategory: total_amount}
        """
        summary = {}
        for row in rows:
            desc = row.get("DESCRIPTION", "")
            cat = self.classify(desc, source)
            amt = float(row.get("AMOUNT", 0) or 0)
            summary[cat] = summary.get(cat, 0) + amt
        return summary


# --- Streamlit UI for client mapping ---

def classifier_settings_ui(classifier):
    """
    Streamlit sidebar/page for client GL mapping configuration.
    Call this in your app.py settings section.
    """
    import streamlit as st
    
    st.markdown("### Item Classification & GL Mapping")
    
    # Option 1: Upload client worksheet
    uploaded = st.file_uploader(
        "Upload client coding worksheet (.xlsx)",
        type=["xlsx"],
        key="client_worksheet_upload"
    )
    if uploaded:
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            tmp.write(uploaded.read())
            tmp_path = tmp.name
        classifier.load_client_mapping(tmp_path)
        os.unlink(tmp_path)
        st.success(f"Loaded {len(classifier.client_map)} GL mappings from worksheet")
    
    # Option 2: Manual mapping via dropdowns
    with st.expander("Manual GL Mapping (or edit uploaded)", expanded=False):
        st.caption("Map each platform category to your GL code")
        
        mapping = dict(classifier.client_map)
        
        for cat in PLATFORM_CATEGORIES:
            existing = mapping.get(cat, {})
            col1, col2 = st.columns([1, 1])
            with col1:
                st.text(cat)
            with col2:
                gl = st.text_input(
                    f"GL Code for {cat}",
                    value=existing.get("gl_code", ""),
                    key=f"gl_{cat}",
                    label_visibility="collapsed"
                )
                if gl:
                    if cat not in mapping:
                        mapping[cat] = {}
                    mapping[cat]["gl_code"] = gl
                    mapping[cat]["client_name"] = existing.get("client_name", cat)
        
        if st.button("Save GL Mapping", key="save_gl_mapping"):
            classifier.load_client_mapping_dict(mapping)
            st.session_state["client_gl_mapping"] = mapping
            st.success("GL mapping saved!")


# --- Quick self-test ---

if __name__ == "__main__":
    # Optional seed CSV is disabled by default for new client workspaces.
    c = ItemClassifier(use_seed_mappings=False)
    
    # Test classifications
    test_items = [
        ("POLYETHYLENE GLYCOL TECHNICAL GRADE", "Contract"),
        ("PTA IMPORTED", "Contract"),
        ("LLDPE MATERIAL", "Contract"),
        ("FREIGHT CHARGES", "Contract"),
        ("PACKING CHARGES", "Contract"),
        ("CGST", "Retail"),
        ("SGST", "Retail"),
        ("INSTALLATION SERVICE", "Services"),
        ("ADMINISTRATION FEE", "Contract"),
        ("*FUEL COORD FEE-4440 LITERS", "Contract"),
        ("ADMIN FEES", "Contract"),
        ("MINERAL OIL TAX", "Contract"),
        ("HOOK UP FEE", "Contract"),
    ]
    
    print(f"{'DESCRIPTION':50s} {'SOURCE':12s} {'SUBCATEGORY':25s} {'TIER'}")
    print("-" * 100)
    for desc, source in test_items:
        info = c.get_gl_info(desc, source)
        print(f"{desc:50s} {source:12s} {info['subcategory']:25s} {info['match_tier']}")
